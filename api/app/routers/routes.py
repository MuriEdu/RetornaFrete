from fastapi import APIRouter

from app.schemas import RouteCalculationResponse, RouteRequest
from app.services.routes import calculate_route

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/calculate", response_model=RouteCalculationResponse)
async def calculate_route_endpoint(payload: RouteRequest) -> RouteCalculationResponse:
    return await calculate_route(
        payload.originCityName,
        payload.destCityName,
        payload.originLat,
        payload.originLon,
        payload.destLat,
        payload.destLon,
    )
