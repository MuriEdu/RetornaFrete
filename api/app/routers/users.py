import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, create_refresh_token, decode_refresh_token, hash_password, verify_password
from app.deps import get_current_user, get_db
from app.models import (
    AccountStatus,
    Cargo,
    CargoStatus,
    RefreshToken,
    PayoutProvider,
    Role,
    Trip,
    TripStatus,
    User,
    UserPayoutAccount,
)
from app.schemas import CreateUserRequest, LoginRequest, LoginResponse, PayoutAccountResponse, PayoutAccountUpsertRequest, RefreshTokenRequest, UserContextResponse
from app.services.payouts import (
    build_mercado_pago_connect_url,
    build_payout_state,
    exchange_mercado_pago_code,
    test_mercado_pago_payout_channel,
    upsert_manual_payout_account,
    upsert_mercado_pago_account,
    verify_payout_state,
)

router = APIRouter(prefix="/users", tags=["users"])


def _vehicle_payload(vehicle):
    return {
        "id": vehicle.id,
        "brand": vehicle.brand,
        "model": vehicle.model,
        "licensePlate": vehicle.license_plate,
        "typeName": vehicle.type.name,
        "typeId": vehicle.type.id,
    }


def _payout_payload(account: UserPayoutAccount) -> PayoutAccountResponse:
    return PayoutAccountResponse(
        id=account.id,
        provider=account.provider,
        status=account.status,
        accountEmail=account.account_email,
        pixKey=account.pix_key,
        bankName=account.bank_name,
        bankBranch=account.bank_branch,
        bankAccount=account.bank_account,
        bankAccountType=account.bank_account_type,
        ownerName=account.owner_name,
        oauthExpiresAt=account.oauth_expires_at,
        createdAt=account.created_at,
        updatedAt=account.updated_at,
    )


def build_user_context(db: Session, user: User) -> UserContextResponse:
    active_trip = db.scalar(
        select(Trip)
        .where(Trip.user_id == user.id, Trip.status.in_([TripStatus.AVAILABLE, TripStatus.MATCHED]))
        .order_by(desc(Trip.created_at))
        .limit(1)
    )
    active_cargo = db.scalar(
        select(Cargo)
        .where(Cargo.user_id == user.id, Cargo.status.in_([CargoStatus.ACTIVE, CargoStatus.MATCHED]))
        .order_by(desc(Cargo.created_at))
        .limit(1)
    )

    trip_payload = None
    if active_trip:
        trip_payload = {
            "id": active_trip.id,
            "originName": active_trip.origin_name,
            "destinationName": active_trip.destination_name,
            "tripDate": active_trip.trip_date,
            "pricePerKm": active_trip.price_per_km,
            "status": active_trip.status,
            "vehicle": _vehicle_payload(active_trip.vehicle),
        }

    cargo_payload = None
    if active_cargo:
        cargo_payload = {
            "id": active_cargo.id,
            "originName": active_cargo.origin_name,
            "destinationName": active_cargo.destination_name,
            "productName": active_cargo.product_name,
            "weightKg": active_cargo.weight_kg,
            "tripDate": active_cargo.trip_date,
            "status": active_cargo.status,
            "createdAt": active_cargo.created_at,
            "requiredVehicleType": {
                "id": active_cargo.required_vehicle_type.id,
                "name": active_cargo.required_vehicle_type.name,
            },
            "isDateFlexible": active_cargo.is_date_flexible,
        }

    payout_account = db.scalar(select(UserPayoutAccount).where(UserPayoutAccount.user_id == user.id))

    return UserContextResponse(
        id=user.id,
        fullname=user.fullname,
        email=user.email,
        roles=[user.role],
        accountStatus=user.account_status,
        activeTrip=trip_payload,
        activeCargo=cargo_payload,
        payoutAccount=_payout_payload(payout_account) if payout_account else None,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserRequest, db: Session = Depends(get_db)) -> Response:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        fullname=payload.fullname,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        account_status=AccountStatus.ACTIVE,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Could not create user") from exc
    return Response(status_code=status.HTTP_201_CREATED)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(str(user.id))
    refresh_token, expires_at = create_refresh_token(str(user.id))
    db.add(RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires_at.replace(tzinfo=None)))
    db.commit()

    return LoginResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        user=build_user_context(db, user),
    )


@router.post("/refresh-token")
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    token_record = db.scalar(select(RefreshToken).where(RefreshToken.token == payload.refreshToken))
    if not token_record or token_record.revoked or token_record.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=401, detail="Refresh token expired")

    decoded = decode_refresh_token(payload.refreshToken)
    user = db.scalar(select(User).where(User.id == uuid.UUID(decoded["sub"])))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(str(user.id))
    return {"accessToken": access_token}


@router.post("/signout", status_code=status.HTTP_204_NO_CONTENT)
def signout(payload: RefreshTokenRequest, db: Session = Depends(get_db)) -> Response:
    token_record = db.scalar(select(RefreshToken).where(RefreshToken.token == payload.refreshToken))
    if token_record:
        token_record.revoked = True
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserContextResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserContextResponse:
    return build_user_context(db, current_user)


@router.get("/payout-account", response_model=PayoutAccountResponse | None)
def get_payout_account(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    account = db.scalar(select(UserPayoutAccount).where(UserPayoutAccount.user_id == current_user.id))
    return _payout_payload(account) if account else None


@router.put("/payout-account", response_model=PayoutAccountResponse)
def upsert_payout_account(
    payload: PayoutAccountUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PayoutAccountResponse:
    if payload.provider == PayoutProvider.MERCADO_PAGO:
        raise HTTPException(status_code=400, detail="Use the Mercado Pago connect flow to link a payout account")

    account = upsert_manual_payout_account(
        db,
        current_user,
        provider=payload.provider,
        pix_key=payload.pixKey,
        bank_name=payload.bankName,
        bank_branch=payload.bankBranch,
        bank_account=payload.bankAccount,
        bank_account_type=payload.bankAccountType,
        owner_name=payload.ownerName,
    )
    db.commit()
    db.refresh(account)
    return _payout_payload(account)


@router.get("/payout-account/mercado-pago/connect")
def get_mercado_pago_connect_url(current_user: User = Depends(get_current_user)) -> dict[str, str]:
    return {"connectUrl": build_mercado_pago_connect_url(build_payout_state(str(current_user.id)))}


@router.post("/payout-account/mercado-pago/payout-test")
async def test_mercado_pago_payout(current_user: User = Depends(get_current_user)) -> dict[str, str | bool]:
    return await test_mercado_pago_payout_channel(current_user)


@router.get("/payout-account/mercado-pago/callback")
async def mercado_pago_connect_callback(
    code: str,
    state: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if not state:
        raise HTTPException(status_code=400, detail="Missing OAuth state")

    user_id = uuid.UUID(verify_payout_state(state))

    user = db.scalar(select(User).where(User.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token_payload = await exchange_mercado_pago_code(code)
    account = upsert_mercado_pago_account(
        db,
        user,
        access_token=token_payload.get("access_token"),
        refresh_token=token_payload.get("refresh_token"),
        expires_in=token_payload.get("expires_in"),
        account_email=token_payload.get("email"),
    )
    db.commit()
    db.refresh(account)
    return RedirectResponse(url="retornafrete://home?payout_connected=1", status_code=302)
