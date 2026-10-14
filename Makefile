# Usa el Python del venv si existe; si no, el del sistema
PYTHON ?= $(if $(wildcard venv/bin/python),venv/bin/python,python3)

.DEFAULT_GOAL := help
.PHONY: help install lint lint-py lint-web format test test-py test-web migrate backfill pipeline backtest train predict api api-types web web-mocks web-build web-coverage dev docker-up docker-seed docker-down docs docs-build clean

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

install: ## Instala las dependencias (Python y web) y los hooks de pre-commit
	$(PYTHON) -m pip install -r requirements-dev.txt
	npm --prefix frontend ci
	$(PYTHON) -m pre_commit install

lint: lint-py lint-web ## Revisa todo el código sin modificarlo (Python y web)

lint-py: ## Revisa el código Python con ruff
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

lint-web: ## Revisa la web: oxlint y tipos de TypeScript
	npm --prefix frontend run lint
	npm --prefix frontend run typecheck

format: ## Corrige y formatea el código con ruff
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m ruff format .

test: test-py test-web ## Ejecuta todos los tests (Python y web)

test-py: ## Tests de Python (pytest)
	$(PYTHON) -m pytest

test-web: ## Tests de la web (Vitest)
	npm --prefix frontend test

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

api-types: ## Regenera el esquema OpenAPI y los tipos de TypeScript de la web
	$(PYTHON) -m src.api.openapi frontend/src/api/openapi.json
	cd frontend && npx --yes openapi-typescript@7.13.0 src/api/openapi.json -o src/api/schema.d.ts

web: ## Arranca la web en http://localhost:5173 (reenvía /api, /v1 y /health a la API)
	npm --prefix frontend run dev

web-mocks: ## Web con datos de ejemplo, sin API (SCENARIO=stale|error|slow para ver avisos, errores o cargas)
	VITE_MOCK_SCENARIO=$(SCENARIO) npm --prefix frontend run dev:mocks

web-coverage: ## Tests de la web con cobertura (falla si baja de los mínimos; informe en frontend/coverage)
	npm --prefix frontend run test:coverage

web-build: ## Compila la web para producción en frontend/dist
	npm --prefix frontend run build

dev: ## Arranca la API y la web a la vez (Ctrl+C para las dos)
	$(MAKE) -j2 api web

docker-up: ## Levanta base de datos, API y web con Docker (web en http://localhost:8080)
	docker compose up -d --build

docker-seed: ## Carga en Docker el histórico de REE, entrena el modelo y hace la previsión de mañana
	docker compose run --rm pipeline backfill
	docker compose run --rm pipeline train
	docker compose run --rm pipeline daily

docker-down: ## Para los contenedores de Docker (los datos se conservan; -v en docker compose down los borra)
	docker compose down

docs: ## Guía técnica en http://localhost:8001, recargando al guardar (instala MkDocs la primera vez)
	$(PYTHON) -m pip install -q -r requirements-docs.txt
	$(PYTHON) -m mkdocs serve --dev-addr 127.0.0.1:8001

docs-build: ## Construye la guía técnica en site/ y falla si hay enlaces rotos
	$(PYTHON) -m pip install -q -r requirements-docs.txt
	$(PYTHON) -m mkdocs build --strict

clean: ## Borra cachés de Python, pytest y ruff y la web compilada
	find . -path ./venv -prune -o -path ./frontend/node_modules -prune -o -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache frontend/dist site
