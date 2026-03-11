PYTHON ?= python3
BACKEND_DIR := backend
FRONTEND_DIR := frontend

.PHONY: backend-install frontend-install dev-backend dev-frontend test build-frontend docker-build

backend-install:
	cd $(BACKEND_DIR) && $(PYTHON) -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

frontend-install:
	cd $(FRONTEND_DIR) && npm install

dev-backend:
	cd $(BACKEND_DIR) && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd $(FRONTEND_DIR) && npm run dev

test:
	cd $(BACKEND_DIR) && . .venv/bin/activate && pytest

build-frontend:
	cd $(FRONTEND_DIR) && npm run build

docker-build:
	docker build -t get-putio:latest .

