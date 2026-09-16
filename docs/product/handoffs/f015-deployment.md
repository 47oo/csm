# Product Handoff — F015 内网部署与运行环境

> Status: `READY FOR ARCHITECT`
> Author Role: product-manager
> Date: 2026-09-17
> Feature: F015（ENABLER，E07，P0，`depends_on: [F012, F013]`）
> Git: `feature/F015-deployment`，base `develop`，`start_commit` = `5c9ca84f94134c9bcc87c61a47fd9280ff99d411`
> 已核实事实（只读）：F012 / F013 / F014 均 `DONE`（`project-plan.yaml`）；生产部署打包**当前不存在**（无生产 compose / Dockerfile / nginx 配置 / `docs/deployment/`）；`docker-compose.dev.yml` 顶部显式声明「不是 F015 的生产交付物」；`CSM_ENVIRONMENT` 已存在但当前仅作标签（`backend/app/config.py:27`）；`docker-compose.dev.yml` 把 PostgreSQL `5432` 发布到宿主。

---

## Feature

内网部署与运行环境（F015）— CSM V1 的**可运行生产部署产物**：docker-compose（nginx + 应用 + PostgreSQL）、部署文档、运行约束。

## Problem

CSM 现在只有**开发形态**：按 `README.md` §3 手工建库、装依赖、`alembic upgrade head`、`uvicorn --reload`、前端 `npm run dev`，数据库由 `docker-compose.dev.yml` 提供（该文件已明确标注「不是 F015 的生产交付物」）。运维人员**无法把系统作为内网可用服务交给使用者**：

- 没有生产编排，启动方式依赖开发者本机的工具链与目录结构；
- 没有生产前端产物（当前只有 Vite dev server），也没有 nginx 静态服务与 `/api` 反向代理配置；
- 没有运维文档说明前置条件、首次初始化（migration、初始管理员）、运行约束（内网 HTTP、Cookie 无 `Secure`、数据库 locale 与版本、连接池上限）与升级步骤；
- 开发形态会顺带把框架默认文档面（`/docs`、`/redoc`、`/openapi.json`）与数据库端口暴露出来（F013 REV-01 实测三者在未认证下返回 `200`）。

已确认的产品约束是：CSM V1 部署在**独立内网虚拟机**（R-DEPLOY-001）、**主要通过内网访问**（R-DEPLOY-002）、使用 **Internal IP + HTTP** 且不自动增加公网入口 / 域名 / HTTPS（R-DEPLOY-003）；打包方式已由用户裁定为 **docker-compose（nginx + 应用 + PostgreSQL）**（DEC-016 / ADR-0001）。

使用者：HPC / AI 集群运维人员与基础设施管理员（§3）。场景是「在机房内网虚拟机上把 CSM 立起来 → 建立初始管理员 → 从内网另一台机器用浏览器登录 → 登记/查询资源 → 机器重启后数据仍在 → 版本升级时按文档执行 migration」。

F015 的产品价值：**把 CSM 从「开发者本机能跑」变成「运维可部署、可登录、可运维、可升级的内网系统」**，且不因部署形态扩大任何访问面（认证边界、公共数据面、暴露端口）。

## Confirmed Requirements

仅列已确认内容，来源见括号；其中 #12 / #13 / #14 为本 Feature 被显式交由 Product 裁定的问题（F013 PROPOSED-4 / F013 REV-01），裁定结果不新增任何领域规则、不修改任何 ADR。

**交付形态**

1. **F015 交付「可运行的生产部署产物 + 部署文档 + 运行约束」，不是仅文档。**（ADR-0001 Decision 部署项：单台内网虚拟机，docker-compose；DEC-016；`csm-v1-foundation-architecture.md` Architecture Summary #2；M1 `completion_criteria`：「系统可在独立内网虚拟机以 Internal IP + HTTP 运行」；F012 Handoff 明确把「生产内网虚拟机 + docker-compose（nginx + 应用 + PostgreSQL）+ locale/encoding 文档」列为 **F015**，并声明 `docker-compose.dev.yml`「非生产交付物」。）
2. **编排组成固定为三部分：nginx（前端静态资源 + API 反向代理）、应用（单个 ASGI 进程）、PostgreSQL。**（ADR-0001 Decision；`csm-v1-foundation-architecture.md` Architecture Summary #2。）
3. **部署在独立内网虚拟机**（R-DEPLOY-001）。
4. **系统主要通过内网访问**（R-DEPLOY-002）。
5. **V1 使用 Internal IP + HTTP**；不因互联网 Web 最佳实践自动增加公网入口、域名、HTTPS；如后续网络安全要求改变，再单独设计（R-DEPLOY-003；§20）。
6. **不引入任何 §23 排除的基础设施**：监控平台替代 / 告警平台 / 工单系统 / 微服务化等（§23；ADR-0001 Constraints #1 另含消息队列、Redis、Event Bus、CQRS、Kubernetes、Elasticsearch）。

**运行环境与配置**

7. **生产运行环境标签为 `prod`**（`CSM_ENVIRONMENT=prod`），且生产下任何 dev-only 面不可达（F012 Review Follow-up 1「F015 强制 `CSM_ENVIRONMENT=prod` + 部署断言」，已记为 F015 进入条件；F012 Handoff Constraints #7；F013 REV-01）。
8. **数据库 DSN 与凭据由部署时外部注入**，生产部署产物不得依赖或包含开发默认连接串 / 默认口令（`.env.example`「不得提交真实密码」；`docker-compose.dev.yml` 的 `csm:csm` 属 dev 用途）。
9. **部署文档必须记录数据库的 `datcollate` / `datctype` / `encoding` 与 PostgreSQL 大版本**，并把「大小写敏感」断言作为「locale 未被静默改变」的持续回归（F012 Handoff Q5；`README.md` §7；`csm-v1-foundation-architecture.md` Risk #1；ADR-0002 §1）。
10. **部署文档必须明确连接池上限（低于 PostgreSQL `max_connections`）**（`csm-v1-foundation-architecture.md`「规模假设与阈值」；DEC-015：资源总量约 10⁵、并发约 50）。
11. **部署/升级步骤必须包含 `alembic upgrade head`，可重复应用；生产环境禁止 `downgrade`**（ADR-0002 迁移策略「版本化、向前」；F012 Handoff Data Layer #6「生产环境禁止 downgrade（会 DROP 并丢失资源历史）」；F012 AC「基线 migration 可应用、可重复应用、可从空库重建」）。
12. **资源数据必须持久化**：PostgreSQL 数据落于持久卷，容器重启 / 重建后资源数据仍在（§25 History Preservation；项目目标「替代 Excel 的可信资源事实库」；R-DELETE-001 不得物理删除核心资源记录 —— 部署形态不得使该语义失效）。

**认证、探针与信息面（Product 裁定）**

13. **认证边界在新部署形态下不变**：除 `POST /api/auth/login` 外全部 `/api/*` 未认证一律 `401 UNAUTHENTICATED`，**`/api/health` 不豁免**（F013 AC-01 / AC-13；ADR-0005 §4；F013 Handoff REQUIRED #8）。
14. **存活 / 就绪探测必须存在，且必须走产品认证面之外的机制**：
    - **不得**为探测新增任何 `/api/*` 认证豁免成员（F013 REQUIRED #8）；
    - 探测响应**不得**包含任何产品数据、资源数据、会话信息或凭据；
    - 探测**不得**成为绕过认证访问产品数据的路径；
    - 落地机制二选一（F013 PROPOSED-4，由 F015 决策）：**(a) 容器 / 运行时级探测（TCP / 进程级，不发起 HTTP）**，或 **(b) 挂载在 `/api` 之外的 HTTP 生存性路径（如 `/healthz`）**；采用 (b) 时该路径**仅 GET**、不属产品 API 契约、不进入任何契约文档。
    - **产品倾向 (a)**：不新增任何 HTTP 面无收益的暴露面（§25 Simple First）。
15. **`CSM_ENVIRONMENT=prod` 时，框架默认文档面 `/docs`、`/redoc`、`/openapi.json` 必须不可达**（关闭，或仅认证后可达）（F013 REV-01：三者位于 `/api` 之外、未认证可达，实测均 `200`，暴露完整 API schema）。理由：没有任何已确认需求要求向未认证访问者提供 API 文档，而它们位于认证边界之外；dev / test 可保留。**不得**因此改动 `/api/*` 的认证规则或契约。
    > 该裁定为 F015 生产信息面取舍，可逆；若组织明确需要生产环境 API 文档，见 NQ-3。

**运维与边界**

16. **初始管理员按文档化步骤建立**：CLI 从 stdin 读口令、幂等；产品中不存在自助注册入口（F013 AC-11 / ADR-0005 §1；`README.md` §5.1）。
17. **部署文档必须记录「仅限受控内网」的运行约束**：内网明文 HTTP、无 HTTPS、会话 Cookie `HttpOnly` + `SameSite=Lax` + **不设 `Secure`**（因 HTTP 下浏览器会丢弃）为**已确认产品取舍**，不是缺陷；文档必须同时写明该边界要求，不得反向要求引入 HTTPS / 域名 / 公网入口（ADR-0005 §3 + Consequences；Risk #3；R-DEPLOY-003）。
18. **生产部署不得把数据库（或应用内部端口）直接发布到宿主 / 内网**；对 Internal IP 暴露的入口只有 nginx（ADR-0001 Decision「nginx 为入口」；R-DEPLOY-001 / 002 / 003；F015 不得照搬 `docker-compose.dev.yml` 的 `5432:5432`）。
19. **生产部署产物不得包含可用于生产环境的硬编码默认口令**（第 8 条的具体化）。

## Confirmed Domain Rules

本 Feature **不新增、不修改任何领域对象、字段、关系、状态或唯一性规则**；不定义任何资源行为。它依赖并**必须不破坏**以下已确认领域规则：

| 规则 | 内容 | 来源 |
|---|---|---|
| 显式资源类型 / 显式约束 | 每类资源独立模块 + 独立表；无 DataCenter / Rack；仅 BareMetal 有状态 | `requirements.md` §4 / §5 / §23 / §24；`domain-model.md`；ADR-0001 |
| 大小写敏感唯一性 | Cluster Name / BareMetal hostname 等值比较区分大小写（§22）；**由数据库 locale 承载**，非应用折叠 | `requirements.md` §22；ADR-0002 §1；F012 Handoff Q5 |
| 已删不占唯一性 | partial unique index predicate `deleted_at IS NULL` | ADR-0004 §2；`domain-model.yaml > lifecycle` |
| 历史保留 | 资源删除不破坏历史事实 | `requirements.md` §25；R-DELETE-001 |
| 认证边界 | 仅「已认证 / 未认证」两态；除登录端点外全部 `/api/*` 要求认证；无 RBAC、无 403 触发路径；认证表不适用资源软删语义 | ADR-0005 §4；R-AUTH-003；`domain-model.yaml > authentication.note` |
| 关键约束不只依赖 UI | 一致性由 Backend / Database 保证 | `requirements.md` §21 |

**部署形态不得改变上述任一语义**：locale / 版本 / 卷 / 端口 / 环境标签的任何配置都不得使「大小写敏感」「已删不占唯一性」「历史保留」「两态认证边界」在部署环境中静默失效。

## Scope

### 本次包含

1. **生产 docker-compose 编排**（nginx + 应用 + PostgreSQL）：服务定义、镜像构建入口、生产环境变量注入、数据卷、服务依赖与启动顺序、入口端口发布策略。
2. **生产 nginx 配置**：前端生产构建产物静态服务 + `/api` 反向代理到应用 + 入口监听。
3. **后端生产运行形态**：`prod` 环境标签、DSN 外部注入、连接池上限、无 `--reload` 的运行命令。
4. **生产下 dev-only 面关闭**：框架默认文档面不可达（#15）；不存在任何 dev-only 自检面（F012 `/_foundation` 已由 F001 彻底删除，部署产物不得复活任何等价面）。
5. **存活 / 就绪探测**（#14）：不经过产品认证面的机制 + 供运维与编排使用的可观察结果。
6. **部署文档**：前置条件、部署步骤、首次初始化（`alembic upgrade head` + 初始管理员）、端到端验证步骤、升级步骤、内网 / HTTP / 无 `Secure` 约束、locale / encoding / PG 版本、连接池上限、探测方式、账号停用与运维约束（引用 `README.md` §5.1）。
7. **端到端可复现验收**：干净内网虚拟机（或等价环境）上按文档部署后，通过 Internal IP + HTTP 登录并访问资源；未认证访问仍被拒。
8. **`README.md` 的部署入口更新**：区分「本地开发流程」（§3，保持有效）与「生产内网部署流程」（新增或指向部署文档），并纠正 `docker-compose.dev.yml` 的用途表述（该文件仍为 dev 专用）。

### 本次明确不包含

（用户明确排除，或已由 CONFIRMED 规则 / 已批准架构约束排除）

1. **HTTPS / TLS 证书 / 域名 / 公网入口 / 外部网关**（R-DEPLOY-003；§20；ADR-0005 Alternatives）。
2. **Kubernetes、微服务化、多机部署、高可用、负载均衡、多进程横向扩展**（R-DEPLOY-001 单台内网虚拟机；ADR-0001 Decision 单体 + Constraints #1；§23）。
3. **监控平台替代 / 告警平台 / 工单系统**（§23）。
4. **消息队列、Redis、Event Bus、CQRS、Elasticsearch 等额外基础设施**（ADR-0001 Constraints #1；§23）。
5. **RBAC / LDAP / AD / OAuth / SSO / MFA / 自助注册 / 口令找回**（R-AUTH-002 / R-AUTH-003；ADR-0005 §1；§23）。
6. **任何新业务功能、新 API、领域规则变更**（F015 是 ENABLER；`project-plan.yaml > F015.requirements` 仅 R-DEPLOY-001~003）。
7. **开发形态的替换或删除**：`docker-compose.dev.yml`、`README.md` §3 的本地开发流程保持有效（F012 交付，非生产交付物）。

### 本次未涉及

当前需求没有要求，但**不能推断为永远不需要**：

- 备份 / 恢复 / 灾备演练（`pg_dump` / `pg_restore` 步骤、备份周期、保留份数）；
- 数据归档 / 清理 / 保留期限（与 F014 PROPOSED-3 同一悬空问题）；
- CI/CD 流水线、内网镜像仓库、自动化发布与镜像回滚策略；
- 宿主机层面运维：Docker / Compose 安装、开机自启（`restart` 策略 / systemd 单元）、防火墙与网络策略、VM 规格与磁盘容量；
- 集中式日志采集 / 访问日志归档 / 审计日志；
- 多环境（staging）部署；
- 部署变更审批 / 发布窗口约定；
- 面向最终用户的使用手册与培训材料；
- 生产数据库参数调优（除连接池上限外）。

## Acceptance Criteria

可判定（是 / 否），描述用户可观察到的行为。与 `project-plan.yaml > F015.acceptance_criteria` 逐条对齐（映射见末尾），可细化但未削弱。

- **AC-01（独立内网虚拟机，R-DEPLOY-001）**：在一台**独立内网虚拟机**（该机上仅运行 CSM 自身组件）上，按部署文档从零完成部署后，nginx、应用、PostgreSQL **三个组件均在该机运行**；部署过程不依赖任何 CSM 之外的外部服务（仅依赖容器运行时 / 镜像来源与内网网络）。
- **AC-02（内网访问，R-DEPLOY-002）**：从**内网内另一台机器**的浏览器访问 `http://<Internal IP>/` 可打开 CSM；全过程不经过公网、不需要域名解析。
- **AC-03（Internal IP + HTTP，不引入公网入口 / 域名 / HTTPS，R-DEPLOY-003）**：部署产物与文档中不存在 HTTPS 终止、证书、域名或公网入口配置；唯一对外入口为 `http://<Internal IP>/` 的 HTTP（80）端口。
- **AC-04（端到端可用：可登录、可访问资源）**：按部署文档步骤执行后：① 未认证访问入口页面呈现**登录页**（不是 401 JSON / 空白页）；② 按文档建立初始管理员后可用该凭据登录成功；③ 登录后能完成一次 Cluster 的列表查询与一次登记，并在界面上看到结果；④ 已认证访问 `GET /api/health` 返回 `200 {"status":"ok","database":"ok"}`。
- **AC-05（prod 环境与 dev-only 面不可达）**：生产运行中 `CSM_ENVIRONMENT=prod`；未认证访问 `/docs`、`/redoc`、`/openapi.json` **不可达**（非 `200` 的 schema / 文档内容）；不存在任何 dev-only 自检面。
- **AC-06（认证边界与探针不越界）**：未认证访问 `GET /api/health` 与任一 `/api/clusters*` 端点 → `401 UNAUTHENTICATED`（不返回任何资源数据）；存活 / 就绪探测可被运维与编排观察到，且**不通过** `/api/*` 认证豁免实现，其响应**不含**任何资源 / 会话 / 凭据 / 数据库内容。
- **AC-07（数据持久化）**：在已部署系统中登记一条 Cluster → `docker compose stop` / `start`（及**重建容器**，如 `up` 后容器被替换）→ 该 Cluster 仍可通过界面查到；数据库数据位于**命名持久卷**，不随容器删除而消失。
- **AC-08（迁移可重复、生产无 downgrade）**：部署 / 升级步骤包含 `alembic upgrade head`；**重复执行成功且幂等**；部署产物中不存在对生产环境执行 `downgrade` 的步骤或文档指引。
- **AC-09（部署文档内容完整）**：部署文档包含并明确记录：① 前置条件；② 部署命令序列；③ 首次初始化（`alembic upgrade head` + 初始管理员建立）；④ 端到端验证步骤；⑤ 升级步骤；⑥ 数据库 `datcollate` / `datctype` / `encoding` 与 PostgreSQL 大版本；⑦ 连接池上限依据；⑧ 「仅限受控内网 / 无 HTTPS / Cookie 无 `Secure`」约束；⑨ 存活探测方式；⑩ 账号停用与运维约束（或指向 `README.md` §5.1）。
- **AC-10（暴露面最小且无默认凭据）**：部署后对 Internal IP 暴露的 TCP 端口**仅 nginx 入口**（PostgreSQL 与应用端口未直接发布到宿主 / 内网）；生产部署产物中**不存在**仓库内硬编码的数据库口令或连接串，凭据由部署时外部注入。
- **AC-11（无越界能力，§23 / R-DEPLOY-003）**：部署产物与文档中不存在 HTTPS / 域名 / 公网入口、Kubernetes / 多机 / 高可用、监控告警平台、工单、消息队列、Redis、Elasticsearch 等配置或指引。
- **AC-12（文档可复现性）**：一个**此前未接触本仓库**的运维人员，仅依据部署文档（不借助源码阅读与开发者口头补充）即可完成 AC-01 ~ AC-04 的部署与验证（口径对标 F012 AC-01 的「干净 checkout + 仅依文档」）。

**与 `project-plan.yaml > F015.acceptance_criteria` 的映射（不削弱）**：

| plan AC | 本 Handoff |
|---|---|
| CSM V1 部署在独立内网虚拟机（R-DEPLOY-001） | AC-01（+ AC-12 的可复现性） |
| 系统主要通过内网访问（R-DEPLOY-002） | AC-02（+ AC-04 的端到端可用） |
| V1 使用 Internal IP + HTTP，不自动增加公网入口 / 域名 / HTTPS（R-DEPLOY-003） | AC-03（+ AC-11 的否定性断言） |

（AC-04 ~ AC-12 为对 plan AC 的可判定细化：把 R-DEPLOY-001/002 从「结构陈述」细化为「按文档部署后可登录、可访问资源」，并把 F012 / F013 / F014 交接给 F015 的遗留项 —— prod 环境与 dev-only 面、探针、locale 记录、连接池上限、内网 HTTP 约束、migration 步骤 —— 纳入验收。**未新增产品规则、未修改任何领域规则**。）

## Assumptions

（不阻塞当前工作、可安全暂时采用；**不得当作 CONFIRMED**）

1. F012 / F013 / F014 均 `DONE`，F001 的 Cluster 端点可用；当前产品面 = 登录 / 登出 / 会话、`/api/health`、5 个 `/api/clusters*`（`README.md` §5）。
2. 目标虚拟机已具备 Docker Engine 与 Docker Compose v2，并能获取基础镜像（内网镜像源或离线导入）；部署文档只需覆盖 **CSM 自身**的部署，不覆盖容器运行时的安装。
3. 部署形态为**单机单应用进程**：V1 无多 worker / 多机需求（DEC-015：总量约 10⁵、并发约 50；ADR-0005 Consequences 会话表使多进程需共享存储，V1 单进程）。
4. 默认路径为「在 VM 上从本仓库构建镜像」；是否使用预构建镜像 / 内网 registry 属实现与运维选择，不改变产品行为（见 NQ-4）。
5. 前端以**生产构建产物**（静态文件）由 nginx 提供，不引入新前端框架 / 路由库。
6. 生产 compose 与 `docker-compose.dev.yml` **分离**；dev compose 保持 dev 用途。
7. F015 不新增 / 修改任何产品 API 与契约；前后端契约不变。
8. 当前**不存在**备份机制；在无明确规则前，部署文档不承诺备份能力（见 PROPOSED-1 / NQ-1）。
9. 宿主防火墙、网络可达性、VM 磁盘容量由运维方负责；F015 的责任边界是「CSM 产物不引入公网入口、不发布多余端口」。
10. `CSM_ENVIRONMENT` 目前只是标签（`backend/app/config.py:27`）；「prod 下关闭文档面」的具体实现形式是架构 / 实现细节，不在本 Handoff 指定。

## Proposed Rules

**PROPOSED-1（需用户裁定，非 CONFIRMED）**：是否要求部署文档提供**备份 / 恢复步骤**（如 `pg_dump` / `pg_restore`、建议周期、恢复演练）。当前无任何已确认规则；F015 **不实现、不承诺**。需注意其运维后果：系统被定位为「替代 Excel 的可信事实库」，一次磁盘 / 卷事故会造成登记事实丢失。本 Feature 不据此扩大范围。

**PROPOSED-2（需用户裁定，非 CONFIRMED）**：是否需要**开机自启 / 崩溃重启**（compose `restart: unless-stopped` 或 systemd 单元）。属运维偏好而非已确认产品规则；F015 建议提供 `restart` 策略并在文档记录，但不作为产品验收项。

**PROPOSED-3（需用户裁定，非 CONFIRMED）**：生产是否保留**需认证**的 API 文档面。当前产品裁定为「prod 关闭」（#15）；若组织需要在内网保留开发者文档，可改为「仅认证后可达」，但这需要显式裁定（见 NQ-3）。

**PROPOSED-4（需用户裁定，非 CONFIRMED）**：是否需要「一键部署脚本」。当前 AC-12 只要求**文档化步骤可复现**，不承诺单条命令；是否额外提供脚本属实现选择。

**PROPOSED-5（需用户裁定，非 CONFIRMED）**：部署文档是否记录**数据保留 / 归档策略**。当前无规则（与 F014 PROPOSED-3 同一悬空问题），在无明确规则前**一律保留、不清理**。

## Open Questions

### Blocking

**无。**

逐条对照阻塞判定标准（不确认就无法确定本次功能范围 / 导致两种明显不同的用户行为 / 改变核心领域关系 / 导致验收标准无法定义）：

| 候选问题 | 判定 | 依据 |
|---|---|---|
| F015 是「产物 + 文档」还是「仅文档」 | **非阻塞**：唯一自洽读法只有一种 | R-DEPLOY-001 + DEC-016（docker-compose 打包）+ M1 `completion_criteria`「可在独立内网虚拟机运行」+ F012 Handoff 显式把生产打包列为 F015（Confirmed #1） |
| 探针机制如何落地 | **非阻塞**：已被 F013 显式交给 F015，且产品侧只需给边界约束 | F013 PROPOSED-4 / REQUIRED #8 / Constraints #10：「F015 探针须走产品认证面之外的机制」+「不得把端点放到 `/api` 之外（F015 探针除外，且不得属产品契约）」→ 两个候选机制均已获准，产品只需固定「不得新增豁免、不得返回产品数据」 |
| 生产是否关闭 `/docs`、`/redoc`、`/openapi.json` | **非阻塞**：可由既有规则与本 Handoff 裁定确定 | F013 REV-01 已把该取舍交给 F015；无任何已确认需求要求向未认证访问者提供 API 文档；关闭不违反任何已确认规则（#15） |
| 「一条命令启动」是否为硬性要求 | **非阻塞**：无已确认规则 | 已确认的只有「可在内网虚拟机运行」；本次以 AC-12「仅依文档可复现」替代，未削弱 plan AC（AC-03 说明） |
| 备份 / 恢复是否属于验收 | **非阻塞**：无已确认需求 | 属「本次未涉及」+ PROPOSED-1；不影响本次范围与 AC 判定 |
| 生产数据库 locale / 版本 / 连接池是否需文档化 | **非阻塞**：已确认规则直接给出 | F012 Handoff Q5 + `README.md` §7 + 架构规模假设（Confirmed #9 / #10） |
| `CSM_ENVIRONMENT=prod` 是否必须 | **非阻塞**：F012 Review 已登记为 F015 进入条件 | F012 Review Follow-up 1（Confirmed #7） |

### Non-blocking

- **NQ-1（备份 / 恢复）**：是否需要（PROPOSED-1）。在无规则前部署文档不承诺备份；若需要，应由用户裁定后作为独立小范围工作，不并入本次 AC。
- **NQ-2（开机自启 / 重启策略）**：见 PROPOSED-2。属运维偏好；建议 Architect 在部署产物中给出 `restart` 策略并记录，不构成产品验收项。
- **NQ-3（生产 API 文档面）**：当前裁定为「prod 关闭」（#15）。若组织需要内网开发者文档，需用户显式裁定为「仅认证后可达」；届时须同步 URE 更新对应 AC 与部署文档，**不得**为此在 `/api/*` 上新增豁免。
- **NQ-4（镜像获取方式）**：在 VM 上构建 vs 内网 registry 预构建。属实现 / 运维选择，不影响 AC（AC-12 只要求文档可复现）。
- **NQ-5（探针机制二选一）**：产品倾向 (a) 容器 / 运行时级探测（不新增 HTTP 面）；若 Architect 选 (b)，路径必须在 `/api` 之外、仅 GET、不属产品契约、不检查数据库内容（可返回「进程存活」而非「数据库可用」）。
- **NQ-6（应用与数据库的启动顺序 / 就绪等待）**：应用在 PostgreSQL 未就绪时的行为（重试 / 依赖条件）属实现细节；产品只要求 AC-01 / AC-04 在按文档启动后成立。
- **NQ-7（升级与回滚）**：`alembic upgrade head` 属验收（AC-08）；应用镜像层面的回滚是否需要文档化流程，属非阻塞（无已确认规则；与 CI/CD 同属「本次未涉及」）。
- **NQ-8（F012 F-03 的环境断言形式）**：`prod` 下「dev-only 面不可达」如何断言（配置校验 / 启动期失败 / 结构 guard）属架构硬化，见 Architecture Handoff #3。
- **NQ-9（部署文档落点）**：`docs/deployment/` 新目录 vs `README.md` 新章节。需满足「同一份详细信息只维护一个权威来源」（`AGENTS.md` §4）；`README.md` 保留开发流程与指向。
- **NQ-10（`README.md` §8 常见问题的新增项）**：部署后常见故障（端口占用、locale 不符、卷权限、健康检查失败）是否汇总，属非阻塞。

## Architecture Handoff

以下为 Architect 需解决的技术设计问题（本 Handoff 不选择实现方式、不定义文件、不编写配置）：

1. **交付层判定**：`project-plan.yaml > F015.layers` 当前为空，请依本 Handoff 判定 `database` / `backend` / `frontend` / 部署产物（若无对应字段则说明落点）。预期 `database: false`（无 Schema / migration 变更）；`backend: true`（prod 环境配置、文档面关闭、探针实现）；`frontend: true`（生产构建产物接线）；以及**部署产物（compose / Dockerfile / nginx 配置 / 部署文档）的归属与落点**——当前 `layers` 无该项，请明确其记录方式。
2. **生产编排形态**：文件落点（新增生产 compose 还是区分 profile）、镜像构建方式（Dockerfile 与构建上下文）、服务依赖 / 启动顺序、数据卷命名、端口发布策略（仅 nginx 入口）、`restart` 策略（NQ-2）。
3. **`prod` 环境与 dev-only 面关闭的落实与验证**（F012 F-03 / F013 REV-01）：`CSM_ENVIRONMENT=prod` 的强制方式、`/docs` / `/redoc` / `/openapi.json` 的关闭或保护方式，以及**可失败的验证**（AC-05）。
4. **探针设计**：在 (a) 容器 / 运行时级 与 (b) `/api` 外 HTTP 路径之间选择并给出理由；证明不新增 `/api/*` 豁免、不返回产品数据；给出可失败测试（AC-06，并保证 F013 AC-01 / AC-13 不回归）。
5. **生产凭据与 DSN 注入**：外部注入方式（环境文件 / 编排 secrets 机制），以及「产物内无生产默认口令」如何被验证（AC-10）。
6. **数据持久化与验证方式**：命名卷 / 挂载点设计，以及「容器重建后数据仍在」的可复现验证方法（AC-07）。
7. **migration 的执行点与升级流程**：`alembic upgrade head` 由 entrypoint 触发还是显式运维步骤（含「可重复执行」的保证），以及生产禁止 `downgrade` 的落实与文档化（AC-08）。
8. **locale / encoding / PG 版本的固定方式**：生产镜像如何固定 `datcollate` / `datctype` / `encoding`，以及把「大小写敏感」回归断言落到生产产物上的方式（架构 Risk #1；`README.md` §7）。
9. **连接池上限的确定与记录**：与 PostgreSQL `max_connections` 的关系，以及文档化位置（AC-09）。
10. **部署文档落点与权威来源**：`docs/deployment/` 与 `README.md` 的分工（NQ-9）；`docker-compose.dev.yml` 的用途表述是否需要同步修订。
11. **端到端验收方法**：在真实内网虚拟机或等价环境上验证 AC-01 ~ AC-12 的步骤与证据形式（含从内网另一台机器访问 Internal IP、未认证 401、dev-only 面不可达、数据持久化）。测试 / 验收需要哪一层证据请在 Handoff 中明确（NQ-5 / NQ-7 亦在此收口）。
12. **不在本 Feature 的边界声明**：请在设计文档中显式声明不引入 HTTPS / 域名 / 公网入口 / 多机 / K8s / 监控告警栈 / Redis 等（AC-11），以及不新增任何业务功能或领域规则。

## Handoff Status

`READY FOR ARCHITECT`

无 Blocking 问题。题面列出的 5 项重点澄清（交付边界、探针、文档面、HTTP 明文与 Cookie 约束、环境与配置）已逐条给出产品结论（Confirmed #1、#7 ~ #15、#17 ~ #19、AC-01 ~ AC-12）：

- **交付边界 = 可运行的生产部署产物 + 部署文档 + 运行约束**，而非仅文档（#1）；
- **探针 = 必须存在，但走产品认证面之外的机制**，不得新增 `/api/*` 豁免、不得返回产品数据；倾向容器 / 运行时级探测（#14、AC-06）；
- **`prod` 关闭 `/docs`、`/redoc`、`/openapi.json`**（#15、AC-05）；
- **「仅限受控内网 / 无 HTTPS / Cookie 无 `Secure`」写入部署文档并作为验收项**（#17、AC-09、AC-03）；
- **`CSM_ENVIRONMENT=prod` 强制、DSN 外部注入、初始管理员步骤、数据卷持久化、`alembic upgrade head` 且禁止生产 downgrade**（#7 ~ #12、AC-04、AC-07、AC-08）。

以上全部可由已确认来源推导（R-DEPLOY-001~003、§20、§22、§23、§25、ADR-0001 / 0002 / 0005、DEC-015 / DEC-016、F012 Handoff Q5 与 Review Follow-up、F013 AC-11 / AC-13 与 PROPOSED-4、F013 REV-01），**未新增或修改任何产品规则、领域对象、唯一性或状态语义**。PROPOSED-1 ~ PROPOSED-5 与 NQ-1 ~ NQ-10 均不阻塞架构设计，其中 PROPOSED-1（备份）与 PROPOSED-3（生产文档面）建议由用户确认后由协调器更新 `project-plan.yaml` / 相关文档。