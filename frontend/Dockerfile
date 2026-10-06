# F001 前端镜像：多阶段构建
# 阶段 1：node:22 构建 Vite 产物（含 TypeScript 类型检查）
# 阶段 2：nginx:1.27-alpine 提供静态服务
FROM node:22-alpine AS build
WORKDIR /app

# 先复制清单以利用层缓存；npm ci 严格按 lockfile 安装
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
