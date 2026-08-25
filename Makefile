up:        ## start local infra services
	docker compose -f infra/docker-compose.yml up -d
down:      ## stop local infra services
	docker compose -f infra/docker-compose.yml down
logs:      ## tail backend logs
	docker compose -f infra/docker-compose.yml logs -f backend
install:   ## install backend + frontend deps
	cd backend && pip install -r requirements.txt && cd ../frontend && npm ci
migrate:   ## apply db migrations
	cd backend && alembic upgrade head
revision:  ## create a new migration; usage: make revision m="message"
	cd backend && alembic revision --autogenerate -m "$(m)"
api:       ## run the backend dev server
	cd backend && uvicorn app.main:app --reload --port 8000
web:       ## run the frontend dev server
	cd frontend && npm run dev
worker:    ## run the rq worker
	cd backend && rq worker -u $$REDIS_URL copilot
test:      ## run backend + frontend test suites
	cd backend && pytest -q && cd ../frontend && npm run test -- --run
lint:      ## lint backend + frontend
	cd backend && ruff check . && cd ../frontend && npm run lint
openapi:   ## regenerate openapi.json and frontend types
	python scripts/gen_openapi.py && cd frontend && npm run gen:api
smoke:     ## run the smoke test harness
	./scripts/smoke.sh
seed:      ## seed the database with demo data
	cd backend && python ../scripts/seed.py
guard:     ## run the footprint guard
	./scripts/guard.sh
prod-up:   ## build and start the production stack
	docker compose -f infra/docker-compose.prod.yml up -d --build

.PHONY: up down logs install migrate revision api web worker test lint openapi smoke seed guard prod-up
