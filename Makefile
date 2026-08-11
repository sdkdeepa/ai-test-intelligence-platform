.PHONY: install backend frontend test test-cov lint test-frontend e2e build docker-up docker-down clean

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install -e ".[dev]"
	cd frontend && npm install

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

test:
	cd backend && .venv/bin/pytest

test-cov:
	cd backend && .venv/bin/pytest --cov=app --cov-report=term-missing --cov-report=html --cov-report=xml

lint:
	cd backend && .venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests && .venv/bin/mypy

test-frontend:
	cd frontend && npm run test

e2e:
	cd frontend && npm run e2e

build:
	cd frontend && npm run build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.coverage backend/coverage.xml backend/htmlcov \
		frontend/node_modules frontend/dist frontend/playwright-report frontend/test-results
