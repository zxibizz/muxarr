# Run from the repository root. `make help` lists the targets.

BACKEND  := services/backend
FRONTEND := services/frontend

.DEFAULT_GOAL := help
.PHONY: help setup dev check lint typecheck test test-backend test-frontend build \
        gen-api shims image

help: ## List the targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install backend and frontend dependencies
	cd $(BACKEND) && uv sync
	cd $(FRONTEND) && npm ci

dev: ## Run API, worker and Vite with hot reload in the dev container
	docker compose -f compose.dev.yaml up --build

check: lint typecheck test ## Everything CI runs on the code
	python3 scripts/build_shims.py --check
	python3 .github/scripts/check_version.py

lint: ## ruff, ruff format and eslint
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
	cd $(FRONTEND) && npm run lint

typecheck: ## mypy (strict) and tsc
	cd $(BACKEND) && uv run python -m mypy
	cd $(FRONTEND) && npx tsc --noEmit

test: test-backend test-frontend ## Both test suites

test-backend: ## pytest; mux tests skip without mkvtoolnix/ffmpeg on PATH
	cd $(BACKEND) && uv run pytest -q

test-frontend: ## vitest
	cd $(FRONTEND) && npm run test

build: ## Production build of the UI
	cd $(FRONTEND) && npm run build

gen-api: ## Regenerate the UI's API types from the backend schema
	cd $(BACKEND) && uv run python -m src.cli openapi --out ../frontend/openapi.json
	cd $(FRONTEND) && npm run gen:api

shims: ## Render the *arr shims from scripts/src
	python3 scripts/build_shims.py

image: ## Build the production image as muxarr:local
	docker build -f Dockerfile.all-in-one -t muxarr:local .
