from collections.abc import Iterable

import httpx
from sqlalchemy import text

from app.database import Base, SessionLocal, engine

IBGE_MUNICIPIOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios"
IBGE_ESTADOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados"
IBGE_MALHAS_ESTADO_URL = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"


def _chunks(items: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _flatten_points(coordinates) -> Iterable[tuple[float, float]]:
    if not isinstance(coordinates, list) or not coordinates:
        return

    first = coordinates[0]
    if (
        isinstance(first, list)
        and len(first) >= 2
        and isinstance(first[0], (int, float))
        and isinstance(first[1], (int, float))
    ):
        for pair in coordinates:
            if isinstance(pair, list) and len(pair) >= 2:
                yield float(pair[0]), float(pair[1])
        return

    for child in coordinates:
        yield from _flatten_points(child)


def _centroid_from_geometry(geometry: dict) -> tuple[float | None, float | None]:
    coordinates = geometry.get("coordinates")
    points = list(_flatten_points(coordinates))
    if not points:
        return None, None

    min_lon = min(point[0] for point in points)
    max_lon = max(point[0] for point in points)
    min_lat = min(point[1] for point in points)
    max_lat = max(point[1] for point in points)

    lon = (min_lon + max_lon) / 2.0
    lat = (min_lat + max_lat) / 2.0
    return lat, lon


def _fetch_municipios_base() -> list[dict]:
    with httpx.Client(timeout=90.0) as client:
        response = client.get(IBGE_MUNICIPIOS_URL)
        response.raise_for_status()
        payload = response.json()

    municipios: list[dict] = []
    for item in payload:
        microrregiao = item.get("microrregiao") or {}
        regiao_imediata = item.get("regiao-imediata") or {}
        uf = (
            microrregiao.get("mesorregiao", {}).get("UF", {}).get("sigla")
            or regiao_imediata.get("regiao-intermediaria", {}).get("UF", {}).get("sigla")
        )
        name = item.get("nome")
        ibge_code = item.get("id")
        if not uf or not name or ibge_code is None:
            continue
        municipios.append(
            {
                "ibge_code": int(ibge_code),
                "nm_mun": str(name).strip(),
                "sigla_uf": str(uf).strip().upper(),
            }
        )
    return municipios


def _fetch_municipio_centroids() -> dict[int, tuple[float | None, float | None]]:
    with httpx.Client(timeout=120.0) as client:
        states_response = client.get(IBGE_ESTADOS_URL)
        states_response.raise_for_status()
        states = states_response.json()

        centroids: dict[int, tuple[float | None, float | None]] = {}
        for state in states:
            uf = str(state.get("sigla", "")).strip().upper()
            if not uf:
                continue

            mesh_response = client.get(
                IBGE_MALHAS_ESTADO_URL.format(uf=uf),
                params={
                    "intrarregiao": "municipio",
                    "formato": "application/vnd.geo+json",
                    "qualidade": "minima",
                },
            )
            mesh_response.raise_for_status()
            features = mesh_response.json().get("features", [])
            for feature in features:
                ibge_code_raw = feature.get("properties", {}).get("codarea")
                geometry = feature.get("geometry") or {}
                if not ibge_code_raw:
                    continue
                try:
                    ibge_code = int(ibge_code_raw)
                except (TypeError, ValueError):
                    continue
                centroids[ibge_code] = _centroid_from_geometry(geometry)
    return centroids


def _ensure_columns_exist() -> None:
    with SessionLocal() as db:
        db.execute(text("ALTER TABLE municipios ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION"))
        db.execute(text("ALTER TABLE municipios ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION"))
        db.commit()


def seed_ibge_municipios() -> int:
    Base.metadata.create_all(bind=engine)
    _ensure_columns_exist()

    municipios = _fetch_municipios_base()
    centroids = _fetch_municipio_centroids()

    for municipio in municipios:
        lat, lon = centroids.get(municipio["ibge_code"], (None, None))
        municipio["latitude"] = lat
        municipio["longitude"] = lon

    if not municipios:
        return 0

    upsert_sql = text(
        """
        INSERT INTO municipios (ibge_code, nm_mun, sigla_uf, latitude, longitude)
        VALUES (:ibge_code, :nm_mun, :sigla_uf, :latitude, :longitude)
        ON CONFLICT (ibge_code) DO UPDATE SET
            nm_mun = EXCLUDED.nm_mun,
            sigla_uf = EXCLUDED.sigla_uf,
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude
        """
    )

    with SessionLocal() as db:
        for batch in _chunks(municipios, 300):
            db.execute(upsert_sql, batch)
        db.commit()

    return len(municipios)


if __name__ == "__main__":
    total = seed_ibge_municipios()
    print(f"IBGE municipios upserted: {total}")
