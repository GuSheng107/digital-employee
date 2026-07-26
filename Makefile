.PHONY: help install install-agent install-gateway install-frontend \
	dev dev-agent dev-gateway dev-frontend \
	infra-up infra-down infra-status build build-frontend \
	test-agent lint-gateway lint-frontend check clean

PYTHON ?= python
NPM ?= npm
UV ?= $(PYTHON) -m uv

ifeq ($(OS),Windows_NT)
AGENT_PYTHON := backend-agent/.venv/Scripts/python.exe
else
AGENT_PYTHON := backend-agent/.venv/bin/python
endif

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Development

dev: infra-up ## Start local infrastructure and print service commands
	@echo "Infrastructure is running. Start app services in separate terminals:"
	@echo "  make dev-agent"
	@echo "  make dev-gateway"
	@echo "  make dev-frontend"

dev-agent: ## Start backend-agent on port 8765
	$(AGENT_PYTHON) backend-agent/main.py --project-root backend-agent

dev-gateway: ## Start backend-gateway on port 8864
	cd backend-gateway && $(UV) run python -m src.main

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

install: install-agent install-gateway install-frontend ## Install all dependencies

install-agent: ## Create backend-agent virtualenv and install runtime/test dependencies
	$(PYTHON) -m venv backend-agent/.venv
	$(AGENT_PYTHON) -m pip install -e backend-agent pytest

install-gateway: ## Install backend-gateway dependencies with uv
	cd backend-gateway && $(UV) sync

install-frontend: ## Install the React frontend dependencies
	cd frontend && $(NPM) ci

# Build

build: build-frontend ## Build the frontend

build-frontend: ## Build the React frontend
	cd frontend && $(NPM) run build

# Verification

test-agent: ## Run backend-agent tests
	$(AGENT_PYTHON) -m pytest backend-agent/tests

lint-gateway: ## Run ruff against backend-gateway
	cd backend-gateway && $(UV) run ruff check src

lint-frontend: ## Run ESLint against the React frontend
	cd frontend && $(NPM) run lint

check: test-agent lint-gateway lint-frontend build-frontend ## Run repository checks available today

# Cleanup

clean: ## Remove generated caches and frontend build output
	$(PYTHON) scripts/clean-pycache.py
	$(PYTHON) -c "import shutil; [shutil.rmtree(path, ignore_errors=True) for path in ('backend-agent/.pytest_cache', 'backend-gateway/.pytest_cache', 'frontend/dist')]"
