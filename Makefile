.PHONY: help dev dev-agent dev-gateway dev-frontend install install-agent install-frontend build build-frontend clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ========================
# Development
# ========================

dev: ## Start all services
	docker compose up --build

dev-agent: ## Start backend-agent only
	cd backend-agent && python main.py

dev-gateway: ## Start backend-gateway only
	cd backend-gateway/cmd/cc-connect && go run .

dev-frontend: ## Start frontend dev server
	cd frontend && npm run dev

# ========================
# Install
# ========================

install: install-agent install-frontend ## Install all dependencies

install-agent: ## Install Python dependencies
	cd backend-agent && pip install -e ".[dev]"

install-frontend: ## Install frontend dependencies
	cd frontend && npm install

# ========================
# Build
# ========================

build: build-frontend ## Build all

build-frontend: ## Build frontend for production
	cd frontend && npm run build

# ========================
# Clean
# ========================

clean: ## Remove build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name node_modules -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf frontend/dist
