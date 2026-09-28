# ADR-001 技术栈与运行时

- **决策 ID**：D-ARCH-STACK
- **状态**：ACCEPTED（2026-09-25，用户批准，revision 8 / BQ-V）
- **影响**：全部 Feature（affects=ALL）

## 背景

CSM V2 是 HPC/AI 运维内部资源管理平台，约 1,000 台/集群量级，以表格与表单密集的资源登记、查询、维护为主；需要整单原子提交、字段级错误、服务端三角色鉴权、操作审计、服务端分页与模糊搜索。团队需要易维护、强校验、生态成熟的技术栈。

## 决策

- **后端**：Python 3.12 + **FastAPI** + Pydantic v2 + SQLAlchemy 2.0（ASGI：Uvicorn / Gunicorn+Uvicorn worker）；测试 pytest + httpx。
- **前端**：**Vue 3 + TypeScript + Vite** + Element Plus + Pinia + Vue Router；HTTP 使用 axios；测试 Vitest。
- 前后端通过 JSON over HTTP 通信（契约见 ADR-003）。
- P0 **不引入数据库迁移工具**（见 ADR-002）。

## 备选与取舍

| 备选 | 取舍 |
| --- | --- |
| Java 21 + Spring Boot 3.x | 事务/校验/RBAC 生态成熟，但用户明确选择 Python/FastAPI |
| Node/NestJS、Go | 均可行；非用户所选 |
| 前端 React + Ant Design | 用户明确选择 Vue 3 + Element Plus |

## 结论与影响

- FastAPI 自带 OpenAPI，利于 `docs/api/<feature>.md` 契约与字段校验；Pydantic v2 契合整单原子与字段级错误。
- Vue 3 + Element Plus 适合表格密集后台，键盘/表单交互开箱较全。
- 风险：栈与团队能力需匹配；由用户在批准时确认。