.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

openapi: ## Generate pygeoapi OpenAPI spec
	@set -a && . ./.env && set +a && \
		uv run python -c "from climate_api.publications.services import ensure_pygeoapi_base_config; ensure_pygeoapi_base_config()"

run: openapi ## Start the app with uvicorn
	set -a && . ./.env && set +a && \
		uv run uvicorn climate_api.main:app --reload --reload-include "*.yaml" --reload-include "*.yml" --port 8000
