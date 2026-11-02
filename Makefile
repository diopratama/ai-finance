.PHONY: help setup install run-local run-local-backend run-local-frontend run-docker stop clean test

# Detect docker-compose (standalone) vs docker compose (plugin)
DOCKER_COMPOSE := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

help: ## Menampilkan daftar perintah yang tersedia
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## First-time setup: salin .env jika belum ada dan instal dependensi
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	$(MAKE) install

install: ## Instal dependensi backend (Python) dan frontend (Node)
	@echo "Installing backend dependencies..."
	@cd backend && python3 -m pip install -r requirements.txt || true
	@echo "Installing frontend dependencies..."
	@cd frontend && npm install

run-local: ## Jalankan backend (port 8000) dan frontend (port 3000) secara lokal
	@echo "Starting backend and frontend..."
	@(trap 'kill 0' SIGINT; cd backend && uvicorn app.main:app --reload --port 8000 & cd frontend && npm run dev & wait)

run-local-backend: ## Jalankan hanya backend FastAPI (port 8000)
	@cd backend && uvicorn app.main:app --reload --port 8000

run-local-frontend: ## Jalankan hanya frontend Next.js (port 3000)
	@cd frontend && npm run dev

run-docker: ## Jalankan seluruh sistem menggunakan Docker Compose
	@echo "Building and starting containers using $(DOCKER_COMPOSE)..."
	$(DOCKER_COMPOSE) up --build -d

stop: ## Hentikan container Docker
	$(DOCKER_COMPOSE) stop

clean: ## Hentikan container dan bersihkan volume Docker
	$(DOCKER_COMPOSE) down -v

test: ## Jalankan unit dan integrasi test di dalam container backend
	docker exec ai_finance_backend python -m pytest tests/ -v

