# Usa el Python del venv si existe; si no, el del sistema
PYTHON ?= $(if $(wildcard venv/bin/python),venv/bin/python,python3)

.DEFAULT_GOAL := help
.PHONY: help install lint format test clean

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Instala las dependencias de desarrollo y los hooks de pre-commit
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m pre_commit install

lint: ## Revisa el código con ruff (sin modificarlo)
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format: ## Corrige y formatea el código con ruff
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test: ## Ejecuta los tests
	$(PYTHON) -m pytest

clean: ## Borra cachés de Python, pytest y ruff
	find . -path ./venv -prune -o -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
