import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Role, Trip, TripStatus, User, Vehicle
from app.schemas import TripCreateRequest

router = APIRouter(prefix="/api/trips", tags=["trips"])


def serialize_trip(trip: Trip) -> dict:
    return {
        "id": trip.id,
        "originName": trip.origin_name,
        "destinationName": trip.destination_name,
        "tripDate": trip.trip_date,
        "pricePerKm": float(trip.price_per_km),
        "status": trip.status,
        "vehicle": {
            "id": trip.vehicle.id,
            "brand": trip.vehicle.brand,
            "model": trip.vehicle.model,
            "licensePlate": trip.vehicle.license_plate,
            "typeName": trip.vehicle.type.name,
            "typeId": trip.vehicle.type.id,
        },
    }


@router.post("")
def create_trip(
    payload: TripCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.role != Role.TRUCKER:
        raise HTTPException(status_code=403, detail="Only truckers can create trips")

    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicleId, Vehicle.user_id == current_user.id, Vehicle.active.is_(True)))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    trip = Trip(
        user_id=current_user.id,
        vehicle_id=vehicle.id,
        origin_name=payload.originCity,
        destination_name=payload.destCity,
        origin_lat=payload.originLat,
        origin_lon=payload.originLon,
        dest_lat=payload.destLat,
        dest_lon=payload.destLon,
        trip_date=payload.tripDate,
        price_per_km=payload.pricePerKm,
        status=TripStatus.AVAILABLE,
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)
    return serialize_trip(trip)


@router.put("/{trip_id}")
def update_trip(
    trip_id: uuid.UUID,
    payload: TripCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == current_user.id))
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    vehicle = db.scalar(select(Vehicle).where(Vehicle.id == payload.vehicleId, Vehicle.user_id == current_user.id, Vehicle.active.is_(True)))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")

    trip.origin_name = payload.originCity
    trip.destination_name = payload.destCity
    trip.origin_lat = payload.originLat
    trip.origin_lon = payload.originLon
    trip.dest_lat = payload.destLat
    trip.dest_lon = payload.destLon
    trip.trip_date = payload.tripDate
    trip.price_per_km = payload.pricePerKm
    trip.vehicle_id = vehicle.id
    db.commit()
    db.refresh(trip)
    return serialize_trip(trip)


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(
    trip_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    trip = db.scalar(select(Trip).where(Trip.id == trip_id, Trip.user_id == current_user.id))
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    trip.status = TripStatus.CANCELED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/my-trips")
def list_my_trips(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    trips = db.scalars(select(Trip).where(Trip.user_id == current_user.id).order_by(desc(Trip.created_at))).all()
    return [serialize_trip(trip) for trip in trips]
