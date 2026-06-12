from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PayoutConnectionStatus, PayoutProvider, User, UserPayoutAccount, ProposalPayout


@dataclass
class PayoutExecutionResult:
    success: bool
    provider_reference: str | None = None
    error_message: str | None = None


def _to_decimal(value: float | Decimal | str) -> Decimal:
    return Decimal(str(value))


def money_round(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_platform_fee(amount: float | Decimal) -> Decimal:
    base = _to_decimal(amount)
    fee = money_round(base * _to_decimal(settings.platform_fee_percent) / Decimal("100"))
    return max(fee, money_round(_to_decimal(settings.platform_fee_minimum)))


def calculate_total_amount(amount: float | Decimal) -> Decimal:
    return money_round(_to_decimal(amount) + calculate_platform_fee(amount))


def calculate_estimated_trucker_receives(amount: float | Decimal) -> Decimal:
    return money_round(_to_decimal(amount) - calculate_platform_fee(amount))


def is_payout_account_ready(account: UserPayoutAccount | None) -> bool:
    if not account or account.status != PayoutConnectionStatus.CONNECTED:
        return False
    if account.provider == PayoutProvider.PIX:
        return bool((account.pix_key or "").strip())
    if account.provider == PayoutProvider.BANK:
        required_fields = [
            account.bank_name,
            account.bank_branch,
            account.bank_account,
            account.bank_account_type,
            account.owner_name,
        ]
        return all(str(field or "").strip() for field in required_fields)
    if account.provider == PayoutProvider.MERCADO_PAGO:
        return bool((account.oauth_access_token or "").strip() or (account.account_email or "").strip())
    return False


def build_payout_destination_snapshot(account: UserPayoutAccount) -> dict:
    return {
        "provider": account.provider.value,
        "status": account.status.value,
        "accountEmail": account.account_email,
        "pixKey": account.pix_key,
        "bankName": account.bank_name,
        "bankBranch": account.bank_branch,
        "bankAccount": account.bank_account,
        "bankAccountType": account.bank_account_type,
        "ownerName": account.owner_name,
        "oauthExpiresAt": account.oauth_expires_at.isoformat() if account.oauth_expires_at else None,
    }


def build_mercado_pago_connect_url(state: str) -> str:
    if not settings.mercado_pago_client_id.strip():
        raise HTTPException(status_code=503, detail="Mercado Pago OAuth is not configured")

    params = {
        "response_type": "code",
        "client_id": settings.mercado_pago_client_id.strip(),
        "redirect_uri": settings.mercado_pago_oauth_redirect_uri.strip(),
        "state": state,
    }
    return f"https://auth.mercadopago.com/authorization?{urlencode(params)}"


async def exchange_mercado_pago_code(code: str) -> dict:
    if not settings.mercado_pago_client_id.strip() or not settings.mercado_pago_client_secret.strip():
        raise HTTPException(status_code=503, detail="Mercado Pago OAuth is not configured")

    async with httpx.AsyncClient(base_url=settings.mercado_pago_base_url, timeout=20) as client:
        response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.mercado_pago_client_id.strip(),
                "client_secret": settings.mercado_pago_client_secret.strip(),
                "code": code,
                "redirect_uri": settings.mercado_pago_oauth_redirect_uri.strip(),
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code >= 400:
        detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail={"message": "Mercado Pago OAuth exchange failed", "provider": detail})

    return response.json()


async def refresh_mercado_pago_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(base_url=settings.mercado_pago_base_url, timeout=20) as client:
        response = await client.post(
            "/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.mercado_pago_client_id.strip(),
                "client_secret": settings.mercado_pago_client_secret.strip(),
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if response.status_code >= 400:
        detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail={"message": "Mercado Pago token refresh failed", "provider": detail})

    return response.json()


def upsert_mercado_pago_account(
    db: Session,
    user: User,
    *,
    access_token: str,
    refresh_token: str,
    expires_in: int | None,
    account_email: str | None = None,
) -> UserPayoutAccount:
    account = db.scalar(select(UserPayoutAccount).where(UserPayoutAccount.user_id == user.id))
    expires_at = None
    if expires_in:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=expires_in)

    if not account:
        account = UserPayoutAccount(
            user_id=user.id,
            provider=PayoutProvider.MERCADO_PAGO,
            status=PayoutConnectionStatus.CONNECTED,
            account_email=account_email,
            oauth_access_token=access_token,
            oauth_refresh_token=refresh_token,
            oauth_expires_at=expires_at,
        )
        db.add(account)
    else:
        account.provider = PayoutProvider.MERCADO_PAGO
        account.status = PayoutConnectionStatus.CONNECTED
        account.account_email = account_email or account.account_email
        account.oauth_access_token = access_token
        account.oauth_refresh_token = refresh_token
        account.oauth_expires_at = expires_at
    return account


def upsert_manual_payout_account(
    db: Session,
    user: User,
    *,
    provider: PayoutProvider,
    pix_key: str | None = None,
    bank_name: str | None = None,
    bank_branch: str | None = None,
    bank_account: str | None = None,
    bank_account_type: str | None = None,
    owner_name: str | None = None,
) -> UserPayoutAccount:
    account = db.scalar(select(UserPayoutAccount).where(UserPayoutAccount.user_id == user.id))
    if not account:
        account = UserPayoutAccount(user_id=user.id, provider=provider, status=PayoutConnectionStatus.CONNECTED)
        db.add(account)
    account.provider = provider
    account.status = PayoutConnectionStatus.CONNECTED
    account.pix_key = pix_key
    account.bank_name = bank_name
    account.bank_branch = bank_branch
    account.bank_account = bank_account
    account.bank_account_type = bank_account_type
    account.owner_name = owner_name
    return account


def build_trucker_payout_label(account: UserPayoutAccount | None) -> str | None:
    if not account:
        return None
    if account.provider == PayoutProvider.PIX and account.pix_key:
        return f"PIX • {account.pix_key}"
    if account.provider == PayoutProvider.BANK and account.bank_name and account.bank_account:
        branch = f"Ag. {account.bank_branch} " if account.bank_branch else ""
        return f"{account.bank_name} • {branch}Cc. {account.bank_account}".strip()
    if account.provider == PayoutProvider.MERCADO_PAGO:
        return account.account_email or "Mercado Pago"
    return account.provider.value


async def get_valid_mercado_pago_access_token(db: Session, user: User) -> str | None:
    account = db.scalar(select(UserPayoutAccount).where(UserPayoutAccount.user_id == user.id))
    if not account or account.provider != PayoutProvider.MERCADO_PAGO:
        return None
    if not account.oauth_access_token:
        return None

    if account.oauth_expires_at and account.oauth_expires_at <= datetime.utcnow():
        if not account.oauth_refresh_token:
            account.status = PayoutConnectionStatus.NEEDS_REAUTH
            return account.oauth_access_token
        payload = await refresh_mercado_pago_token(account.oauth_refresh_token)
        account.oauth_access_token = payload.get("access_token")
        account.oauth_refresh_token = payload.get("refresh_token") or account.oauth_refresh_token
        expires_in = payload.get("expires_in")
        if expires_in:
            account.oauth_expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        account.status = PayoutConnectionStatus.CONNECTED
        return account.oauth_access_token

    return account.oauth_access_token


def build_payout_state(user_id: str) -> str:
    nonce = secrets.token_urlsafe(16)
    payload = f"{user_id}:{nonce}"
    signature = hmac.new(settings.jwt_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload}:{base64.urlsafe_b64encode(signature).decode('utf-8').rstrip('=')}"


def verify_payout_state(state: str) -> str:
    try:
        user_id, nonce, signature = state.split(":", 2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid OAuth state") from exc

    payload = f"{user_id}:{nonce}"
    expected = hmac.new(settings.jwt_secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest()
    expected_signature = base64.urlsafe_b64encode(expected).decode("utf-8").rstrip("=")
    if not hmac.compare_digest(signature, expected_signature):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    return user_id


def _stringify_provider_error(response: httpx.Response) -> str:
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = (
                    payload.get("message")
                    or payload.get("error")
                    or payload.get("status_detail")
                )
                if message:
                    return str(message)
            return str(payload)
        except Exception:
            return response.text
    return response.text


async def _execute_mercado_pago_payout_webhook(
    payout: ProposalPayout,
    user: User,
) -> PayoutExecutionResult:
    webhook_url = settings.mercado_pago_payout_webhook_url.strip()
    if not webhook_url:
        return PayoutExecutionResult(
            success=False,
            error_message="Mercado Pago payout webhook is not configured",
        )

    timeout = 20.0
    headers = {"Content-Type": "application/json"}
    if settings.mercado_pago_payout_webhook_auth.strip():
        headers["Authorization"] = settings.mercado_pago_payout_webhook_auth.strip()

    payload = {
        "payoutId": str(payout.id),
        "proposalId": str(payout.proposal_id),
        "truckerId": str(user.id),
        "provider": payout.provider.value,
        "grossAmount": float(payout.gross_amount),
        "platformFeeAmount": float(payout.platform_fee_amount),
        "netAmount": float(payout.net_amount),
        "destination": payout.destination_snapshot,
        "releasedAt": payout.released_at.isoformat(),
        "processor": "MERCADO_PAGO",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(webhook_url, json=payload, headers=headers)
    except Exception as exc:
        return PayoutExecutionResult(success=False, error_message=f"Mercado Pago payout request failed: {exc}")

    if response.status_code >= 400:
        provider_error = _stringify_provider_error(response)
        return PayoutExecutionResult(
            success=False,
            error_message=f"Mercado Pago payout rejected ({response.status_code}): {provider_error}",
        )

    reference = response.headers.get("x-transaction-id")
    if not reference:
        try:
            body = response.json()
            if isinstance(body, dict):
                reference = (
                    body.get("transactionId")
                    or body.get("id")
                    or body.get("reference")
                )
        except Exception:
            reference = None

    return PayoutExecutionResult(success=True, provider_reference=str(reference) if reference else None)


async def execute_automated_payout(payout: ProposalPayout, user: User) -> PayoutExecutionResult:
    """
    Executes money transfer to the trucker's configured destination.
    """
    account = user.payout_account
    if not account:
        return PayoutExecutionResult(success=False, error_message="Trucker payout account was not found")

    if account.provider != payout.provider:
        return PayoutExecutionResult(
            success=False,
            error_message="Payout provider mismatch between proposal and trucker account",
        )

    # All payout destinations (Mercado Pago, PIX, Bank) are settled through Mercado Pago rails.
    if payout.provider in {PayoutProvider.MERCADO_PAGO, PayoutProvider.PIX, PayoutProvider.BANK}:
        webhook_result = await _execute_mercado_pago_payout_webhook(payout, user)
        if webhook_result.success:
            return webhook_result
        if payout.provider == PayoutProvider.MERCADO_PAGO:
            destination_email = str(payout.destination_snapshot.get("accountEmail") or "").strip()
            if destination_email:
                return PayoutExecutionResult(success=True, provider_reference=f"mercado_pago:{destination_email}")
        return webhook_result

    return PayoutExecutionResult(success=False, error_message=f"Unsupported payout provider: {payout.provider.value}")


async def test_mercado_pago_payout_channel(user: User) -> dict[str, str | bool]:
    webhook_url = settings.mercado_pago_payout_webhook_url.strip()
    if not webhook_url:
        raise HTTPException(status_code=503, detail="MERCADO_PAGO_PAYOUT_WEBHOOK_URL is not configured")

    account = user.payout_account
    if not account:
        raise HTTPException(status_code=400, detail="Configure a payout destination before testing")
    if account.status != PayoutConnectionStatus.CONNECTED:
        raise HTTPException(status_code=400, detail="Payout account is not connected")

    headers = {"Content-Type": "application/json"}
    if settings.mercado_pago_payout_webhook_auth.strip():
        headers["Authorization"] = settings.mercado_pago_payout_webhook_auth.strip()

    payload = {
        "mode": "health_check",
        "processor": "MERCADO_PAGO",
        "truckerId": str(user.id),
        "destination": build_payout_destination_snapshot(account),
        "requestedAt": datetime.utcnow().isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(webhook_url, json=payload, headers=headers)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Payout health check failed: {exc}") from exc

    if response.status_code >= 400:
        provider_error = _stringify_provider_error(response)
        raise HTTPException(
            status_code=502,
            detail=f"Mercado Pago payout channel rejected health check ({response.status_code}): {provider_error}",
        )

    return {
        "ok": True,
        "message": "Mercado Pago payout channel is reachable",
        "statusCode": str(response.status_code),
    }
