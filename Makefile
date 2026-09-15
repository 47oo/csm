# CSM 本地开发辅助命令（不改变任何 Git 状态）。
#
# 首次使用：
#   make install      # 安装后端依赖（Python 3.12）
#   make db-up        # 启动开发用 PostgreSQL（docker-compose.dev.yml，非生产）
#   make migrate      # alembic upgrade head
#   make run          # 启动后端 API（http://127.0.0.1:8000）
#
# 前端（另见 frontend/README.md）：
#   cd frontend && npm install && npm run dev

PYTHON ?= python3
VENV ?= .venv
VENV_PY := $(VENV)/bin/python

.PHONY: help venv install migrate db-up db-down run test lint format-check check

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

venv: ## 创建虚拟环境
	$(PYTHON) -m venv $(VENV)

install: ## 安装后端依赖（含开发依赖）
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements-dev.txt

db-up: ## 启动开发用 PostgreSQL（仅 dev，非生产交付物）
	docker compose -f docker-compose.dev.yml up -d

db-down: ## 停止开发用 PostgreSQL
	docker compose -f docker-compose.dev.yml down

migrate: ## 应用数据库迁移到最新
	$(VENV)/bin/alembic upgrade head

run: ## 启动后端 API
	$(VENV)/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --app-dir backend

test: ## 运行后端测试（需要 PostgreSQL 时设置 CSM_TEST_DATABASE_URL）
	$(VENV_PY) -m pytest

lint: ## 运行 lint
	$(VENV)/bin/ruff check backend tests

format-check: ## 检查格式
	$(VENV)/bin/ruff format --check backend tests

check: lint format-check test ## lint + 格式 + 测试