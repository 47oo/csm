# F013 用户与角色管理 — Test Report（BQ-Y 后独立重测）

> Status: READY FOR REVIEW
> Document Type: Test Report（独立验证）
> Feature: F013（Epic E8，P0）
> 候选 HEAD：`d78b940`（分支 `feature/F013-user-role-management`）
> 测试日期：2026-09-26
> 依据：`requirements-v2.md` §4.9/§10 场景 72–81/§11.1 BQ-Y；`docs/api/F013.md`；`docs/architecture/F013-user-role-management.md`；`docs/database/F013.md`
> 前一轮记录 `docs/project/reports/F013-test-report.md`（候选 `206261e`/`b99e619`）因实现变更被本报告取代。

---

## Task
- Feature：F013 用户与角色管理。
- 角色：Tester（独立验证；不改业务实现）。
- 范围：BQ-Y 内置 `admin` 保护 + 场景 75–81 回归；后端/Frontend 测试与构建。

## Basis
- 产品：`requirements-v2.md` §4.9.1–12、§10 场景 75–81、§11.1 BQ-Y（内置默认管理员固定 `admin`，不可删除/禁用/改角色，可改口令；不设通用最后管理员限制）。
- 契约：`docs/api/F013.md`（`PROTECTED_ADMIN` 409；用户名规则；乐观锁；越权；首登改密）。
- 架构/Schema：`docs/architecture/F013-user-role-management.md` §4.6；`docs/database/F013.md` §2.1/§3/§4。
- 候选提交：`d78b940 feat(F013): protect built-in admin account (BQ-Y)`。

## Environment
- 宿主机：无 pip / 无本机 PostgreSQL；有 Docker、Node v22.23.2、pnpm 11.21.0。
- 数据库：独立 `postgres:16` 容器 `csm-f013-pg`（独立网络 `csm-f013-retest`）；测试库 `csm_test`、探针库 `csm_probe`。
- 后端镜像：`docker build -t csm-backend-retest backend`（真实构建）。
- 探针：宿主机 `python3` + `requests`，经真实 `uvicorn`（容器 `csm-f013-api`，端口 18013）+ 真实 PostgreSQL，非 Mock。
- 测试后清理自建容器/网络/镜像（保留环境中原有 `csm-pg`）。

## 实际执行的命令与结果

| # | 命令 | 结果 |
| --- | --- | --- |
| 1 | `docker build -t csm-backend-retest backend` | 成功（层缓存命中，退出码 0） |
| 2 | `docker run --rm --network csm-f013-retest -v "$PWD/backend:/app" -w /app -e CSM_DATABASE_URL=postgresql+psycopg://csm:csm@csm-f013-pg:5432/csm_test csm-backend-retest pytest -q` | **41 passed**, 1 warning, 8.90s |
| 3 | `cd frontend && pnpm install` | Already up to date（退出码 0） |
| 4 | `cd frontend && pnpm test` | **Test Files 5 passed / Tests 88 passed**, 1.46s |
| 5 | `cd frontend && pnpm build` | 成功（vue-tsc + vite，1709 modules；仅 chunk >500kB 警告） |
| 6 | `python3 scripts/init_db.py`（探针库，执行两次） | 首次预置成功；二次幂等无错。DB：`users=1`（`admin`/`is_builtin=t`）、`reserved_usernames=1`、`audit_log=1`（`bootstrap.create_admin`） |
| 7 | 独立 HTTP 探针 `/tmp/f013_probe.py`（45 项） | **45/45 PASS** |
| 8 | 补充探针 `/tmp/f013_selfdel.py`（删除自身审计） | PASS |

### 后端 pytest 覆盖
场景 72–81 集成测试 + 数据库约束测试（用户名格式/唯一、`reserved_usernames` 只增不删、`audit_log` append-only、CASCADE/SET NULL、乐观锁、会话过期谓词、`is_builtin` 默认 false）。共 41 项全部通过。

### 前端 Vitest
`validation.test.ts`（含 `isProtectedAdmin`：`admin`=true；`Admin`/`ADMIN`/`admin1`/`root`/`''`=false）、`client.test.ts`（409 `PROTECTED_ADMIN` 原样抛出）、`users.test.ts`、`auth.test.ts`、`router/index.test.ts`，共 88 项通过。

## 独立探针结果（真实 HTTP + 真实 PostgreSQL）

### BQ-Y 内置管理员保护（核心）
| 验证项 | 结果 |
| --- | --- |
| 初始化预置用户名为 `admin`，`is_builtin=true`，`must_change_password=true` | PASS |
| 删除内置 `admin` → `409 PROTECTED_ADMIN`（`application/problem+json`） | PASS |
| 禁用内置 `admin` → `409 PROTECTED_ADMIN` | PASS |
| 修改内置 `admin` 角色 → `409 PROTECTED_ADMIN` | PASS |
| 三种拒绝后数据不变（`role/status/version/is_builtin` 前后一致） | PASS |
| 内置 `admin` 可重置口令（旧口令失效、新口令可登录） | PASS |
| 普通 admin（且为唯一其它 admin）可改角色 / 可禁用（再启用）/ 可删除 | PASS |
| 再建普通 admin 后删除仍允许（无“最后管理员”限制） | PASS |

### 场景 75–81 回归
| 场景 | 验证项 | 结果 |
| --- | --- | --- |
| 75 | 创建用户、角色登录；非法用户名（空格/连字符/下划线/空/超长/中文）422；口令策略 422；大小写敏感（`Admin` 可建）；历史用户名复用 409 USERNAME_TAKEN | PASS |
| 76 | PATCH 含 `username` → 400 INVALID_REQUEST；改角色后 `version` 自增；内置 `admin` 角色不可改 | PASS |
| 77 | 删除后不能登录；用户名不复用（409）；`user.delete` 审计保留；内置 `admin` 不可删 | PASS |
| 78 | 管理员重置口令：新口令可登录、旧口令失效；自助改密清除首登标记且当前会话保留 | PASS |
| 79 | 禁用后登录 403 ACCOUNT_DISABLED、记录保留；启用恢复；重复禁用 204 幂等；内置 `admin` 不可禁 | PASS |
| 80 | viewer 调用新增/删/改/禁全部 403 FORBIDDEN；内置 `admin` 数据不变 | PASS |
| 81 | `audit_log` append-only（DB 触发器拒绝 DELETE）；操作含操作者/时间/关键变更 | PASS |

### 其它边界
| 验证项 | 结果 |
| --- | --- |
| 首登未改密访问 `/users` → 403 PASSWORD_CHANGE_REQUIRED | PASS |
| 乐观锁过期 `version` → 409 VERSION_CONFLICT | PASS |
| 未认证访问 `/users` → 401 UNAUTHENTICATED | PASS |
| 非内置 admin 删除自身：用户行删除、审计行保留且 `actor_user_id` 置 NULL（快照 `selfdel`） | PASS（新增 `db.flush()` 生效） |

### DB Schema 逐项核对（探针库 `\d`/`information_schema`）
- `users` 含 `is_builtin boolean NOT NULL DEFAULT false`；`chk_users_username_format ^[A-Za-z0-9]{1,128}$`、`chk_users_role`、`chk_users_status`、`chk_users_version`、`uq_users_username_key` 均存在，与 `docs/database/F013.md` §2.1/§5.2 一致。
- 删除用户后 `reserved_usernames`（含 `root`/`todelete`）留存 → 用户名不复用；`audit_log` 全部保留。

## 验收映射（PASS / FAIL / BLOCKED / NOT TESTED）
- 场景 72–74（登录/禁用登录/登出）：**PASS**（pytest + 前轮契约，覆盖于 41 项）。
- 场景 75–81：**PASS**（pytest + 独立 HTTP 探针）。
- BQ-Y 内置 `admin` 保护：**PASS**（探针全项 + 后端测试）。
- 用户名规则/不可改名/不复用、乐观锁、越权、首登改密、审计 append-only：**PASS**。
- 前端交互与构建：**PASS**（88 单测 + 构建）；浏览器真实点击流 **NOT TESTED**（无 headless browser）。

## Defects
| ID | Severity | Layer | Location | 期望与实际 | Owner | 必须修复 |
| --- | --- | --- | --- | --- | --- | --- |
| F013-T-01 | — | — | `backend/README.md` | 前轮“docker 命令收集 0 测试”已修复（README 改为挂载源码）；本轮实测收集 41 项 | Backend | 已关闭 |
| F013-T-02 | — | — | 业务规则 | 前轮“最后启用 admin 可改角色致无管理员”由 BQ-Y 裁定：仅内置 `admin` 受保护，系统由内置账号保证始终有管理员；本轮验证无缺口 | Product/Architect | 已关闭 |
| F013-T-06 | NOTE | DB/运维 | `users.is_builtin` | 保护标志由初始化预置写入。若某库在 BQ-Y 之前已预置过 `admin`（`is_builtin=false`），本版初始化因“已存在 admin 则跳过”不会回填，保护将不生效。本 Feature 为绿地新建、P0 无迁移，当前无此类历史库；仅提示非绿地升级路径需另行评估。 | Backend/协调器 | 否 |
| F013-T-07 | NOTE | Frontend | `validation.ts isProtectedAdmin` | 前端以 `username === 'admin'` 判定禁用交互，服务端以 `is_builtin` 为权威；对固定内置账号二者一致，且服务端最终校验。 | Frontend | 否 |

无 BLOCKER/HIGH/MEDIUM 必须修复项。

## 未验证项
- 浏览器真实点击流（无 headless browser）：以真实 HTTP API 冒烟 + 前端契约路径/单测替代。
- `docker compose up` 整体编排未端到端启动（分别验证 init 幂等与 uvicorn 真实运行）。
- P95 性能目标未压测（超出本 Feature 功能验收）。

## Issues / Next
- 无阻塞项。建议 Coordinator 进入 Review，候选 HEAD `d78b940`。
- 建议 Review 关注：`F013-T-06` 的非绿地升级回填策略（当前不阻塞）。

## 结论
BQ-Y 内置 `admin` 保护与场景 75–81 经独立、真实 PostgreSQL + 真实 HTTP 验证全部通过；后端 41、前端 88 测试及构建通过；工作区在 `d78b940` 干净。**READY FOR REVIEW**。

## Git（只读）
以下为本次实际执行的 Git 只读命令（未执行任何写命令）：
```text
GIT: git rev-parse --short HEAD        # -> d78b940
GIT: git status --porcelain            # -> 空（clean）
GIT: git log --oneline -3              # -> d78b940 / e71d503 / 206261e
GIT: git show --stat d78b940
GIT: git show d78b940
GIT: git rev-parse HEAD                # -> d78b940bd1954055fe09df0fb61f104a928d4621
GIT: git branch --show-current         # -> feature/F013-user-role-management
GIT: git log --oneline -3
```
注：以上 `git status` 于写入本 Test Report **之前**执行，确认候选 HEAD `d78b940` 工作区 clean；本报告落稿会使工作区多出该文件改动（未提交）。