.PHONY: help dev dev-agent dev-gateway install install-agent build build-frontend clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ========================
# Development
# ========================

dev: ## Start all services (docker)
	docker compose up --build

VENV := backend-agent/.venv
PYTHON := $(VENV)/Scripts/python.exe

dev-agent: ## Start backend-agent only
	cd backend-agent && $(PYTHON) main.py

dev-gateway: ## Start backend-gateway only
	cd backend-gateway/cmd/cc-connect && go run .

# ========================
# Install
# ========================

install: install-agent ## Install all dependencies

install-agent: ## Install Python dependencies in .venv
	cd backend-agent && python -m venv .venv && $(PYTHON) -m pip install -e ".[dev]"

# ========================
# Build
# ========================

build: build-frontend ## Build all

build-frontend: ## Build frontend static files
	cd frontend && npm install && npm run build

# ========================
# Clean
# ========================

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .venv -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist
