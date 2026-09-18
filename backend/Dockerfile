# CSM 应用生产镜像（F015）。
#
# 构建上下文 = 仓库根（需要 requirements.txt / alembic.ini / backend/）：
#   docker build -f backend/Dockerfile -t csm-app .
#
# 不写死任何凭据 / DSN；CSM_ENVIRONMENT 由编排注入（生产固定 prod）。
# 以非 root 用户运行；运行命令无 --reload。

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

WORKDIR /app

# 运行依赖（不含 requirements-dev.txt）。
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码 + 迁移 + Alembic 配置，使 alembic upgrade head 与
# python -m app.auth.cli create-initial-admin 可在容器内直接运行。
COPY alembic.ini ./
COPY backend ./backend

# 非 root 运行用户。
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin csm
USER csm

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]