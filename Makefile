# QE Copilot — developer task runner.
# `make install` bootstraps a venv + web deps; `make check` runs the full gate
# (ruff format+lint, mypy, pytest, eslint, tsc) — the same steps CI runs.

PYTHON ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
NPM ?= npm

.PHONY: help install install-py install-web \
        fmt fmt-check lint typecheck test test-unit test-integration \
        web-lint web-typecheck web-build web-e2e \
        check up down migrate downgrade clean

help:
	@echo "Targets:"
	@echo "  install      create venv, install Python (editable) + web deps"
	@echo "  check        ruff (format+lint) + mypy + pytest + eslint + tsc"
	@echo "  test         run all pytest tests (unit + integration)"
	@echo "  up           docker compose up -d"
	@echo "  down         docker compose down -v"
	@echo "  migrate      alembic upgrade head"

install: install-py install-web

install-py:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

install-web:
	$(NPM) --prefix apps/web install

# --- Python quality gates ---
fmt:
	$(BIN)/ruff format .
	$(BIN)/ruff check . --fix

fmt-check:
	$(BIN)/ruff format --check .

lint:
	$(BIN)/ruff check .

typecheck:
	$(BIN)/mypy .

test:
	$(BIN)/pytest

test-unit:
	$(BIN)/pytest -m "not integration"

test-integration:
	$(BIN)/pytest -m integration

# --- Frontend quality gates ---
web-lint:
	$(NPM) --prefix apps/web run lint

web-typecheck:
	$(NPM) --prefix apps/web run typecheck

web-build:
	$(NPM) --prefix apps/web run build

web-e2e:
	$(NPM) --prefix apps/web run test:e2e

# --- Aggregate gate (mirrors CI) ---
check: fmt-check lint typecheck test web-lint web-typecheck
	@echo "==> all checks passed"

# --- Infrastructure ---
up:
	docker compose up -d

down:
	docker compose down -v

migrate:
	$(BIN)/alembic upgrade head

downgrade:
	$(BIN)/alembic downgrade -1

clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
