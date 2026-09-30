# Lab 4 - machine translation workbench. `make help` lists everything.
SHELL := /bin/bash
COMPOSE := docker compose
WEB_PORT ?= 8090
API_PORT ?= 8020
-include .env

.DEFAULT_GOAL := help
.PHONY: help up down restart build logs logs-api ps test lint format seed dict-rebuild psql shell info clean

help: ## show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## build, start, migrate, seed and wait until the system is ready
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build --wait
	@$(MAKE) --no-print-directory info

down: ## stop and remove containers
	$(COMPOSE) down

restart: ## restart every service
	$(COMPOSE) restart

build: ## rebuild images without starting
	$(COMPOSE) build

logs: ## follow logs of every service
	$(COMPOSE) logs -f

logs-api: ## follow backend logs only
	$(COMPOSE) logs -f backend

ps: ## show container status
	$(COMPOSE) ps

test: ## run pytest inside the backend container
	$(COMPOSE) exec -T backend pytest -q

lint: ## ruff + mypy (backend), tsc + eslint (frontend)
	$(COMPOSE) exec -T backend ruff check app scripts tests
	$(COMPOSE) exec -T backend ruff format --check app scripts tests
	$(COMPOSE) exec -T backend mypy app/mt
	cd frontend && npm run lint && npx tsc --noEmit

format: ## autoformat the backend
	$(COMPOSE) exec -T backend ruff format app scripts tests
	$(COMPOSE) exec -T backend ruff check --fix app scripts tests

seed: ## re-seed the dictionary from data/dictionary/eng-rus.jsonl.gz
	$(COMPOSE) exec -T backend python -m scripts.seed_dictionary --force

dict-rebuild: ## re-download FreeDict and regenerate the committed seed file
	$(COMPOSE) exec -T backend python -m scripts.build_dictionary

psql: ## open a psql shell
	$(COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

shell: ## open a shell in the backend container
	$(COMPOSE) exec backend bash

info: ## print the URLs
	@echo ""
	@echo "  Interface   http://localhost:$(WEB_PORT)"
	@echo "  API docs    http://localhost:$(API_PORT)/api/docs"
	@echo "  Readiness   http://localhost:$(API_PORT)/api/health/ready"
	@echo ""

clean: ## remove containers, volumes and images of this project
	$(COMPOSE) down -v --rmi local --remove-orphans
