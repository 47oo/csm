# F001 工程与部署底座 — PRODUCT 阶段报告

- **Feature**：F001 工程与部署底座（ENABLER，P0，M1）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-06）
- **依据**：`docs/product/requirements-v3.md` revision 3（§25–§31、§22）；`docs/project/project-plan.yaml` plan_revision 4，F001 条目（已批准）；Product Manager 阶段交接（协调器核验后持久化）。

## 确认条款

§26 数据库、§27 数据完整性、§29 技术栈、§30 部署、§31 测试均为 CONFIRMED；§25 统一前缀 `/api/v1/` 约束工程骨架预留；§22 仅作备份边界引用。六项业务决策（§35.2）CONFIRMED，本 Feature 不重开；D01/D02/D03 为专业设计输入（§35.3），在后续 Gate 签核，非产品阻塞。

## F001 必须遵守的已确认约束

- **技术栈与禁引入项**（§29）：React/TypeScript/Vite、Python/FastAPI/Pydantic、pytest、Nginx；一期不引入 Redis、RabbitMQ、Kafka、ElasticSearch、Kubernetes、Celery。
- **数据库选型**（§26）：PostgreSQL、SQLAlchemy 2.x、Alembic；JSONB；IP/网段优先 INET/CIDR（偏离需明确依据）。
- **扩展**（§26、§17）：pg_trgm 为已确认要求；btree_gist 等其它扩展属 D02 条件性设计选择（Database 签核时决定），不得与 §29 禁引入项混淆。
- **部署形态**（§30）：`docker compose up -d` 启动 Nginx→Frontend/FastAPI→PostgreSQL；配置、建库/Migration、初始 ADMIN 与凭据传入方式由后续设计说明。
- **凭据不入仓**（§30、§22）：真实初始凭据不入仓库；不记录或展示密码、令牌等敏感认证内容。
- **备份**（§22、§31/T36）：数据库备份必须包含 Audit（F016 以真实证据闭合 T36）；F001 仅交付 pg_dump 骨架 + 恢复文档 + 冒烟验证。
- **测试基线**（§27、§31）：集成测试基于真实 PostgreSQL（建 schema、执行 Alembic、事务级清理）；SQLite 仅纯逻辑冒烟，不作约束证据。
- **并发前提**（§31 T07/T35、§12.1）：为多连接并发与最终持久化状态断言准备测试前提。

## 可观察验收标准

1. 干净环境 `docker compose up -d` 启动 Nginx/Frontend/FastAPI/PostgreSQL 全链路；经 Nginx 访问健康检查成功，前端页面可达。
2. Alembic 基线在真实 PostgreSQL 建库成功并可回滚（upgrade→downgrade→再 upgrade 一致）。
3. 基线迁移显式启用 pg_trgm（及 Database 设计选定扩展），签核记录可查。
4. pytest 集成 fixture 可在真实 PG 建 schema、执行 Alembic、事务级清理，重复运行无残留。
5. 备份骨架可执行 pg_dump 并按文档恢复到可用实例（冒烟级）。
6. 启动所需真实凭据经环境/密钥注入，仓库无真实凭据。
7. D02 基础部分（软件版本、目录结构、迁移基线、扩展、测试基线）由 Architect/Database 在本 Feature 签核。

## ENABLER 验收边界（不宣称）

- 不宣称 Audit 数据备份覆盖（T36 由 F016 验证）。
- 不包含业务对象与 T01–T41 业务用例通过。
- 不宣称业务约束/索引/并发锁最终签核（后续 Feature 的 DATABASE/CONTRACT Gate 承接）。
- 不把容器可启动等同于生产部署批准（§32 上线验收独立）。

## 结论与下一步

无 Blocking Questions，无待用户裁定事项。下一步：ARCHITECTURE Gate，Architect 输出方案、layers、api_required 与验证策略（D02 基础部分）。
