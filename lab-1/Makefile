# Information Retrieval System — Lab 1, variant 34.
# `make` with no target prints this help.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose
NETWORK := irs-lab1_default
API     := $(COMPOSE) exec -T api
RUN_API := $(COMPOSE) run --rm --no-deps api

# Colours for the help block.
C := \033[36m
B := \033[1m
R := \033[0m

.PHONY: help
help: ## Show this help
	@echo ""
	@echo -e "$(B)Information Retrieval System — variant 34$(R)"
	@echo -e "  vector search model · English corpus · web crawler"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  $(C)%-16s$(R) %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------- lifecycle ----

.PHONY: up
up: ## Build, start everything, then seed the corpus and build the index
	@$(COMPOSE) up -d --build
	@$(MAKE) --no-print-directory wait
	@$(MAKE) --no-print-directory seed
	@$(MAKE) --no-print-directory index
	@$(MAKE) --no-print-directory info

.PHONY: start
start: ## Start without rebuilding, seeding or indexing
	@$(COMPOSE) up -d
	@$(MAKE) --no-print-directory wait
	@$(MAKE) --no-print-directory info

.PHONY: build
build: ## Rebuild images
	@$(COMPOSE) build

.PHONY: build-light
build-light: ## Rebuild, skipping the ~130 MB embedding model download
	@BAKE_SEMANTIC_MODEL=0 SEMANTIC_ENABLED=false $(COMPOSE) build

.PHONY: down
down: ## Stop and remove containers (data volumes are kept)
	@$(COMPOSE) down --remove-orphans

.PHONY: clean
clean: ## Stop and remove containers AND all data. Destructive.
	@printf 'This deletes the database, the crawled corpus and the index. Continue? [y/N] '; \
	read -r reply; [ "$$reply" = "y" ] || { echo "aborted"; exit 1; }
	@$(COMPOSE) down --volumes --remove-orphans
	@echo "volumes removed"

.PHONY: restart
restart: ## Restart the API and worker (picks up source changes)
	@$(COMPOSE) restart api worker

.PHONY: wait
wait: ## Block until every service reports healthy
	@echo "waiting for services..."
	@for i in $$(seq 1 60); do \
		unhealthy=$$($(COMPOSE) ps --format '{{.Service}} {{.Health}}' \
			| awk '$$2 != "healthy" && $$2 != "" {print $$1}'); \
		if [ -z "$$unhealthy" ]; then echo "all services healthy"; exit 0; fi; \
		sleep 2; \
	done; \
	echo "timed out; current state:"; $(COMPOSE) ps; exit 1

.PHONY: info
info: ## Print the URLs to open
	@echo ""
	@echo -e "  $(B)Interface$(R)     http://localhost:$${WEB_PORT:-8080}"
	@echo -e "  $(B)API docs$(R)      http://localhost:$${API_PORT:-8010}/api/docs"
	@echo -e "  $(B)Readiness$(R)     http://localhost:$${API_PORT:-8010}/api/health/ready"
	@echo -e "  $(B)Metrics$(R)       http://localhost:$${API_PORT:-8010}/metrics"
	@echo ""

# ------------------------------------------------------------------ database ----

.PHONY: migrate
migrate: ## Apply migrations
	@$(API) alembic upgrade head

.PHONY: revision
revision: ## Autogenerate a migration: make revision m="add postings"
	@test -n "$(m)" || { echo 'usage: make revision m="message"'; exit 1; }
	@$(API) alembic revision --autogenerate -m "$(m)"

.PHONY: downgrade
downgrade: ## Roll back one migration
	@$(API) alembic downgrade -1

.PHONY: psql
psql: ## Open a psql shell
	@$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-irs} -d $${POSTGRES_DB:-irs}

# -------------------------------------------------------------------- corpus ----

.PHONY: seed
seed: ## Load the frozen document snapshot into the database
	@$(API) python -m irs.cli seed

.PHONY: index
index: ## Rebuild the inverted index and term weights
	@$(API) python -m irs.cli index

.PHONY: crawl
crawl: ## Crawl live URLs: make crawl url=https://example.com pages=50
	@test -n "$(url)" || { echo 'usage: make crawl url=https://... [pages=50] [depth=2]'; exit 1; }
	@$(API) python -m irs.cli crawl --url "$(url)" --pages "$${pages:-50}" --depth "$${depth:-2}"

.PHONY: snapshot
snapshot: ## Freeze the current corpus into backend/seeds/corpus.jsonl.gz
	@$(API) python -m irs.cli snapshot

# ---------------------------------------------------------------- evaluation ----

.PHONY: evaluate
evaluate: ## Run every ranker and compute all metrics (collection="name" to pick one)
	@$(API) python -m irs.cli evaluate $(if $(collection),--collection "$(collection)",)

# ------------------------------------------------------- topical test collection ----
# Order: topics → pool → topics-select → llm-up llm-pull → judge → evaluate collection=…

.PHONY: topics
topics: ## Seed the hand-authored topics from backend/seeds/topics.yaml
	@$(API) python -m irs.cli topics seed

.PHONY: pool
pool: ## Build the judgment pool (every ranker + oracle + random sample) — freezes the runs
	@$(API) python -m irs.cli pool build $(if $(depth),--depth $(depth),)
	@$(API) python -m irs.cli pool stats

.PHONY: pool-stats
pool-stats: ## Pool coverage and how relevant each provenance class turned out
	@$(API) python -m irs.cli pool stats

.PHONY: topics-select
topics-select: ## Select the judged subset after the pool exists (count=25)
	@$(API) python -m irs.cli topics select $(if $(count),--count $(count),)

.PHONY: judge
judge: ## Judge pending pool pairs with the LLM assessor, inline (limit=N for a smoke run)
	@$(API) python -m irs.cli judge $(if $(limit),--limit $(limit),) $(if $(dry),--dry-run,)

.PHONY: lsa
lsa: ## Build the latent-semantic projection for the Relevance Lab
	@$(API) python -m irs.cli lsa

.PHONY: llm-up
llm-up: ## Start the local LLM assessor (Ollama, compose profile `llm`)
	@$(COMPOSE) --profile llm up -d ollama
	@echo "ollama is starting; run 'make llm-pull' once to download the model"

.PHONY: llm-pull
llm-pull: ## Download the assessor model into the ollama volume (~2 GB, once)
	@$(COMPOSE) --profile llm exec ollama ollama pull $${ASSESSOR_LLM_MODEL:-qwen2.5:3b-instruct}

.PHONY: llm-down
llm-down: ## Stop the local LLM assessor
	@$(COMPOSE) --profile llm stop ollama

.PHONY: report
report: ## Regenerate docs/report.md with charts from real evaluation runs
	@$(API) python -m irs.cli report --out /app/docs
	@echo "report written to docs/"

# --------------------------------------------------------------------- checks ----

# The dev image carries pytest/ruff/mypy; the production image deliberately does not.
DEV_IMAGE := irs-backend:dev
DEV_RUN   := docker run --rm \
	-v "$(CURDIR)/backend/src:/app/src:ro" \
	-v "$(CURDIR)/backend/tests:/app/tests:ro" \
	-v "$(CURDIR)/backend/seeds:/app/seeds:ro" \
	-v "$(CURDIR)/backend/pyproject.toml:/app/pyproject.toml:ro" \
	$(DEV_IMAGE)

.PHONY: dev-image
dev-image: ## Build the image used for tests and linting
	@docker build --build-arg BAKE_SEMANTIC_MODEL=0 --target dev -t $(DEV_IMAGE) ./backend

.PHONY: test
test: ## Run the backend test suite (unit tests; no services needed)
	@$(DEV_RUN) pytest -q $(if $(k),-k "$(k)",) $(ARGS)

.PHONY: test-all
test-all: ## Run every test including those needing PostgreSQL
	@docker run --rm --network $(NETWORK) \
		-v "$(CURDIR)/backend/src:/app/src:ro" \
		-v "$(CURDIR)/backend/tests:/app/tests:ro" \
		-v "$(CURDIR)/backend/seeds:/app/seeds:ro" \
		-v "$(CURDIR)/backend/pyproject.toml:/app/pyproject.toml:ro" \
		-e POSTGRES_DSN=postgresql+asyncpg://$${POSTGRES_USER:-irs}:$${POSTGRES_PASSWORD:-irs}@postgres:5432/$${POSTGRES_DB:-irs} \
		-e REDIS_DSN=redis://redis:6379/0 \
		$(DEV_IMAGE) pytest -q $(ARGS)

.PHONY: test-fe
test-fe: ## Run the frontend test suite
	@cd frontend && npm test

.PHONY: lint
lint: ## ruff + mypy on the backend
	@$(DEV_RUN) sh -c "ruff check src tests && ruff format --check src tests && mypy src"

.PHONY: fmt
fmt: ## Auto-format the backend
	@docker run --rm \
		-v "$(CURDIR)/backend/src:/app/src" \
		-v "$(CURDIR)/backend/tests:/app/tests" \
		-v "$(CURDIR)/backend/pyproject.toml:/app/pyproject.toml:ro" \
		$(DEV_IMAGE) sh -c "ruff check --fix src tests && ruff format src tests"

.PHONY: smoke
smoke: ## End-to-end sanity check against the running system
	@set -e; \
	base=http://localhost:$${API_PORT:-8010}; \
	echo "-> readiness"; curl -fsS $$base/api/health/ready | head -c 400; echo; \
	echo "-> queue round-trip"; $(API) python -c "\
import asyncio; from irs.crawler.tasks import ping; \
print(asyncio.run(ping()))"; \
	echo "-> metrics"; curl -fsS $$base/metrics | grep -c '^irs_' | xargs -I{} echo "  {} irs metrics exported"; \
	echo "smoke OK"

# ----------------------------------------------------------------------- logs ----

.PHONY: logs
logs: ## Follow all logs
	@$(COMPOSE) logs -f --tail=100

.PHONY: logs-api
logs-api: ## Follow API logs
	@$(COMPOSE) logs -f --tail=100 api

.PHONY: logs-worker
logs-worker: ## Follow crawl worker logs
	@$(COMPOSE) logs -f --tail=100 worker

.PHONY: ps
ps: ## Show container status
	@$(COMPOSE) ps

.PHONY: shell
shell: ## Open a shell in the API container
	@$(COMPOSE) exec api bash
