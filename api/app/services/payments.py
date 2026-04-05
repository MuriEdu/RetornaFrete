import secrets
from datetime import datetime
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FreightPaymentStatus, Proposal, ProposalPayment, ProposalStatus


def mercado_pago_configured() -> bool:
    return bool(settings.mercado_pago_access_token.strip())


def build_external_reference(proposal_id) -> str:
    return f"proposal:{proposal_id}"


def generate_delivery_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def ensure_proposal_payment(db: Session, proposal: Proposal) -> ProposalPayment:
    if proposal.payment:
        if proposal.payment.amount != proposal.current_bid:
            proposal.payment.amount = proposal.current_bid
        return proposal.payment

    payment = ProposalPayment(
        proposal_id=proposal.id,
        amount=proposal.current_bid,
        status=FreightPaymentStatus.AWAITING_PAYMENT,
        delivery_code=generate_delivery_code(),
        mercado_pago_external_reference=build_external_reference(proposal.id),
    )
    db.add(payment)
    db.flush()
    proposal.payment = payment
    return payment


def payment_status_from_mercado_pago(status: str | None) -> FreightPaymentStatus:
    normalized = (status or "").lower()
    if normalized == "approved":
        return FreightPaymentStatus.APPROVED
    if normalized in {"pending", "in_process", "authorized"}:
        return FreightPaymentStatus.PENDING
    if normalized in {"cancelled", "cancelled_by_user"}:
        return FreightPaymentStatus.CANCELED
    return FreightPaymentStatus.FAILED


def _mercado_pago_headers() -> dict[str, str]:
    if not mercado_pago_configured():
        raise HTTPException(status_code=503, detail="Mercado Pago is not configured")
    return {
        "Authorization": f"Bearer {settings.mercado_pago_access_token}",
        "Content-Type": "application/json",
    }


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _apply_payment_payload(payment: ProposalPayment, payload: dict) -> ProposalPayment:
    payment_id = payload.get("id")
    status = payload.get("status")
    status_detail = payload.get("status_detail")

    if payment_id is not None:
        payment.mercado_pago_payment_id = str(payment_id)
    payment.mercado_pago_payment_status = status
    payment.mercado_pago_status_detail = status_detail
    payment.status = payment_status_from_mercado_pago(status)
    payment.last_error = None

    if payment.status == FreightPaymentStatus.APPROVED and not payment.paid_at:
        payment.paid_at = _parse_datetime(payload.get("date_approved")) or datetime.utcnow()

    if payment.status in {FreightPaymentStatus.FAILED, FreightPaymentStatus.CANCELED}:
        payment.last_error = status_detail or status or "Payment was not approved"

    return payment


async def create_checkout_preference(payment: ProposalPayment, proposal: Proposal, payer_email: str) -> ProposalPayment:
    notification_url = settings.mercado_pago_notification_url.strip() or None
    body: dict = {
        "external_reference": payment.mercado_pago_external_reference,
        "notification_url": notification_url,
        "items": [
            {
                "id": str(proposal.id),
                "title": f"Frete {proposal.cargo.origin_name} -> {proposal.cargo.destination_name}",
                "description": f"Pagamento antecipado do frete para {proposal.cargo.product_name}",
                "quantity": 1,
                "currency_id": "BRL",
                "unit_price": float(Decimal(payment.amount)),
            }
        ],
        "payer": {"email": payer_email},
        "metadata": {
            "proposal_id": str(proposal.id),
            "cargo_id": str(proposal.cargo_id),
            "trip_id": str(proposal.trip_id),
        },
    }

    back_urls = {
        "success": settings.mercado_pago_success_url.strip(),
        "pending": settings.mercado_pago_pending_url.strip(),
        "failure": settings.mercado_pago_failure_url.strip(),
    }
    filtered_back_urls = {key: value for key, value in back_urls.items() if value}
    if filtered_back_urls:
        body["back_urls"] = filtered_back_urls
        body["auto_return"] = "approved"

    async with httpx.AsyncClient(base_url=settings.mercado_pago_base_url, timeout=20) as client:
        response = await client.post("/checkout/preferences", headers=_mercado_pago_headers(), json=body)

    if response.status_code >= 400:
        detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail={"message": "Mercado Pago preference creation failed", "provider": detail})

    payload = response.json()
    payment.mercado_pago_preference_id = payload.get("id")
    payment.mercado_pago_checkout_url = payload.get("init_point")
    payment.mercado_pago_sandbox_checkout_url = payload.get("sandbox_init_point")
    payment.status = FreightPaymentStatus.PENDING
    payment.last_error = None
    return payment


async def fetch_payment_by_id(payment_id: str) -> dict:
    async with httpx.AsyncClient(base_url=settings.mercado_pago_base_url, timeout=20) as client:
        response = await client.get(f"/v1/payments/{payment_id}", headers=_mercado_pago_headers())

    if response.status_code >= 400:
        detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail={"message": "Mercado Pago payment lookup failed", "provider": detail})

    return response.json()


async def sync_payment_from_search(payment: ProposalPayment) -> ProposalPayment:
    params = {
        "external_reference": payment.mercado_pago_external_reference,
        "sort": "date_last_updated",
        "criteria": "desc",
        "limit": 1,
        "offset": 0,
    }
    async with httpx.AsyncClient(base_url=settings.mercado_pago_base_url, timeout=20) as client:
        response = await client.get("/v1/payments/search", headers=_mercado_pago_headers(), params=params)

    if response.status_code >= 400:
        detail = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
        raise HTTPException(status_code=502, detail={"message": "Mercado Pago payment search failed", "provider": detail})

    results = response.json().get("results") or []
    if not results:
        return payment

    return _apply_payment_payload(payment, results[0])


async def sync_payment_from_webhook(db: Session, payment_id: str) -> ProposalPayment | None:
    payload = await fetch_payment_by_id(payment_id)
    external_reference = payload.get("external_reference")
    if not external_reference:
        return None

    payment = db.scalar(select(ProposalPayment).where(ProposalPayment.mercado_pago_external_reference == external_reference))
    if not payment:
        return None

    return _apply_payment_payload(payment, payload)


def validate_payment_release(payment: ProposalPayment, proposal: Proposal) -> None:
    if proposal.status != ProposalStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Proposal must be accepted before delivery confirmation")
    if payment.status != FreightPaymentStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Freight payment has not been approved yet")
    if payment.released_at:
        raise HTTPException(status_code=400, detail="Freight payment has already been released")
