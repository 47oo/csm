# CSM V1 内网部署与运行环境

> 唯一权威部署文档（F015）。面向 HPC / AI 运维与基础设施管理员。
> 目标形态：**单台独立内网虚拟机**，Internal IP + HTTP，docker-compose 编排
> （nginx + 应用 + PostgreSQL）。本机仅运行 CSM 自身组件。
>
> 开发流程见 `README.md` §3；本文件只描述生产内网部署与运维。

---

## 1. 前置条件

| 项 | 要求 |
| --- | --- |
| 部署机 | 独立内网虚拟机，**仅运行 CSM 自身组件**；固定 Internal IP |
| 容器运行时 | Docker Engine + Docker Compose v2（本文件命令使用 `docker compose`） |
| 镜像来源 | 能从内网镜像源 / 代理获取 `python:3.12-slim`、`node:22-alpine`、`nginx:stable-alpine`、`postgres:16`，或使用离线导入 / 内网 registry（见 §12） |
| 仓库 | 本仓库 checkout（用于在部署机构建镜像） |
| 网络 | 仅需内网可达；**不需要**公网入口、域名解析或 HTTPS |
| 资源 | 由运维方按容量规划（本文件不规定 VM 规格 / 磁盘） |

**不使用**：HTTPS / TLS 证书 / 域名 / 公网入口 / 多机 / Kubernetes / 负载均衡 /
监控告警平台 / 消息队列 / Redis / Elasticsearch（见 §12）。

---

## 2. 部署命令序列

所有命令均在**仓库根目录**执行。首次部署：

```bash
# 2.1 准备生产环境变量（仓库外，勿提交）
mkdir -p /etc/csm
cp deploy/env.prod.example /etc/csm/csm.env
# 编辑 /etc/csm/csm.env，填入 CSM_POSTGRES_USER / CSM_POSTGRES_PASSWORD / CSM_POSTGRES_DB
# 口令须为 URL-safe 字符（或 URL 编码），因为应用 DSN 由这些变量插值组装。

# 2.2 概念校验编排（缺失凭据会直接失败，证明无内置默认口令）
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env config

# 2.3 构建并启动数据库
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env up -d --build postgres
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env ps   # 等待 postgres healthy

# 2.4 首次初始化（迁移 + 初始管理员）—— 见 §3

# 2.5 启动全栈
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env up -d
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env ps   # 三个服务均 healthy
```

- 对外发布端口**仅** nginx 的 `${CSM_HTTP_PORT:-80}:80`；`app` / `postgres`
  只在内部网络 `expose`，**不**发布到宿主 / 内网。
- `app` 硬编码 `CSM_ENVIRONMENT=prod`，并显式设置连接池上限（见 §7）。
- 三个服务均声明 `restart: unless-stopped`：宿主 / 守护进程重启后自动恢复。

> 也可把凭据导出为环境变量而不使用 `--env-file`；此时变量必须由部署环境提供，
> 缺失时编排会拒绝启动（fail-closed）。

---

## 3. 首次初始化

### 3.1 数据库迁移

```bash
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env \
  run --rm --no-deps app alembic upgrade head
```

- 该命令**幂等**：在迁移链 head 处重复执行为 no-op，可安全重跑。
- 必须**先**迁移**再**启动应用 / 升级。
- 生产环境**禁止**执行任何向下的迁移操作：向下的迁移会 DROP 表并丢失资源历史
  （ADR-0002：版本化、向前迁移；R-DELETE-001）。

### 3.2 建立初始管理员

系统中**不存在**自助注册端点 / 页面；初始管理员只能通过 CLI 建立：

```bash
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env \
  run --rm app python -m app.auth.cli create-initial-admin --username <用户名>
```

- 口令从 **stdin** 读取（交互式终端下无回显），**不进入 argv / shell history**。
- 口令长度**至少 8 位**；不足则命令失败且不产生账号。
- 命令**幂等**：用户名已存在时输出「已存在，未修改」并退出 0。
- 本文档**不提供任何示例口令**。

---

## 4. 端到端验证

在内网**另一台机器**的浏览器打开 `http://<Internal IP>/`（默认 80 端口）。逐项确认：

1. **入口呈现登录页**（SPA，非 401 JSON / 空白页）。
2. 用 §3.2 建立的凭据**登录成功**。
3. 登录后完成一次 Cluster 的**列表查询**与一次**登记**，并在界面看到结果。
4. 已认证访问 `GET /api/health` 返回 `200 {"status":"ok","database":"ok"}`。
5. 未认证访问入口页面呈现登录页；浏览器直接访问 `/api/health`、任一 `/api/clusters*`
   → `401 UNAUTHENTICATED`（不返回资源数据）。
6. 直接访问 `/docs`、`/redoc`、`/openapi.json` → **不可达**（`404`）。
7. 仅 nginx 入口端口对外：在部署机执行 `ss -ltn`（或 `docker compose ps`）确认
   宿主仅监听 `${CSM_HTTP_PORT}`，未监听 5432 / 8000。
8. **数据持久化**：登记一条 Cluster → `docker compose ... stop` / `start`，
   以及 `up -d --force-recreate`（容器被替换）后，该 Cluster 仍可查到；
   `docker volume ls | grep csm-prod-pgdata` 存在。

---

## 5. 升级步骤

升级采用「**先迁移、后替换应用**」的向前流程：

```bash
# 5.1 获取新版本代码 / 镜像（保留 /etc/csm/csm.env 不变）
# 5.2 先应用迁移（幂等）
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env \
  run --rm --no-deps app alembic upgrade head

# 5.3 重建并滚动替换应用与入口
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env up -d --build
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env ps
```

- **禁止**使用任何会删除数据卷的 `down` 选项（例如删除命名卷的变体）：会销毁资源历史。
- 停止 / 重建容器不影响命名卷内数据（§4.8）。
- 本 Feature **不承诺**应用镜像层面的降级流程；不得在 schema 已前进后回退到旧镜像。

---

## 6. 数据库 locale / encoding / PostgreSQL 大版本

生产 `postgres` 服务固定：

- 镜像版本：**PostgreSQL 16**（`postgres:16`）。
- initdb 参数：`POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale=C.UTF-8"`，并设置
  `LANG=C.UTF-8` / `LC_ALL=C.UTF-8`。

**记录与持续校验**（部署后、**录入生产数据前**执行）：

```bash
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env \
  exec postgres psql -U "$CSM_POSTGRES_USER" -d "$CSM_POSTGRES_DB" -c \
  "SELECT datname, datcollate, datctype, pg_encoding_to_char(encoding) AS encoding
     FROM pg_database WHERE datname = current_database();"
```

期望：`datcollate` / `datctype` = `C.UTF-8`，`encoding` = `UTF8`。

```bash
docker compose -f docker-compose.prod.yml --env-file /etc/csm/csm.env \
  exec postgres psql -U "$CSM_POSTGRES_USER" -d "$CSM_POSTGRES_DB" -c \
  "SELECT ('cluster-a' = 'Cluster-A') AS case_sensitive;"
```

期望：`case_sensitive` = `false`（大小写敏感，§22）。该断言是「locale 未被静默改变」
的持续回归，**必须绕过应用层直连数据库执行**。

> ⚠️ **重要**：locale / encoding 只在命名卷**首次初始化**时生效。对已存在的卷修改
> `POSTGRES_INITDB_ARGS` **不会**改变既有数据目录的 locale。因此在**录入任何生产数据
> 之前**务必执行上述断言；若不符，应删除该卷后重建（此时尚无历史数据可丢）。

---

## 7. 连接池上限

`app` 服务显式设置：

| 变量 | 值 |
| --- | --- |
| `CSM_DB_POOL_SIZE` | `5` |
| `CSM_DB_MAX_OVERFLOW` | `10` |

**依据**：单 ASGI 进程（V1 单进程）可同时持有的数据库连接上限 =
`pool_size + max_overflow = 5 + 10 = 15`。PostgreSQL `max_connections` 默认为 `100`；
余量 `100 − 15 = 85` 足以容纳迁移（单连接）、`psql` 排障与运维。规模依据：资源总量约
10⁵、并发约 50（DEC-015）。V1 不做数据库参数调优，也不引入外部连接池中间件。

---

## 8. 运行约束：仅限受控内网 / 无 HTTPS / Cookie 无 `Secure`

- 本系统**仅限受控内网**部署与访问；唯一入口为 `http://<Internal IP>/`（HTTP）。
- V1 **不使用** HTTPS、TLS 证书、域名或公网入口（R-DEPLOY-003）。
- 会话 Cookie `csm_session` 为 `HttpOnly` + `SameSite=Lax` + `Path=/api`，
  **不设 `Secure`**：在明文 HTTP 下浏览器会丢弃带 `Secure` 的 Cookie。
  这是**已确认的产品取舍**，不是缺陷。
- 因此**不得**把本系统暴露到公网；若后续网络安全要求改变，应作为独立设计变更。

---

## 9. 存活 / 就绪探测

探测采用**容器 / 运行时级（传输层）**机制，**不发起 HTTP**、不引用 `/api`、
不返回任何资源 / 会话 / 凭据 / 数据库内容：

| 服务 | 探测 |
| --- | --- |
| `postgres` | `pg_isready -U <user> -d <db>`（PostgreSQL 原生协议） |
| `app` | TCP 连接 `127.0.0.1:8000` |
| `nginx` | TCP 连接 `127.0.0.1:80` |

运维与编排可通过 `docker compose ps`（`healthy` / `unhealthy`）与
`docker inspect --format '{{json .State.Health}}' <container>` 观察结果。
`app` 的就绪探测**不代表数据库可用**；数据库就绪由 `postgres` 的 `pg_isready`
与 `depends_on: condition: service_healthy` 保证。

---

## 10. 账号停用与运维约束

- **账号停用**：无管理界面，运维直接操作数据库（即时生效）：

  ```sql
  UPDATE users SET active = FALSE, updated_at = now() WHERE username = '<name>';
  ```

- **密钥 / 凭据**：生产凭据只存在于部署机的环境文件（如 `/etc/csm/csm.env`），
  权限应限制为仅运维可读；不得提交到版本库，也不得写入镜像。
- **会话**：绝对有效期 8 小时，不滑动续期；登出 / 过期物理删除会话行。
  详见 `README.md` §5.1。
- **Shell 命令不要使用会删除命名卷的 `down` 变体**；排障走
  `docker compose exec`，不要重建数据卷。
- 命名卷 `csm-prod-pgdata` 承载资源事实库，**不得删除**。

---

## 11. 常见故障

| 现象 | 排查 |
| --- | --- |
| `docker compose ... up` 报缺少变量 | 未提供 / 未加载环境文件；按 §2.1 准备并传 `--env-file` |
| `postgres` 一直 `starting` / `unhealthy` | 查看 `docker compose logs postgres`；确认卷权限与磁盘空间 |
| 已认证 `GET /api/health` 返回 `500` | 应用连不上数据库：核对 DSN 组装与凭据一致性（口令含特殊字符时需 URL 编码） |
| 登录后立刻掉线 | 浏览器丢弃 Cookie：确认使用的是 HTTP 入口且未强制要求 `Secure`（§8） |
| 中文乱码 / 大小写不敏感 | locale / encoding 不符；按 §6 校验，必要时在录入数据前重建卷 |
| 入口 80 端口被占用 | 设置 `CSM_HTTP_PORT` 为其他值后重启 |

---

## 12. 明确不包含（边界声明）

本部署产物与文档**不**包含、不提供、不指引：HTTPS / TLS / 证书 / 域名 / 公网入口 /
外部网关；多机 / 高可用 / 负载均衡 / 多 worker / 容器编排平台；监控告警 / 工单 /
消息队列 / Redis / 事件总线 / Elasticsearch；RBAC / LDAP / OAuth / SSO / MFA /
自助注册 / 口令找回；备份 / 恢复 / 灾备；数据归档 / 清理；CI/CD 与镜像回滚；
宿主机防火墙 / systemd / 日志采集；生产数据库参数调优（除 §7 连接池上限）。

镜像获取方式（在部署机构建 vs 内网 registry / 离线导入）属运维选择，不影响本系统行为。

---

## 13. AC-09 内容清单对照

| # | 内容 | 位置 |
| --- | --- | --- |
| ① | 前置条件 | §1 |
| ② | 部署命令序列 | §2 |
| ③ | 首次初始化（迁移 + 初始管理员） | §3 |
| ④ | 端到端验证步骤 | §4 |
| ⑤ | 升级步骤 | §5 |
| ⑥ | `datcollate` / `datctype` / `encoding` 与 PG 大版本 | §6 |
| ⑦ | 连接池上限依据 | §7 |
| ⑧ | 仅限受控内网 / 无 HTTPS / Cookie 无 `Secure` | §8 |
| ⑨ | 存活探测方式 | §9 |
| ⑩ | 账号停用与运维约束 | §10（并指向 `README.md` §5.1） |