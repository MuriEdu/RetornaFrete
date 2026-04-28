.PHONY: api-build api-up api-up-no-cache api-down api-logs api-dev api-shell api-seed-cities api-seed-all api-clean-db api-migrate api-revision mobile-install ios android

api-build:
	docker compose -f api/docker-compose.yml build

api-up:
	docker compose -f api/docker-compose.yml up -d

api-up-no-cache:
	docker compose -f api/docker-compose.yml build --no-cache
	docker compose -f api/docker-compose.yml up -d

api-down:
	docker compose -f api/docker-compose.yml down

api-clean-db:
	docker compose -f api/docker-compose.yml down -v

api-logs:
	docker compose -f api/docker-compose.yml logs -f api

api-dev:
	docker compose -f api/docker-compose.yml up --build

api-migrate:
	docker compose -f api/docker-compose.yml run --rm --build api sh -c "alembic -c alembic.ini upgrade head"

api-revision:
	docker compose -f api/docker-compose.yml run --rm --build api sh -c "alembic -c alembic.ini revision --autogenerate -m 'update schema'"

api-shell:
	docker compose -f api/docker-compose.yml exec api sh

api-seed-cities:
	docker compose -f api/docker-compose.yml exec api python -m app.seed_ibge

api-seed-all:
	docker compose -f api/docker-compose.yml exec api python -m app.seed_all

mobile-install:
	cd mobile && npm install

ios:
	cd mobile && npm run ios

android:
	cd mobile && npm run android
