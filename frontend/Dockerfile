# CSM 前端生产镜像（F015，多阶段）。
#
# 构建上下文 = **仓库根**（需要 frontend/ 源码 + deploy/nginx/default.conf）：
#   docker build -f frontend/Dockerfile -t csm-nginx .
#
# builder：Node 构建静态产物；runtime：nginx 提供 dist 与 /api 反向代理。

FROM node:22-alpine AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:stable-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80