from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VehicleType


DEFAULT_VEHICLE_TYPES = [
    "Baú",
    "Carreta",
    "Graneleiro",
    "Sider",
    "Truck",
    "Toco",
]


def seed_vehicle_types(db: Session) -> None:
    existing_names = set(db.scalars(select(VehicleType.name)).all())

    added = False
    for name in DEFAULT_VEHICLE_TYPES:
        if name in existing_names:
            continue
        db.add(VehicleType(name=name))
        added = True

    if added:
        db.commit()
