# F016 一期集成验收与交付 — PRODUCT 阶段报告

- **Feature**：F016 一期集成验收与交付（FEATURE，P0，M7 一期整体验收；deps F001–F015）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`
- **依据**：`docs/product/requirements-v3.md` revision 3 CONFIRMED（§22、§30、§31 T01–T41、§32、§33、§35.1/§35.2）；`docs/project/project-plan.yaml` plan_revision 4 F016（用户 2026-10-06 批准，含 `project.acceptance`）；F001–F015 product/test-report/review-report（均 DONE）；`docs/project/project-state.md`、`git-workflow.md`；`compose.yaml`、`deploy/backup/`。

## 1. 范围与排除项

### 1.1 目标
在真实 Docker Compose（Nginx → Frontend / FastAPI → PostgreSQL，§30）上执行 §31–§33 跨功能验收，确认一期能力集成可用、可回答目标查询、备份覆盖 Audit，并据 §32 逐项上线验收。产出 `project.acceptance.evidence`，协调器核验后置 `COMPLETE`。

### 1.2 本次范围
- **真实 Compose 验收执行**（§30）：`docker compose up -d`（db→migrate→bootstrap→backend→frontend→nginx），经入口 Nginx 访问。
- **T01–T41 映射与证据**（§31）：逐条标注权威 Feature、判据与证据；已由权威 Feature 真 PG/真 HTTP 执行者复用；跨功能/集成耦合者在 Compose 重跑。
- **§33 目标查询端到端**（Q1–Q9）。
- **§32 上线验收清单逐项**（C1–C15）。
- **备份覆盖 Audit（T36）**（§22/§31）：备份含 audit_logs，恢复后审计完整、append-only 保持。
- **跨功能耦合回归**：T11/T16/T19/T22/T23/T24/T25/T26/T27/T29/T32/T37/T40/T41。
- **验收证据写入 `project.acceptance`**。

### 1.3 明确排除
不新增功能/业务对象/字段/状态；不改 F001–F015 行为语义；不做发布授权；不做监控/调度/运维；不预建归档/清理；不以 Mock/SQLite 替代约束与并发证据；不把未执行预期写成 PASS。

## 2. 验收环境与执行约束

### 2.1 CONFIRMED 环境基线（§30）
Compose 拓扑（compose.yaml）：db(postgres:16)→migrate(alembic upgrade head)→bootstrap(首个 ADMIN)→backend(uvicorn, `/api/v1/health/ready`)→frontend→nginx(入口，默认 :80)。真实凭据经 .env；使用独立项目名/端口与独立验收库。

### 2.2 环境限制处理
若 `docker build`/`docker compose up -d` 不可用：如实记录，给出真实可替代栈（本机 PostgreSQL 16 + 后端 ASGI + Nginx 入口 + 前端构建产物）并说明差异；不得伪造 Compose PASS，不得以 Mock 替代约束/并发证据。无法执行部分按 BLOCKED 记录条件/责任者/恢复动作。

### 2.3 验收数据集（PROPOSED）
至少 2 Cluster、cn001（BM，管理网+IB 两 Interface/IP）、vm001（VM，Host=pve01）、pve01（BM，多 VM）、含 gateway/RESERVED/禁用地址的 Network 与 AUTO/MANUAL 池、绑定与未绑定 IP、Service/Endpoint、导入样例。由执行者按已签核契约构造，不新增业务规则。

## 3. T01–T41 映射与证据

> 判据以各 T 权威 Feature 契约为准；F016 不重定义。`复用`＝引用权威 Feature 真 PG/真 HTTP 证据并在 Compose 确认端点可达；`重跑`＝在 F016 集成环境端到端执行。

| T | 权威 Feature | 判据摘要 | 执行方式 |
| --- | --- | --- | --- |
| T01/T02/T03 | F004 | 同 Cluster hostname 重复失败/跨 Cluster 允许/软删后可重建 | 复用+Compose 确认 |
| T04/T05/T06 | F010 | 重复 IP 失败/跨 Cluster 允许/非 CIDR 失败 | 复用 |
| T07 | F010 | 自动分配不冲突（含并发，真提交） | 复用 F010 B40 |
| T08/T09 | F006 | VM Host 为 VM/跨 Cluster 失败 | 复用 |
| T10 | F010 | Interface 跨 Cluster 绑 IP 失败 | 复用 |
| T11 | F004/F014 | 归一化一致；API 与导入同源 | **重跑** |
| T12 | F007 | 同 Resource Interface 名重复失败；删除后可重用 | 复用 |
| T13 | F003 | Cluster code 大小写不敏感/全局唯一/删除不复用/不可改 | 复用 |
| T14 | F008 | Network 重叠失败/跨 Cluster 允许；有 Pool/IP 禁改 CIDR/Cluster | 复用 |
| T15 | F009 | Pool 越界/逆序/重叠失败；AUTO/MANUAL/RESERVED 行为 | 复用 |
| T16 | F008/F010 | INACTIVE 禁分配；关 auto_allocate 禁自动；耗尽不切换 | **重跑** |
| T17/T18 | F010 | 池外允许/gateway/RESERVED 失败/AUTO 升序；未绑定占用/解绑不释放/删缩池不回收/容量分口径 | 复用 |
| T19 | F004/F006 | VM Host 规则；换 Host 记审计；Resource 不可改 Cluster/类型 | **重跑** |
| T20 | F007 | parent_interface 跨 Resource/自引用/环失败；MAC 空不阻塞 | 复用 |
| T21 | F011 | Service 名称归一化后同 Resource 重复失败；状态默认 | 复用 |
| T22 | F010/F012 | Endpoint 校验；有引用禁解绑/转移/释放 | **重跑** |
| T23 | F007–F012/F015 | 存活引用阻止删除并返回列表；无隐式级联；类型明细跟随；Pool 例外 | **重跑** |
| T24 | F015/各域 | ADMIN 查看/恢复；不级联；标识重用/依赖仍删失败 | **重跑** |
| T25 | F002/F015 | 权限矩阵服务端执行；EDITOR/VIEWER 边界 | **重跑** |
| T26 | F002/F015 | 过期版本拒绝；审计历史操作者；不记录密码令牌 | **重跑** |
| T27 | F014 | 先校验后确认再校验；整批回滚；错误含行号/字段/原因 | **重跑** |
| T28 | F014 | VM Host 须已存在；不更新/覆盖；上限 | 复用+重跑子集 |
| T29 | F003/F008 | Cluster INACTIVE 维护；默认含停用；不级联；Network 停用仍阻分配 | **重跑** |
| T30/T31 | F010 | 地址边界；禁用范围；LOOPBACK 不入口台账 | 复用 |
| T32 | F010/F013 | 容量集合口径；Dashboard 一致；停用不清零 | **重跑** |
| T33/T34 | F009/F010 | 保留范围/网关冲突拒绝与明细；类型互换；删缩池保留来源；恢复不绕过 | 复用 |
| T35 | F009/F010 | 保留范围变更与并发分配不双成功 | 复用真并发 |
| T36 | F015/F016 | Audit 保留/无入口；删除恢复复用停用不改旧审计；**备份覆盖 Audit** | 保留复用；备份为 F016 新增 |
| T37 | F004/F007–F012 | 默认值；Role 显式 null 拒绝；接口类型不推断；API 与导入同规则 | **重跑** |
| T38 | F005/F006/F014 | 必填失败；未知 null；正整数/非负/零值；单位一致 | 复用 |
| T39 | F005/F006/F007 | cpu_cores 不含超线程；VM 不因超容量拒；speed_mbps 标称 | 复用 |
| T40 | F007/F008/F009/F011 | 名称 trim/空名控制字符失败；Interface 内部空白失败区分大小写；Network/Pool/Service 不敏感保留中文内部空格 | **重跑** |
| T41 | F008/F009/F011/F015 | 删除后名称可复用；作用域唯一；复用时旧对象恢复失败不覆盖；Cluster code 不复用 | **重跑** |

完整通过结论由 F016 TEST/集成执行与协调器核验给出；本阶段不预填 PASS。

## 4. §33 目标查询场景端到端

| # | 查询 | 路径 | 期望 |
| --- | --- | --- | --- |
| Q1 | hostname 属于哪个集群 | 搜索 hostname→Resource 含 cluster | 正确 Cluster |
| Q2 | 某 IP 是哪台机器 | 搜索 IP→IPAddress→Interface→Resource | 绑定返回机器；未绑定明确无 Resource |
| Q3 | cn001 管理网和 IB 地址 | Resource Detail Interfaces/IP Addresses | 两 Interface 及 IP 正确 |
| Q4 | vm001 宿主机 | VM Detail Host | pve01 |
| Q5 | pve01 下有哪些 VM | Host Resource Virtual Machines | 全部未删 VM |
| Q6 | Network 剩余可用 IP | Dashboard / capacity | 与容量端点逐项一致 |
| Q7 | IP 是否被使用 | IPAddress 绑定状态 | 状态正确；未绑定仍占用 |
| Q8 | 机器运行哪些 Service | Resource Detail Services | 列出 Service（含 Endpoint） |
| Q9 | 谁修改了服务器信息 | Activity/完整 Audit | 操作者/动作/before-after/时间 |

## 5. §32 上线验收清单

C1 创建 Cluster/BM/VM 并关联 Host；C2 维护 Interface/Network/Pool/Service；C3 手动与自动分配 IP；C4 按 hostname/IP/Cluster/Service 找到 Resource；C5 详情显示；C6 阻止重复/跨 Cluster/非法 CIDR；C7 逻辑删除及 ADMIN 恢复；C8 Audit Log；C9 基础权限；C10 本地登录；C11 版本冲突检查；C12 CSV/.xlsx 导入；C13 Network/Pool/Endpoint/恢复约束；C14 审计持续保留且纳入备份；C15 §31 与以上均有真实证据，全部必需能力不被删除。

## 6. 备份覆盖 Audit（T36，F016 新增验证）
1) 产生真实写入并确认 audit_logs 有行。2) 执行 `deploy/backup/pg_dump.sh`，产物非空。3) `restore.sh` 恢复到新库。4) 恢复库 audit_logs 行数与关键字段一致；append-only 触发器存在且无修改/删除/清空路径。5) 恢复库后端 `/api/v1/health/ready` 200、`alembic current`=head。不得宣称 Audit 覆盖而无实际恢复后证据。

## 7. 不变量（I-1…）
- I-1 证据真实（未执行/受限项标 NOT TESTED/BLOCKED）。
- I-2 不夸大（不以局部 PASS 拼接整体）。
- I-3 约束/并发证据来自真实 PostgreSQL，不用 Mock/SQLite。
- I-4 环境限制如实记录。
- I-5 不改 F001–F015 已 DONE 行为语义；发现问题退回责任 Feature。
- I-6 不新增业务规则。
- I-7 验收数据可清理（独立项目/库/卷）。
- I-8 acceptance 不可虚报；COMPLETE 仅在协调器核验后写入。
- I-9 上线条件≠发布授权。

## 8. 可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | Compose up 链路可用且 `/api/v1/health/ready` 经 Nginx 200；否则记录限制与真实替代栈，不伪造 PASS | §30 |
| A2 | 验收数据就绪覆盖 §31–§33 触发条件 | §32/§33 |
| A3 | T01–T41 映射完整且有证据来源；集成者已重跑并给结果 | §31 |
| A4 | 跨功能耦合用例在集成栈端到端通过 | §31/§32 |
| A5 | §33 Q1–Q9 端到端可回答 | §33 |
| A6 | §32 C1–C15 逐项满足且有真实证据 | §32 |
| A7 | 备份覆盖 Audit：恢复后审计完整、append-only 保持 | §22/T36 |
| A8 | 权限矩阵集成栈服务端执行，401 先于 403 | §23/T25 |
| A9 | 导入集成栈：先校验后确认再校验、整批回滚、错误明细、Host 须已存在、上限 | §24/T27/T28 |
| A10 | 并发证据引用/复核真实 PG 真提交 | §31/T07/T35 |
| A11 | project.acceptance 写入 COMPLETE + 真实 evidence，协调器核验 | project-state §1 |
| A12 | 未改 F001–F015 契约/实现语义 | plan F016 |
| A13 | 环境限制如实记录（含替代栈差异） | §2.2 |
| A14 | 验收后清理独立项目/库/卷，无残留 | 环境纪律 |

## 9. 依赖与未决问题
依赖均已 DONE：F001–F015。BLOCKING：无。

PROPOSED（非阻塞，交 Architect/CONTRACT）：
- O-1 F016 layers/api_required：PROPOSED api_required=false；layers 视验收脚本/夹具而定。
- O-2 验收脚本/夹具落点：PROPOSED 复用 backend/tests/integration + scripts；evidence 指向 Test Report 与 project.acceptance。
- O-3 §33 多跳查询落点：PROPOSED 用既有 Resource/Cluster Detail/Dashboard/搜索组合，不新增场景专用接口。
- O-4 备份恢复 Audit 断言：PROPOSED 容器内 psql/SQLAlchemy 断言行数与字段一致性 + append-only 触发器存在。

## 10. 交 Architect 的输入
layers/api_required（O-1）；验收执行方案（Compose 启动/健康/数据/复用重跑边界/§33/§32 证据落点）；T36 备份验证（O-4）；证据与 acceptance 组织（A11/I-8）；环境限制预案（§2.2）。边界：不新增功能/规则、不改 DONE 语义、不以 Mock 替代约束并发证据。

## 11. 结论与下一步
无 Blocking Questions。**READY FOR ARCHITECT**。下一步 ARCHITECTURE 确定 layers/api_required（O-1）、验收执行方案与 T36 备份验证（O-2/O-3/O-4），定义证据落点与 project.acceptance 写入路径；TEST 阶段细化可执行步骤与断言，禁止把未执行预期写成 PASS。
