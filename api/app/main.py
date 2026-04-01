from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import cargos, matches, notifications, proposals, routes, trips, users, vehicles
from app.seed import seed_vehicle_types

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_vehicle_types(db)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(users.router)
app.include_router(vehicles.router)
app.include_router(trips.router)
app.include_router(cargos.router)
app.include_router(routes.router)
app.include_router(matches.router)
app.include_router(proposals.router)
app.include_router(notifications.router)
