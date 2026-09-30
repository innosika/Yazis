# Лабораторная работа 2 — распознавание языка текста (вариант 1)
# Все команды выполняются через Docker Compose.

COMPOSE ?= docker compose
FRONTEND_PORT ?= 3000

.DEFAULT_GOAL := help

help: ## Показать список команд
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Собрать и запустить приложение (UI: http://localhost:3000)
	$(COMPOSE) up --build -d
	@echo "→ Интерфейс: http://localhost:$(FRONTEND_PORT)   API: http://localhost:8000/api/docs"

down: ## Остановить контейнеры
	$(COMPOSE) down

restart: down up ## Перезапустить

build: ## Пересобрать образы без запуска
	$(COMPOSE) build

logs: ## Логи всех сервисов
	$(COMPOSE) logs -f

logs-backend: ## Логи бэкенда
	$(COMPOSE) logs -f backend

ps: ## Состояние контейнеров
	$(COMPOSE) ps

test: ## Запустить pytest внутри контейнера бэкенда
	$(COMPOSE) run --rm --no-deps backend python -m pytest -q

corpus: ## Пересобрать корпус (train/test) из Wikipedia
	$(COMPOSE) run --rm --no-deps backend python scripts/build_corpus.py

hard-cases: ## Перегенерировать сложные документы (hard_*) в коллекции
	$(COMPOSE) run --rm --no-deps backend python scripts/build_hard_cases.py

retrain: ## Удалить кэш нейросети и переобучить при следующем старте
	rm -f data/models/*.pt data/models/*.json
	$(COMPOSE) restart backend

report: ## Сохранить отчёт по коллекции в reports/ (json, csv, html)
	@mkdir -p reports
	@curl -sf -X POST http://localhost:8000/api/collection/evaluate -o reports/evaluation.json && echo "reports/evaluation.json"
	@curl -sf "http://localhost:8000/api/collection/report?format=csv" -o reports/evaluation.csv && echo "reports/evaluation.csv"
	@curl -sf "http://localhost:8000/api/collection/report?format=html" -o reports/evaluation.html && echo "reports/evaluation.html"

shell: ## Shell внутри контейнера бэкенда
	$(COMPOSE) exec backend bash

dev-backend: ## Бэкенд локально без Docker (нужен python3 + pip install -r backend/requirements.txt)
	cd backend && DATA_DIR=../data uvicorn app.main:app --reload --port 8000

dev-frontend: ## Фронтенд локально без Docker (нужен node; API проксируется на :8000)
	cd frontend && npm install && npm run dev

clean: down ## Остановить и удалить образы/тома проекта
	$(COMPOSE) down --rmi local -v --remove-orphans
	rm -rf frontend/node_modules frontend/dist reports

.PHONY: help up down restart build logs logs-backend ps test corpus hard-cases retrain report shell dev-backend dev-frontend clean
