# CSM — Cluster Source Manager

面向 HPC / AI 多集群环境的轻量级资源管理与查询平台，定位为 **Resource Source of Truth（资源事实数据源）**，替代分散的 Excel / 文档台账。

当前阶段：**CSM V3 一期已全部交付（F001–F036 全部 DONE），并已合入 `main`。** 交付线为 `v3.4`（标签 `v3.4` → `e972285`），`main` 为稳定发布线；`docs/project/project-plan.yaml` 记录 `project.status=DONE`、`project.acceptance=COMPLETE`、`plan_revision=24`；需求基线为 revision 15，六项业务问题与 D01–D03 专业设计输入均已确认/签核（见需求 §35）。版本边界见 `AGENTS.md` §1.1。

一期覆盖集群、统一 Resource（裸金属 / VM）、接口、IPv4 Network / IPAM、Service / Endpoint、全局搜索（含字段组合，§17.1）、审计、本地账号与基础权限、系统级角色 + 集群范围授权（§23.2）、API Key 机器凭据（§23.1）、接口侧 IP 绑定（§13.4）、二次确认对话框（§28）、逻辑删除/管理员恢复，以及 CSV / .xlsx 整批新增资源导入（§24.1）、前端 CSV 文本导入载体（§24.5）、向既有 Resource 追加 Interface / IP（§24.6），并提供离线主机信息采集脚本（§24.2–§24.4）。不包含部署执行、监控、Slurm 同步或自动化运维。

## 文档入口

| 路径 | 说明 |
| --- | --- |
| [需求基线](docs/product/requirements-v3.md) | 一期范围、字段、完整性规则、验收及待决项 |
| [领域索引](docs/product/domain-model.md) | 引用需求规则，尚非完整 Schema 设计 |
| [项目计划](docs/project/project-plan.yaml) | 唯一计划状态源；36 个 Feature 全部 DONE，整体验收 COMPLETE |
| [Feature 记录](docs/features/) | F001–F036 各自的 product / architecture / implementation / test-report / review-report 与测试证据 |
| [Backlog](docs/project/backlog.md) / [依赖图](docs/project/dependency-map.md) / [里程碑](docs/project/milestones.md) | 从计划自动生成，禁止手工维护 |
| [项目状态](docs/project/project-state.md) | 字段、阶段 Gate、统计与校验 |
| [变更控制](docs/project/change-control.md) | 用户批准、专业签核、需求变更 |
| [Git 流程](docs/project/git-workflow.md) | 约定交付线 `v3.4`、`main` 稳定发布线、Review 基线、合并与恢复 |
| [交接规范](docs/project/handoff.md) | 公共报告、证据、缺陷与 Git 声明 |
| [实现规则](docs/project/implementation-rules.md) | 前后端、数据库、导入及验证要求 |
| `.pi/` | 角色定义、领域分析 Skill、Prompt 和通用调度扩展 |

架构决策、数据库 Schema、API Contract 与部署实现均已建立（`docs/architecture/`、`docs/database/`、`docs/api/`、`compose.yaml`）；迁移覆盖 `backend/alembic/versions/0001`–`0015`，已批准 Feature 的契约见 16 份 `docs/api/F0xx.md`。技术栈（React / TypeScript / Vite、Python / FastAPI / Pydantic、PostgreSQL / SQLAlchemy 2.x / Alembic、pytest、Docker Compose / Nginx、`/api/v1/`）已确认并落地。

## 流程入口

* 首次规划 / 需求修订：`.pi/prompts/project.md`
* 已批准项目调度：`.pi/prompts/implement-project.md`
* 单个 Feature 执行：`.pi/prompts/feature.md`

首次规划先做需求澄清、能力拆分和轻量全局设计评估，再修订计划。Feature 按“需求 → 架构/API 草案 → 数据库设计与测试设计 → 契约定稿 → 前后端实现 → 独立测试 → Review → 合并”执行；一期完成还需要整体验收证据。

保留八个专业角色，按实际影响调用或复用。领域分析使用 `.pi/skills/resource-domain/SKILL.md`，完整性检查使用 `.pi/skills/data-integrity/SKILL.md`；角色报告引用权威规则。

## 本地 / 测试部署

```bash
# 复制并填写环境变量（.env 及 .env.* 均被 .gitignore 忽略，勿提交真实凭据）
cp .env.example .env      # 生产走 compose.yaml 的 build 路径

# 标准部署（需要可访问 Docker Hub / deb.debian.org）
docker compose up -d
```

受限网络（无法 `docker build`）下可用测试覆盖：本地构建镜像后

```bash
docker compose --env-file .env.test -f compose.yaml -f compose.test.yaml -p csmtest up -d --no-build
```

入口默认经 Nginx 反向代理；初始 ADMIN 由 `bootstrap` 服务创建（`INITIAL_ADMIN_*`）。

## 离线主机信息采集脚本

`scripts/collect_host_info.py` 在待登记主机上采集本机信息，生成「资源 + 网卡 + IP」导入模板 CSV（默认离线、只读）。完整参数与取值说明见 `docs/features/F024`、`docs/features/F025`、`docs/features/F032`，`python3 scripts/collect_host_info.py --help` 输出与实际行为一致。

```bash
# 裸金属：默认输出 csm_host_info_bare_metal.csv
python3 scripts/collect_host_info.py --resource-type BARE_METAL --cluster <cluster-code>

# 虚拟机：额外引用已登记的 BARE_METAL Host
python3 scripts/collect_host_info.py --resource-type VIRTUAL_MACHINE \
  --cluster <cluster-code> --host <host-hostname>

# 可选：经 API Key 直接推送（API Key 建议用环境变量 CSM_API_KEY，不落盘）
python3 scripts/collect_host_info.py --resource-type BARE_METAL --cluster <cluster-code> \
  --push --api-url http://csm.example:8080
```

脚本只引用、不创建 Cluster / Host / Network；生成的 CSV 通过导入入口的预校验后写入。脚本自身测试见 `scripts/test_collect_host_info.py`。

## 文档状态检查

环境需有 `scripts/requirements.txt` 中的依赖，然后运行：

```bash
python3 scripts/validate_project_state.py
python3 scripts/render_project_views.py
python3 -m unittest discover -s scripts -p 'test_*.py'
```

计划修改后由协调器执行 `python3 scripts/render_project_views.py --write` 更新统计和视图；默认不带 --write 只检查。状态转换使用 `validate_project_state.py --previous <修改前的V3计划快照>`，细节见项目状态规范。检查通过不等于批准来源、Git 证据或应用验收已经人工核实。
