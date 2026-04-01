from fastapi import APIRouter

from app.schemas import RouteCalculationResponse, RouteCity, RouteRequest
from app.services.routes import get_cities_along_route

router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/calculate", response_model=RouteCalculationResponse)
async def calculate_route(payload: RouteRequest) -> RouteCalculationResponse:
    cities: list[RouteCity] = await get_cities_along_route(
        payload.originLat,
        payload.originLon,
        payload.destLat,
        payload.destLon,
        payload.originCityName,
        payload.destCityName,
    )
    return RouteCalculationResponse(status="success", count=len(cities), cities=cities)
