import math
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import Cargo, CargoStatus, Trip, TripStatus, User

router = APIRouter(prefix="/api/matches", tags=["matches"])


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def is_trip_date_compatible(cargo_date: date, trip_date: date, is_date_flexible: bool) -> bool:
    if is_date_flexible:
        return abs((trip_date - cargo_date).days) <= 2
    return trip_date == cargo_date


@router.get("/cargo/{cargo_id}")
def get_matches(
    cargo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cargo = db.scalar(select(Cargo).where(Cargo.id == cargo_id, Cargo.user_id == current_user.id))
    if not cargo:
        raise HTTPException(status_code=404, detail="Cargo not found")

    trips = db.scalars(
        select(Trip).where(
            Trip.status == TripStatus.AVAILABLE,
            Trip.user_id != current_user.id,
        )
    ).all()

    distance = haversine_km(cargo.origin_lat, cargo.origin_lon, cargo.dest_lat, cargo.dest_lon)
    matches = []
    for trip in trips:
        if trip.vehicle.type_id != cargo.required_vehicle_type_id:
            continue
        if not is_trip_date_compatible(cargo.trip_date, trip.trip_date, cargo.is_date_flexible):
            continue
        total = Decimal(trip.price_per_km) * Decimal(str(distance))
        matches.append(
            {
                "tripId": trip.id,
                "truckerName": trip.user.fullname,
                "vehicleInfo": f"{trip.vehicle.brand} {trip.vehicle.model} - {trip.vehicle.license_plate}",
                "truckerRating": 4.8,
                "pricePerKm": float(trip.price_per_km),
                "cargoDistanceKm": round(distance, 2),
                "totalFreightPrice": float(total.quantize(Decimal("0.01"))),
                "tripDate": str(trip.trip_date),
            }
        )

    if not matches:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return matches
