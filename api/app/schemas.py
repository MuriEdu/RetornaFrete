import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import AccountStatus, CargoStatus, FreightPaymentStatus, ProposalStatus, Role, TripStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class CreateUserRequest(BaseModel):
    fullname: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    refreshToken: str


class UserBasicResponse(BaseModel):
    id: uuid.UUID
    fullname: str
    email: EmailStr
    roles: list[Role]
    accountStatus: AccountStatus


class VehicleTypeResponse(ORMModel):
    id: int
    name: str


class VehicleCreateRequest(BaseModel):
    brand: str
    model: str
    licensePlate: str
    typeId: int


class VehicleResponse(BaseModel):
    id: uuid.UUID
    brand: str
    model: str
    licensePlate: str
    typeName: str
    typeId: int


class TripCreateRequest(BaseModel):
    originCity: str
    destCity: str
    originLat: float
    originLon: float
    destLat: float
    destLon: float
    tripDate: date
    pricePerKm: Decimal
    vehicleId: uuid.UUID

    @field_validator("tripDate", mode="before")
    @classmethod
    def parse_trip_date(cls, value):
        if isinstance(value, date):
            return value
        if isinstance(value, str) and "/" in value:
            return datetime.strptime(value, "%d/%m/%Y").date()
        return value


class CargoCreateRequest(BaseModel):
    originCity: str
    destCity: str
    originLat: float
    originLon: float
    destLat: float
    destLon: float
    tripDate: date
    productName: str
    weightKg: float
    requiredVehicleType: int
    isDateFlexible: bool = False

    @field_validator("tripDate", mode="before")
    @classmethod
    def parse_trip_date(cls, value):
        if isinstance(value, date):
            return value
        if isinstance(value, str) and "/" in value:
            return datetime.strptime(value, "%d/%m/%Y").date()
        return value


class RouteRequest(BaseModel):
    originLat: float
    originLon: float
    destLat: float
    destLon: float
    originCityName: str | None = None
    destCityName: str | None = None


class RouteCity(BaseModel):
    name: str
    state: str
    latitude: float | None = None
    longitude: float | None = None


class RouteCalculationResponse(BaseModel):
    status: str
    count: int
    cities: list[RouteCity]


class VehicleNested(BaseModel):
    id: uuid.UUID
    brand: str
    model: str
    licensePlate: str
    typeName: str
    typeId: int


class VehicleTypeNested(BaseModel):
    id: int
    name: str


class TripResponse(BaseModel):
    id: uuid.UUID
    originName: str
    destinationName: str
    tripDate: date
    pricePerKm: float
    status: TripStatus
    vehicle: VehicleNested


class CargoResponse(BaseModel):
    id: uuid.UUID
    originName: str
    destinationName: str
    productName: str
    weightKg: float
    tripDate: date
    status: CargoStatus
    createdAt: datetime
    requiredVehicleType: VehicleTypeNested
    isDateFlexible: bool


class UserContextResponse(BaseModel):
    id: uuid.UUID
    fullname: str
    email: EmailStr
    roles: list[Role]
    accountStatus: AccountStatus
    activeTrip: TripResponse | None = None
    activeCargo: CargoResponse | None = None


class LoginResponse(BaseModel):
    accessToken: str
    refreshToken: str
    user: UserContextResponse


class MatchResponse(BaseModel):
    tripId: uuid.UUID
    truckerName: str
    vehicleInfo: str
    truckerRating: float
    pricePerKm: float
    cargoDistanceKm: float
    totalFreightPrice: float
    tripDate: str


class CreateProposalRequest(BaseModel):
    cargoId: uuid.UUID
    tripId: uuid.UUID
    initialPrice: Decimal


class ProposalActionRequest(BaseModel):
    action: Literal["ACCEPT", "REJECT"]


class NegotiateProposalRequest(BaseModel):
    newBid: Decimal


class BidHistoryResponse(BaseModel):
    id: uuid.UUID
    value: float
    bidderId: uuid.UUID
    bidderName: str
    createdAt: datetime


class ProposalPaymentSummaryResponse(BaseModel):
    amount: float
    status: FreightPaymentStatus
    provider: str
    providerStatus: str | None = None
    paidAt: datetime | None = None
    releasedAt: datetime | None = None
    deliveryCodeHint: str


class ProposalPaymentDetailsResponse(ProposalPaymentSummaryResponse):
    checkoutUrl: str | None = None
    sandboxCheckoutUrl: str | None = None
    deliveryCode: str | None = None
    lastError: str | None = None


class ConfirmDeliveryCodeRequest(BaseModel):
    deliveryCode: str = Field(min_length=4, max_length=8)


class ProposalResponse(BaseModel):
    id: uuid.UUID
    cargoId: uuid.UUID
    tripId: uuid.UUID
    initialValue: float
    currentBid: float
    currentBidderId: uuid.UUID
    createdAt: datetime
    status: ProposalStatus
    freightDate: date
    originCity: str
    destCity: str
    distanceKm: str
    productName: str
    weightKg: float
    tripDate: date
    bidHistory: list[BidHistoryResponse]
    payment: ProposalPaymentSummaryResponse | None = None
