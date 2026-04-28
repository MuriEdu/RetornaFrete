from app.database import SessionLocal
from app.seed import seed_vehicle_types
from app.seed_ibge import seed_ibge_municipios


def seed_all() -> None:
    with SessionLocal() as db:
        seed_vehicle_types(db)

    total_cities = seed_ibge_municipios()
    print(f"Seed complete. IBGE municipios upserted: {total_cities}")


if __name__ == "__main__":
    seed_all()
