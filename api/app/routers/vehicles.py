import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Role, User, Vehicle, VehicleType
from app.schemas import VehicleCreateRequest, VehicleResponse, VehicleTypeResponse

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.post("", response_model=VehicleResponse)
def create_vehicle(
    payload: VehicleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VehicleResponse:
    if current_user.role != Role.TRUCKER:
        raise HTTPException(status_code=403, detail="Only truckers can create vehicles")

    vehicle_type = db.scalar(select(VehicleType).where(VehicleType.id == payload.typeId))
    if not vehicle_type:
        raise HTTPException(status_code=404, detail="Vehicle type not found")

    vehicle = Vehicle(
        user_id=current_user.id,
        type_id=vehicle_type.id,
        brand=payload.brand,
        model=payload.model,
        license_plate=payload.licensePlate,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    return VehicleResponse(
        id=vehicle.id,
        brand=vehicle.brand,
        model=vehicle.model,
        licensePlate=vehicle.license_plate,
        typeName=vehicle.type.name,
        typeId=vehicle.type.id,
    )


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[VehicleResponse]:
    vehicles = db.scalars(select(Vehicle).where(Vehicle.user_id == current_user.id, Vehicle.active.is_(True))).all()
    return [
        VehicleResponse(
            id=vehicle.id,
            brand=vehicle.brand,
            model=vehicle.model,
            licensePlate=vehicle.license_plate,
            typeName=vehicle.type.name,
            typeId=vehicle.type.id,
        )
        for vehicle in vehicles
    ]


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.user_id == current_user.id))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    vehicle.active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/types", response_model=list[VehicleTypeResponse])
def list_types(db: Session = Depends(get_db)) -> list[VehicleTypeResponse]:
    return list(db.scalars(select(VehicleType).order_by(VehicleType.name)).all())
