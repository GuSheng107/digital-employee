.PHONY: help install install-gateway install-data install-frontend \
	dev dev-gateway dev-data dev-frontend \
	infra-up infra-down infra-status build build-frontend \
	lint-gateway lint-frontend check clean

PYTHON ?= python
NPM ?= npm
UV ?= $(PYTHON) -m uv

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development

dev: infra-up ## Start local infrastructure and print service commands
	@echo "Infrastructure is running. Start app services in separate terminals:"
	@echo "  make dev-gateway"
	@echo "  make dev-frontend"

dev-gateway: ## Start backend-gateway on port 8864
	cd backend-gateway && $(UV) run uvicorn src.main:app --host 0.0.0.0 --port 8864

dev-data: ## Start backend-data on port 8010
	cd backend-data/backend && $(UV) run uvicorn app.main:app --host 0.0.0.0 --port 8010

dev-frontend: ## Start the React frontend development server
	cd frontend && $(NPM) run dev

# Infrastructure

infra-up: ## Start RabbitMQ and MinIO
	docker compose up -d

infra-down: ## Stop RabbitMQ and MinIO
	docker compose down

infra-status: ## Show infrastructure status
	docker compose ps

# Installation

install: install-gateway install-data install-frontend ## Install all dependencies

install-gateway: ## Install backend-gateway dependencies with uv
	cd backend-gateway && $(UV) sync

install-data: ## Install backend-data dependencies with uv
	cd backend-data/backend && $(UV) sync

install-frontend: ## Install the React frontend dependencies
	cd frontend && $(NPM) ci

# Build

build: build-frontend ## Build the frontend

build-frontend: ## Build the React frontend
	cd frontend && $(NPM) run build

# Verification

lint-gateway: ## Run ruff against backend-gateway
	cd backend-gateway && $(UV) run ruff check src

lint-frontend: ## Run ESLint against the React frontend
	cd frontend && $(NPM) run lint

check: lint-gateway lint-frontend build-frontend ## Run repository checks available today

# Cleanup

clean: ## Remove generated caches and frontend build output
	$(PYTHON) scripts/clean-pycache.py
	$(PYTHON) -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('backend-gateway/.pytest_cache', 'frontend/dist')]"  # noqa: E501
