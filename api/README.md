# FastAPI API

Novo backend em FastAPI para servir o app mobile.

## Subir com Docker

1. Copie `.env.example` para `.env`
2. Rode `make api-dev`

## Endpoints principais

- `POST /users`
- `POST /users/login`
- `POST /users/refresh-token`
- `GET /users/me`
- `GET /api/vehicles`
- `GET /api/trips/my-trips`
- `GET /api/cargos/my-cargos`
- `GET /api/matches/cargo/{cargo_id}`
- `GET /api/proposals/my-offers`
- `GET /api/proposals/recived`
- `GET /api/notifications/subscribe`
