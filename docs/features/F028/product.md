# F028 一期变更集成验收 — Product

- Feature：F028（P0，M19）；状态：READY FOR ARCHITECT
- 需求：requirements revision 11 §23.2、§31 T85–T99、§32–§33、§30
- 依据：CHG-010；plan revision 14；F016 整体验收；F026/F027 交付
- 依赖：F026、F027（DONE）

## 1. 目标

在真实部署拓扑（Nginx → Frontend / FastAPI → PostgreSQL）上验证集群范围授权的端到端行为，并承接候选 revision 14 的一期整体验收：

- T85–T89、T91、T93–T95、T97–T98 的端到端证据；
- T90/T92/T96/T99 的基座回归（F026 已交付）；
- T01–T84 关键回归（权限、软删、导入、API Key、搜索、Dashboard、审计、迁移）；
- T36 备份覆盖 Audit；
- 更新 `project.acceptance=COMPLETE`（由协调器核验）。

## 2. 范围

In scope：真实 Compose 拓扑或等价真实栈；API 端到端；前端构建与入口；迁移/回填；备份/恢复；证据归档。
Out of scope：新增业务规则/端点/Schema；修改 F026/F027 语义；F027 已覆盖的逐域矩阵重复；发布授权。

## 3. 验收标准

- A1：`docker compose up -d` 或已记录的等价真实栈可启动 Nginx→Frontend/FastAPI→PostgreSQL，健康检查 200，alembic head `0015_user_cluster_authorizations`。
- A2：T85–T89 端到端：未授权列表/详情/写/搜索/Dashboard/导入按 §23.2 收敛，无泄露、无残留。
- A3：T91/T93–T95：撤销/角色变更即时生效；零授权空态；INACTIVE/软删/恢复；API Key 继承。
- A4：T90/T92/T96/T99 回归：授权管理、Audit、回填/迁移。
- A5：T97–T98：既有角色矩阵、完整性、已删对象权限不回归。
- A6：T36：备份包含 Audit；恢复后行数/内容/触发器/版本一致；append-only 仍生效。
- A7：前端构建通过，受限范围下既有页面可加载；F026 中“范围尚未生效”提示已移除/更正。
- A8：证据归档（运行日志、pytest、T36 日志）；未执行项明确记录。
- A9：`project.acceptance` 由协调器在证据核验后置 COMPLETE；不自动授权发布。

## 4. 环境差异

Compose 尝试已执行并记录：镜像构建可用，但 `bootstrap` 因未提供 INITIAL_ADMIN 凭据退出 2；随后使用 F016 同款等价真实栈（postgres:16 + 当前 backend 代码 + 构建后的 frontend + nginx 入口，同源 `http://localhost:18081`）。差异与限制在 Test Report 中如实记录，不将 Compose 尝试写成成功。

**Status：READY FOR ARCHITECT**
