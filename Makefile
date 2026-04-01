.PHONY: api-build api-up api-down api-logs api-dev api-shell api-seed-cities api-seed-all ios android start stop build clean dev dev-start dev-stop dev-build

api-build:
	docker compose -f api/docker-compose.yml build

api-up:
	docker compose -f api/docker-compose.yml up -d

api-down:
	docker compose -f api/docker-compose.yml down

api-logs:
	docker compose -f api/docker-compose.yml logs -f api

api-dev:
	docker compose -f api/docker-compose.yml up --build

api-shell:
	docker compose -f api/docker-compose.yml exec api sh

api-seed-cities:
	docker compose -f api/docker-compose.yml exec api python -m app.seed_ibge

api-seed-all:
	docker compose -f api/docker-compose.yml exec api python -m app.seed_all

ios:
	cd mobile && npm install && npm run ios

android:
	cd mobile && npm install && npm run android

start:
	docker-compose -f backend/docker-compose.yaml up -d

stop:
	docker-compose -f backend/docker-compose.yaml down

build:
	docker-compose -f backend/docker-compose.yaml build

clean:
	docker-compose -f backend/docker--compose.yaml down -v --rmi all
	docker system prune -a -f

dev: dev-start

dev-start:
	docker-compose -f backend/docker-compose.dev.yaml up

dev-stop:
	docker-compose -f backend/docker-compose.dev.yaml down

dev-build:
	docker-compose -f backend/docker-compose.dev.yaml build
