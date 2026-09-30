# Lector - voice reader for CS papers. `make help` lists everything.
SHELL := /bin/bash
COMPOSE := docker compose
WEB_PORT ?= 8100
API_PORT ?= 8030
-include .env

.DEFAULT_GOAL := help
.PHONY: help up down restart build models logs logs-api ps test test-all loopback catalog \
        lint format shell info extension reset-db clean dev

help: ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up: ## build, download models once, start and wait until the voice is ready
	@test -f .env || cp .env.example .env
	$(COMPOSE) build
	$(COMPOSE) run --rm models
	$(COMPOSE) up -d --wait
	@$(MAKE) --no-print-directory info

down: ## stop and remove containers (models and library are kept)
	$(COMPOSE) down

restart: ## restart backend and frontend
	$(COMPOSE) restart backend frontend

build: ## rebuild images without starting
	$(COMPOSE) build

models: ## download the speech models into the models volume (skips what is cached)
	$(COMPOSE) run --rm models

logs: ## follow logs of every service
	$(COMPOSE) logs -f backend frontend

logs-api: ## follow backend logs only
	$(COMPOSE) logs -f backend

ps: ## show container status
	$(COMPOSE) ps

test: ## fast test suite (no speech models needed)
	$(COMPOSE) exec -T backend pytest -q
	cd frontend && (test -d node_modules || npm ci --no-audit --no-fund) && npx vitest run

test-all: ## every test, including the ones that load the real models
	$(COMPOSE) exec -T backend pytest -q -m ""

loopback: ## synthesize command phrases with Kokoro, recognize them, print accuracy (ENGINE=local|cloud)
	$(COMPOSE) exec -T backend python -m scripts.loopback --engine $(or $(ENGINE),local)

catalog: ## export the voice command catalog for the frontend type check
	$(COMPOSE) exec -T backend python -m scripts.export_catalog > frontend/src/voice/catalog.gen.ts

lint: ## ruff + mypy (backend), eslint + tsc (frontend)
	$(COMPOSE) exec -T backend ruff check app scripts tests
	$(COMPOSE) exec -T backend ruff format --check app scripts tests
	$(COMPOSE) exec -T backend mypy app
	cd frontend && (test -d node_modules || npm ci --no-audit --no-fund) && npm run lint && npx tsc --noEmit

format: ## autoformat the backend
	$(COMPOSE) exec -T backend ruff format app scripts tests
	$(COMPOSE) exec -T backend ruff check --fix app scripts tests

shell: ## open a shell in the backend container
	$(COMPOSE) exec backend bash

dev: ## frontend dev server on :5174 against the running API
	cd frontend && (test -d node_modules || npm ci --no-audit --no-fund) && npm run dev

extension: ## pack the Chrome extension into extension/lector-extension.zip
	cd extension && rm -f lector-extension.zip && zip -qr lector-extension.zip . -x '*.zip'
	@echo "  extension/lector-extension.zip  (or load extension/ unpacked in chrome://extensions)"

reset-db: ## forget the library, settings and custom commands (models and audio cache stay)
	$(COMPOSE) exec -T backend sh -c 'rm -f /data/lector.db /data/lector.db-wal /data/lector.db-shm'
	$(COMPOSE) restart backend

info: ## print the URLs
	@echo ""
	@echo "  Lector      http://localhost:$(WEB_PORT)"
	@echo "  API docs    http://localhost:$(API_PORT)/api/docs"
	@echo "  Readiness   http://localhost:$(API_PORT)/api/health/ready"
	@echo ""

clean: ## remove containers, volumes (models too) and images of this project
	$(COMPOSE) down -v --rmi local --remove-orphans
