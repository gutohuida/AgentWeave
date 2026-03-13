# AgentWeave Hub — convenience targets
# Run from the hub/ directory

.PHONY: help install dev build docker-build docker-up docker-down test lint

help:
	@echo "AgentWeave Hub"
	@echo ""
	@echo "  make install        Install Python deps (editable) + UI npm deps"
	@echo "  make dev            Start Hub API server (uvicorn, port 8000)"
	@echo "  make ui-dev         Start UI dev server (vite, port 5173)"
	@echo "  make ui-build       Build React UI into ui/dist/"
	@echo "  make docker-build   Build Docker image from source (multi-stage)"
	@echo "  make docker-up      Start Hub via Docker Compose (production image)"
	@echo "  make docker-down    Stop Docker Compose services"
	@echo "  make test           Run Python test suite"
	@echo "  make lint           Run ruff + mypy on hub/ source"

install:
	pip install -e ".[dev]"
	cd ui && npm install

dev:
	alembic upgrade head
	uvicorn hub.main:app --host 0.0.0.0 --port 8000 --reload

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

docker-build:
	docker build . -t agentweave-hub:latest

docker-up:
	docker build . -t agentweave-hub:latest && docker compose up -d

docker-down:
	docker compose down

test:
	pytest

lint:
	ruff check hub/
	mypy hub/
