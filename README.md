# CSM — Cluster Source Manager

面向 HPC / AI 多集群环境的轻量级资源管理与查询平台，定位为 **Resource Source of Truth（资源事实数据源）**，替代分散的 Excel / 文档台账。

当前阶段：**CSM V3 一期需求已更新至 revision 3，尚未开展完整 Feature 规划或应用实现。** 六项剩余业务问题均已按用户确认关闭；确认记录及 D01–D03 专业设计输入见需求 §35。项目计划仍为未批准的 DRAFT / incomplete 骨架。版本边界见 `AGENTS.md` §1.1。

一期覆盖集群、统一 Resource（裸金属 / VM）、接口、IPv4 Network / IPAM、Service / Endpoint、查询、审计、本地账号与基础权限、逻辑删除/管理员恢复及 CSV / .xlsx 整批新增资源导入。不包含部署执行、监控、Slurm 同步或自动化运维。

## 文档入口

| 路径 | 说明 |
| --- | --- |
| [需求基线](docs/product/requirements-v3.md) | 一期范围、字段、完整性规则、验收及待决项 |
| [领域索引](docs/product/domain-model.md) | 引用需求规则，尚非完整 Schema 设计 |
| [项目计划](docs/project/project-plan.yaml) | 唯一计划状态源；空骨架，不可调度 |
| [Backlog](docs/project/backlog.md) / [依赖图](docs/project/dependency-map.md) / [里程碑](docs/project/milestones.md) | 从计划自动生成，禁止手工维护 |
| [项目状态](docs/project/project-state.md) | 字段、阶段 Gate、统计与校验 |
| [变更控制](docs/project/change-control.md) | 用户批准、专业签核、需求变更 |
| [Git 流程](docs/project/git-workflow.md) | 约定 v3 集成分支、Review、合并与恢复 |
| [交接规范](docs/project/handoff.md) | 公共报告、证据、缺陷与 Git 声明 |
| [实现规则](docs/project/implementation-rules.md) | 前后端、数据库、导入及验证要求 |
| `.pi/` | 角色定义、领域分析 Skill、Prompt 和通用调度扩展 |

架构 ADR、数据库 Schema、API Contract 和部署实现在后续对应阶段建立，不从旧版本补齐。计划视图当前显示未规划状态。React / TypeScript / Vite、Python / FastAPI / Pydantic、PostgreSQL / SQLAlchemy 2.x / Alembic、pytest、Docker Compose / Nginx 及 `/api/v1/` 已确认；具体版本与实现设计交专业角色签核。

## 流程入口

* 首次规划 / 需求修订：`.pi/prompts/project.md`
* 已批准项目调度：`.pi/prompts/implement-project.md`
* 单个 Feature 执行：`.pi/prompts/feature.md`

本次文档更新未创建或切换 Git 分支，未启动 Feature，也不代表计划获批。

首次规划先做需求澄清、能力拆分和轻量全局设计评估，再修订计划。Feature 按“需求 → 架构/API 草案 → 数据库设计与测试设计 → 契约定稿 → 前后端实现 → 独立测试 → Review → 合并”执行；一期完成还需要整体验收证据。

保留八个专业角色，按实际影响调用或复用。领域分析使用 `.pi/skills/resource-domain/SKILL.md`，完整性检查使用 `.pi/skills/data-integrity/SKILL.md`；角色报告引用权威规则。

## 文档状态检查

环境需有 `scripts/requirements.txt` 中的依赖，然后运行：

```bash
python3 scripts/validate_project_state.py
python3 scripts/render_project_views.py
python3 -m unittest discover -s scripts -p 'test_*.py'
```

计划修改后由协调器执行 `python3 scripts/render_project_views.py --write` 更新统计和视图；默认不带 --write 只检查。状态转换使用 `validate_project_state.py --previous <修改前的V3计划快照>`，细节见项目状态规范。检查通过不等于批准来源、Git 证据或应用验收已经人工核实。
