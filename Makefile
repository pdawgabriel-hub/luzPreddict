# Usa el Python del venv si existe; si no, el del sistema
PYTHON ?= $(if $(wildcard venv/bin/python),venv/bin/python,python3)

.DEFAULT_GOAL := help
.PHONY: help install lint format test migrate backfill pipeline backtest train predict api web web-build dev clean

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## Instala las dependencias (Python y web) y los hooks de pre-commit
	$(PYTHON) -m pip install -r requirements-dev.txt
	npm --prefix frontend ci
	$(PYTHON) -m pre_commit install

lint: ## Revisa el código: ruff en Python, oxlint y tipos en la web (sin modificarlo)
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck

format: ## Corrige y formatea el código con ruff
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test: ## Ejecuta los tests
	$(PYTHON) -m pytest

migrate: ## Aplica las migraciones pendientes a la base de datos de DATABASE_URL
	$(PYTHON) -m alembic upgrade head

backfill: ## Descarga de REE el PVPC y la generación que faltan y los guarda en la base de datos
	$(PYTHON) -m src.pipeline backfill

pipeline: ## Tarea diaria: ingesta, previsión del siguiente día y error diario
	$(PYTHON) -m src.pipeline daily

backtest: ## Compara LightGBM con las referencias en el periodo de prueba (desde 2025)
	$(PYTHON) -m src.models.train backtest

train: ## Entrena LightGBM con el histórico de la base de datos y lo guarda en ella
	$(PYTHON) -m src.pipeline train

predict: ## Muestra la previsión del primer día sin precio publicado (sin guardarla)
	$(PYTHON) -m src.pipeline predict

api: ## Arranca la API en http://localhost:8000 (documentación en /docs)
	$(PYTHON) -m uvicorn src.api.main:app --reload --port 8000 --no-access-log

web: ## Arranca la web en http://localhost:5173 (reenvía /api, /v1 y /health a la API)
	npm --prefix frontend run dev

web-build: ## Compila la web para producción en frontend/dist
	npm --prefix frontend run build

dev: ## Arranca la API y la web a la vez (Ctrl+C para las dos)
	$(MAKE) -j2 api web

clean: ## Borra cachés de Python, pytest y ruff y la web compilada
	find . -path ./venv -prune -o -path ./frontend/node_modules -prune -o -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache frontend/dist
