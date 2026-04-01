import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Cargo, CargoStatus, Role, User, VehicleType
from app.schemas import CargoCreateRequest

router = APIRouter(prefix="/api/cargos", tags=["cargos"])


def serialize_cargo(cargo: Cargo) -> dict:
    return {
        "id": cargo.id,
        "originName": cargo.origin_name,
        "destinationName": cargo.destination_name,
        "productName": cargo.product_name,
        "weightKg": cargo.weight_kg,
        "tripDate": cargo.trip_date,
        "status": cargo.status,
        "createdAt": cargo.created_at,
        "requiredVehicleType": {
            "id": cargo.required_vehicle_type.id,
            "name": cargo.required_vehicle_type.name,
        },
        "isDateFlexible": cargo.is_date_flexible,
    }


@router.post("")
def create_cargo(
    payload: CargoCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role != Role.SHIPPER:
        raise HTTPException(status_code=403, detail="Only shippers can create cargos")

    vehicle_type = db.scalar(select(VehicleType).where(VehicleType.id == payload.requiredVehicleType))
    if not vehicle_type:
        raise HTTPException(status_code=404, detail="Vehicle type not found")

    cargo = Cargo(
        user_id=current_user.id,
        required_vehicle_type_id=vehicle_type.id,
        origin_name=payload.originCity,
        destination_name=payload.destCity,
        origin_lat=payload.originLat,
        origin_lon=payload.originLon,
        dest_lat=payload.destLat,
        dest_lon=payload.destLon,
        trip_date=payload.tripDate,
        product_name=payload.productName,
        weight_kg=payload.weightKg,
        is_date_flexible=payload.isDateFlexible,
        status=CargoStatus.ACTIVE,
    )
    db.add(cargo)
    db.commit()
    db.refresh(cargo)
    return serialize_cargo(cargo)


@router.put("/{cargo_id}")
def update_cargo(
    cargo_id: uuid.UUID,
    payload: CargoCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    cargo = db.scalar(select(Cargo).where(Cargo.id == cargo_id, Cargo.user_id == current_user.id))
    if not cargo:
        raise HTTPException(status_code=404, detail="Cargo not found")
    vehicle_type = db.scalar(select(VehicleType).where(VehicleType.id == payload.requiredVehicleType))
    if not vehicle_type:
        raise HTTPException(status_code=404, detail="Vehicle type not found")

    cargo.origin_name = payload.originCity
    cargo.destination_name = payload.destCity
    cargo.origin_lat = payload.originLat
    cargo.origin_lon = payload.originLon
    cargo.dest_lat = payload.destLat
    cargo.dest_lon = payload.destLon
    cargo.trip_date = payload.tripDate
    cargo.product_name = payload.productName
    cargo.weight_kg = payload.weightKg
    cargo.required_vehicle_type_id = vehicle_type.id
    cargo.is_date_flexible = payload.isDateFlexible
    db.commit()
    db.refresh(cargo)
    return serialize_cargo(cargo)


@router.delete("/{cargo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cargo(
    cargo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    cargo = db.scalar(select(Cargo).where(Cargo.id == cargo_id, Cargo.user_id == current_user.id))
    if not cargo:
        raise HTTPException(status_code=404, detail="Cargo not found")
    cargo.status = CargoStatus.CANCELED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/my-cargos")
def list_my_cargos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    cargos = db.scalars(select(Cargo).where(Cargo.user_id == current_user.id).order_by(desc(Cargo.created_at))).all()
    return [serialize_cargo(cargo) for cargo in cargos]
