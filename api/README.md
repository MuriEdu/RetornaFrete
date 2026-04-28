# FastAPI API

Novo backend em FastAPI para servir o app mobile.

## Launch checklist

Before launch, make sure these are set:

- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `JWT_REFRESH_SECRET_KEY`
- `CORS_ORIGINS`
- `MERCADO_PAGO_ACCESS_TOKEN`
- `MERCADO_PAGO_NOTIFICATION_URL`
- `MERCADO_PAGO_WEBHOOK_SECRET`
- `MERCADO_PAGO_SUCCESS_URL`
- `MERCADO_PAGO_PENDING_URL`
- `MERCADO_PAGO_FAILURE_URL`

## Subir com Docker

1. Copie `.env.example` para `.env`
2. Rode `make api-migrate`
3. Rode `make api-dev`

## Migrações

- `make api-migrate` aplica as migrações no banco configurado
- `make api-revision` cria uma nova revisão do Alembic

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
- `POST /api/proposals/{proposal_id}/payment/preference`
- `POST /api/proposals/{proposal_id}/payment/sync`
- `POST /api/proposals/{proposal_id}/payment/release`
- `POST /api/payments/mercado-pago/webhook`
