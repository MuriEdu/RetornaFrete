import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.auth import create_access_token, create_refresh_token, decode_refresh_token, hash_password, verify_password
from app.deps import get_current_user, get_db
from app.models import (
    AccountStatus,
    Cargo,
    CargoStatus,
    RefreshToken,
    Role,
    Trip,
    TripStatus,
    User,
)
from app.schemas import CreateUserRequest, LoginRequest, LoginResponse, RefreshTokenRequest, UserContextResponse

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

    return UserContextResponse(
        id=user.id,
        fullname=user.fullname,
        email=user.email,
        roles=[user.role],
        accountStatus=user.account_status,
        activeTrip=trip_payload,
        activeCargo=cargo_payload,
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
    db.commit()
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
