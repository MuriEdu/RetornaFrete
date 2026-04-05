import math
import unicodedata

import httpx
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import SessionLocal
from app.schemas import RouteCalculationResponse, RouteCity


def _distance_km(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    radius = 6371.0
    lat1, lon1 = map(math.radians, point_a)
    lat2, lon2 = map(math.radians, point_b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _route_distance_km(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(_distance_km(previous, current) for previous, current in zip(points, points[1:]))


def _sample_route_points(points: list[tuple[float, float]], step_km: float, max_points: int) -> list[tuple[float, float]]:
    if not points:
        return []

    sampled = [points[0]]
    carried = 0.0
    for previous, current in zip(points, points[1:]):
        carried += _distance_km(previous, current)
        if carried >= step_km:
            sampled.append(current)
            carried = 0.0

    if sampled[-1] != points[-1]:
        sampled.append(points[-1])

    if len(sampled) > max_points:
        stride = max(1, len(sampled) // max_points)
        sampled = sampled[::stride]
        if sampled[-1] != points[-1]:
            sampled.append(points[-1])

    return sampled


def _normalize_city_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _split_city_name(value: str | None, default_name: str) -> tuple[str, str]:
    if not value:
        return default_name, "BR"
    normalized = value.strip()
    if " - " in normalized:
        city, state = normalized.rsplit(" - ", 1)
        return city.strip(), state.strip().upper()
    if "/" in normalized:
        city, state = normalized.rsplit("/", 1)
        return city.strip(), state.strip().upper()
    return normalized, "BR"


def _fallback_cities(
    origin_name: str | None,
    dest_name: str | None,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> list[RouteCity]:
    origin_city, origin_state = _split_city_name(origin_name, "Origem")
    dest_city, dest_state = _split_city_name(dest_name, "Destino")
    return [
        RouteCity(name=origin_city, state=origin_state, latitude=origin_lat, longitude=origin_lon),
        RouteCity(name=dest_city, state=dest_state, latitude=dest_lat, longitude=dest_lon),
    ]


def _merge_endpoints(
    cities: list[RouteCity],
    origin_name: str | None,
    dest_name: str | None,
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> list[RouteCity]:
    origin_city, origin_state = _split_city_name(origin_name, "Origem")
    dest_city, dest_state = _split_city_name(dest_name, "Destino")

    if not cities:
        return _fallback_cities(origin_name, dest_name, origin_lat, origin_lon, dest_lat, dest_lon)

    if _normalize_city_text(cities[0].name) != _normalize_city_text(origin_city):
        cities.insert(0, RouteCity(name=origin_city, state=origin_state, latitude=origin_lat, longitude=origin_lon))
    else:
        cities[0].name = origin_city
        cities[0].state = origin_state

    if _normalize_city_text(cities[-1].name) != _normalize_city_text(dest_city):
        cities.append(RouteCity(name=dest_city, state=dest_state, latitude=dest_lat, longitude=dest_lon))
    else:
        cities[-1].name = dest_city
        cities[-1].state = dest_state

    unique: list[RouteCity] = []
    seen: set[tuple[str, str]] = set()
    for city in cities:
        key = (_normalize_city_text(city.name), city.state.strip().upper())
        if key in seen:
            continue
        seen.add(key)
        unique.append(city)
    return unique


def _load_cities_with_centroid() -> list[RouteCity]:
    query = text(
        """
        SELECT nm_mun, sigla_uf, latitude, longitude
        FROM municipios
        WHERE latitude IS NOT NULL
          AND longitude IS NOT NULL
        """
    )
    try:
        with SessionLocal() as db:
            rows = db.execute(query).mappings().all()
    except SQLAlchemyError:
        return []

    return [
        RouteCity(
            name=str(row["nm_mun"]).strip(),
            state=str(row["sigla_uf"]).strip().upper(),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        )
        for row in rows
    ]


async def _forward_geocode_mapbox(client: httpx.AsyncClient, city_name: str) -> tuple[float, float]:
    try:
        response = await client.get(
            "https://api.mapbox.com/search/geocode/v6/forward",
            params={
                "q": city_name,
                "access_token": settings.mapbox_token,
                "country": "br",
                "language": "pt",
                "types": "place,locality,district,region",
                "limit": 1,
            },
            timeout=20.0,
        )
        response.raise_for_status()
        feature = (response.json().get("features") or [None])[0]
        coordinates = feature.get("geometry", {}).get("coordinates") if feature else None
        if not coordinates or len(coordinates) < 2:
            raise HTTPException(status_code=404, detail=f"City not found: {city_name}")
        return float(coordinates[1]), float(coordinates[0])
    except httpx.HTTPError:
        return await _forward_geocode_nominatim(client, city_name)


async def _forward_geocode_nominatim(client: httpx.AsyncClient, city_name: str) -> tuple[float, float]:
    response = await client.get(
        settings.nominatim_search_url,
        params={"q": city_name, "format": "jsonv2", "limit": 1, "countrycodes": "br"},
        headers={"User-Agent": settings.nominatim_user_agent},
        timeout=20.0,
    )
    response.raise_for_status()
    results = response.json()
    if not results:
        raise HTTPException(status_code=404, detail=f"City not found: {city_name}")
    return float(results[0]["lat"]), float(results[0]["lon"])


async def _resolve_point(
    client: httpx.AsyncClient,
    city_name: str | None,
    lat: float | None,
    lon: float | None,
) -> tuple[float, float]:
    if lat is not None and lon is not None:
        return lat, lon
    if not city_name:
        raise HTTPException(status_code=400, detail="Origin and destination must include either coordinates or city names")
    if settings.mapbox_token:
        return await _forward_geocode_mapbox(client, city_name)
    return await _forward_geocode_nominatim(client, city_name)


async def _fetch_route_geometry(
    client: httpx.AsyncClient, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
) -> list[list[float]]:
    coordinates = f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    fallback_route = [[origin_lon, origin_lat], [dest_lon, dest_lat]]

    try:
        if settings.mapbox_token:
            response = await client.get(
                f"{settings.mapbox_directions_url}/{coordinates}",
                params={
                    "geometries": "geojson",
                    "overview": "full",
                    "access_token": settings.mapbox_token,
                },
                timeout=20.0,
            )
            response.raise_for_status()
            routes = response.json().get("routes", [])
        else:
            response = await client.get(
                f"{settings.osrm_directions_url}/{coordinates}",
                params={"geometries": "geojson", "overview": "full"},
                timeout=20.0,
            )
            response.raise_for_status()
            payload = response.json()
            routes = payload.get("routes", []) if payload.get("code") == "Ok" else []
    except httpx.HTTPError:
        return fallback_route

    if not routes:
        return fallback_route

    geometry = routes[0].get("geometry", {})
    route_coordinates = geometry.get("coordinates") or []
    return route_coordinates or fallback_route


def _find_cities_near_route(
    route_points: list[tuple[float, float]],
    candidate_cities: list[RouteCity],
) -> list[RouteCity]:
    if not route_points or not candidate_cities:
        return []

    total_km = _route_distance_km(route_points)
    if total_km <= 120:
        sample_step_km = 6.0
        corridor_km = 10.0
    elif total_km <= 350:
        sample_step_km = 10.0
        corridor_km = 14.0
    else:
        sample_step_km = 14.0
        corridor_km = 18.0

    sampled_points = _sample_route_points(route_points, step_km=sample_step_km, max_points=180)
    route_lats = [point[0] for point in sampled_points]
    route_lons = [point[1] for point in sampled_points]
    min_lat, max_lat = min(route_lats), max(route_lats)
    min_lon, max_lon = min(route_lons), max(route_lons)
    margin_deg = 0.35

    ranked: list[tuple[int, RouteCity]] = []
    for city in candidate_cities:
        if city.latitude is None or city.longitude is None:
            continue

        if city.latitude < min_lat - margin_deg or city.latitude > max_lat + margin_deg:
            continue
        if city.longitude < min_lon - margin_deg or city.longitude > max_lon + margin_deg:
            continue

        best_distance = float("inf")
        best_index = 0
        city_point = (city.latitude, city.longitude)
        for idx, route_point in enumerate(sampled_points):
            distance = _distance_km(city_point, route_point)
            if distance < best_distance:
                best_distance = distance
                best_index = idx

        if best_distance <= corridor_km:
            ranked.append((best_index, city))

    ranked.sort(key=lambda item: item[0])
    unique: list[RouteCity] = []
    seen: set[tuple[str, str]] = set()
    last_kept_city: RouteCity | None = None
    for _, city in ranked:
        key = (_normalize_city_text(city.name), city.state.upper())
        if key in seen:
            continue
        if last_kept_city is not None and last_kept_city.latitude is not None and last_kept_city.longitude is not None:
            if city.latitude is not None and city.longitude is not None:
                if _distance_km((last_kept_city.latitude, last_kept_city.longitude), (city.latitude, city.longitude)) < 18.0:
                    continue
        seen.add(key)
        unique.append(city)
        last_kept_city = city
    return unique


async def calculate_route(
    origin_name: str | None,
    dest_name: str | None,
    origin_lat: float | None,
    origin_lon: float | None,
    dest_lat: float | None,
    dest_lon: float | None,
) -> RouteCalculationResponse:
    async with httpx.AsyncClient() as client:
        resolved_origin_lat, resolved_origin_lon = await _resolve_point(client, origin_name, origin_lat, origin_lon)
        resolved_dest_lat, resolved_dest_lon = await _resolve_point(client, dest_name, dest_lat, dest_lon)
        route_coordinates = await _fetch_route_geometry(
            client,
            resolved_origin_lat,
            resolved_origin_lon,
            resolved_dest_lat,
            resolved_dest_lon,
        )

    route_points = [(point[1], point[0]) for point in route_coordinates if len(point) >= 2]
    candidate_cities = _load_cities_with_centroid()
    if candidate_cities:
        cities = _find_cities_near_route(route_points, candidate_cities)
        cities = _merge_endpoints(
            cities,
            origin_name,
            dest_name,
            resolved_origin_lat,
            resolved_origin_lon,
            resolved_dest_lat,
            resolved_dest_lon,
        )
    else:
        cities = _fallback_cities(
            origin_name,
            dest_name,
            resolved_origin_lat,
            resolved_origin_lon,
            resolved_dest_lat,
            resolved_dest_lon,
        )

    return RouteCalculationResponse(
        status="success",
        count=len(cities),
        cities=cities,
        originLat=resolved_origin_lat,
        originLon=resolved_origin_lon,
        destLat=resolved_dest_lat,
        destLon=resolved_dest_lon,
        routeCoordinates=route_coordinates,
    )
