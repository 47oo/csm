# ADR-0001: 技术栈、模块边界与部署形态

## Status

`PROPOSED`（等待用户批准；批准前不得视为已确定）

## Context

CSM V1 为 greenfield 内部资源管理平台，14 个 Feature 全部被 DEC-009 阻塞。

约束来自 `docs/product/requirements.md`：

- 必须显式建模资源类型，禁止 EAV / 通用 `resources` 表 / STI / JSONB 万能模型（§4 / §24）；
- 禁止微服务化（§23）；
- 部署在独立内网虚拟机并以 Internal IP + HTTP 提供服务（§20）；
- 界面与数据含中文；
- 优先简单、可理解、可维护的设计（§25 Simple First）。

项目无任何既有代码、ADR 或技术栈约定，因此不存在需要兼容的历史技术选择。

## Decision

采用单体分层应用：

- **Backend**：Python + FastAPI + Pydantic + SQLAlchemy 2.x + Alembic。
  分层：HTTP / 序列化 → 校验 → 领域服务（业务规则） → 数据访问 → 关系数据库。
- **Frontend**：Vue 3 + TypeScript + Vite + Element Plus。
- **模块边界**：每类资源（Cluster / BareMetal / NetworkInterface / IPAddress / VirtualMachine / Container / Service）各为一个垂直模块，独占自己的表与领域规则。**不建立通用 Resource ORM 基类或通用资源路由**。仅允许 `id` / `created_at` / `updated_at` / `deleted_at` 这类横切列的 mixin 复用（代码便利，不是数据模型统一）。
- **横切关注点**：统一错误信封、分页、软删除过滤、事务边界、认证，位于 `common/`。
- **部署**：单台内网虚拟机；nginx 提供前端静态资源并反向代理 API；应用为单个 ASGI 进程；PostgreSQL 运行于本机或受控内网。V1 使用 Internal IP + HTTP，不引入公网入口、域名或 HTTPS。

## Consequences

- 业务规则集中且可见，符合 `AGENTS.md` §2.4「业务规则必须显式表达」。
- 单进程单体部署与 R-DEPLOY-001 / 002 / 003 直接一致，无额外基础设施。
- FastAPI 的 OpenAPI 产出可自动校验 API Contract 的一致性。
- 需要团队同时具备 Python 与 TypeScript 能力。
- 认证、迁移等能力需自行组装，而非依赖框架自带。

## Alternatives Considered

- **Django + DRF**：开箱能力更多（ORM / migration / auth / admin），对 CRUD 密集型内部系统开发最快；但自带 Admin 容易诱发「顺手做一个页面」的范围蔓延，且 `convention over configuration` 会把部分业务规则藏进框架行为，与本项目「规则显式表达」原则冲突，相对更重。
- **Spring Boot / Go + React**：强类型、长期可维护、企业内常见；但对 14 个中小型 CRUD Feature 而言样板量明显偏高，Go 的 ORM / migration 生态与本项目「显式关系 + 复杂唯一性」需求匹配度一般。
- **微服务 / 前后端拆为多服务**：无任何已确认需求支撑，违反 `requirements.md` §23。

## Affected Features

F001 ~ F015（全部）；直接决定 **F012**、F013、F014、F015。

Milestone: **M1**（入口条件 DEC-009）。M1 不放行则 M2 ~ M5 全部无法启动。

## Reversibility

**中等偏低**。Greenfield 且数据模型清晰，真正难以回退的是 DEC-010 的 collation / 索引能力与 DEC-011 的 URL 形态，而不是语言本身。