.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install dependencies with uv
	uv sync

run: ## Start the app with uvicorn
	set -a && . ./.env && set +a && \
		uv run uvicorn climate_api.main:app --reload --reload-include "*.yaml" --reload-include "*.yml" --port 8000
