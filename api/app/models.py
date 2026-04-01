import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def uuid_column():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Role(str, enum.Enum):
    SHIPPER = "SHIPPER"
    TRUCKER = "TRUCKER"


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"


class ProposalStatus(str, enum.Enum):
    PENDING = "PENDING"
    UNDER_NEGOTIATION = "UNDER_NEGOTIATION"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


class TripStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    MATCHED = "MATCHED"
    CANCELED = "CANCELED"
    COMPLETED = "COMPLETED"


class CargoStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    MATCHED = "MATCHED"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_column()
    fullname: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False)
    account_status: Mapped[AccountStatus] = mapped_column(Enum(AccountStatus), default=AccountStatus.ACTIVE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    trips: Mapped[list["Trip"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    cargos: Mapped[list["Cargo"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship()


class VehicleType(Base):
    __tablename__ = "vehicle_types"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)


class Municipio(Base):
    __tablename__ = "municipios"

    ibge_code: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    nm_mun: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    sigla_uf: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"), nullable=False)
    brand: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    license_plate: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="vehicles")
    type: Mapped["VehicleType"] = relationship()


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    origin_name: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_lat: Mapped[float] = mapped_column(nullable=False)
    origin_lon: Mapped[float] = mapped_column(nullable=False)
    dest_lat: Mapped[float] = mapped_column(nullable=False)
    dest_lon: Mapped[float] = mapped_column(nullable=False)
    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_km: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[TripStatus] = mapped_column(Enum(TripStatus), default=TripStatus.AVAILABLE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="trips")
    vehicle: Mapped["Vehicle"] = relationship()


class Cargo(Base):
    __tablename__ = "cargos"

    id: Mapped[uuid.UUID] = uuid_column()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    required_vehicle_type_id: Mapped[int] = mapped_column(ForeignKey("vehicle_types.id"), nullable=False)
    origin_name: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_name: Mapped[str] = mapped_column(String(255), nullable=False)
    origin_lat: Mapped[float] = mapped_column(nullable=False)
    origin_lon: Mapped[float] = mapped_column(nullable=False)
    dest_lat: Mapped[float] = mapped_column(nullable=False)
    dest_lon: Mapped[float] = mapped_column(nullable=False)
    trip_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    weight_kg: Mapped[float] = mapped_column(nullable=False)
    is_date_flexible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[CargoStatus] = mapped_column(Enum(CargoStatus), default=CargoStatus.ACTIVE, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="cargos")
    required_vehicle_type: Mapped["VehicleType"] = relationship()


class Proposal(Base):
    __tablename__ = "proposals"

    id: Mapped[uuid.UUID] = uuid_column()
    cargo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cargos.id"), nullable=False, index=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id"), nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    current_bidder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    initial_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    current_bid: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(Enum(ProposalStatus), default=ProposalStatus.PENDING, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    cargo: Mapped["Cargo"] = relationship()
    trip: Mapped["Trip"] = relationship()
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    current_bidder: Mapped["User"] = relationship(foreign_keys=[current_bidder_id])
    bids: Mapped[list["ProposalBid"]] = relationship(back_populates="proposal", cascade="all, delete-orphan", order_by="ProposalBid.created_at")


class ProposalBid(Base):
    __tablename__ = "proposal_bids"

    id: Mapped[uuid.UUID] = uuid_column()
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proposals.id"), nullable=False, index=True)
    bidder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    proposal: Mapped["Proposal"] = relationship(back_populates="bids")
    bidder: Mapped["User"] = relationship()
