# Review Report — F010 资源详情与关联查询

> Status: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立评审）
> Date: 2026-09-18
> Base（develop）: `1baedc0d092424926e61afa4f6cf2d869f8236a6`
> Reviewed HEAD: `9dff02b6951d714042fccdbc10580b3efe23ac24`
> merge-base: `1baedc0…`（= base，无分叉）
> 实现提交: `6109d4c`；docs/plan: `691b6bb` / `bad7681` / `985cfe5` / `c5cb68a` / `90e5207` / `9dff02b`
> 工作区: **clean**（`git status --short` 空；无暂存 / 未跟踪）
> 已审查: 完整 `git diff 1baedc0 9dff02b`（25 文件，+3699 / −42）
> 未审查: 真实浏览器 E2E；超大规模性能；AC-05-b / AC-07-b（已作废分支）

---

## 独立执行摘要（真实命令与数字）

```text
# 评审自建真实 PG（pgserver，socket /tmp/f010-rev/pgdata）+ 3 库，结束后按 PID 499115/499139 精确 kill；未触碰无关实例
$ pytest -q tests/test_resource_views_api.py tests/test_resource_views_guards.py  →  30 passed in 30.83s
$ pytest -q                                                                       →  965 passed, 2 warnings in 989.42s（无 skipped）
$ python /tmp/f010-rev/indep.py（评审自写、自造数据、自调 canonical 端点）          →  TOTAL 30 checks, 0 failures
$ 前端：npm run typecheck → exit 0；npm run test → 38 files / 562 passed；npm run build → ✓ built in 6.42s
$ 迁移：git diff 1baedc0 9dff02b -- backend/migrations/ → 空
$ 0001–0008 + deletion/service.py：sha256 在 base / HEAD / 工作区 三方相等
$ Guard 注入（/tmp 副本，逐字节还原）：M1 未批准路由、M2 子资源路由、M3b deleted_at 写入、M6 删既有路由 → 全部检出
```

**评审的独立核心验证（`indep.py`）**：自建数据后**自己调用 canonical 端点**（NIC 单端点 / IP 按 NIC 并集 / VM 单端点 / Container「B + 各 VM」并集 / Service「R(B) 各载体」并集按 id 去重），与聚合端点逐类集合**深等**。结果：**五类全部相等**；`svc_multi`（绑定 B + VM1 + Container 三载体）**只出现一次**；各类 `id` 升序、`total==len`；210 项容器 / 205 项服务**完整快照未被静默截断**且与 canonical 深等。

---

## AC-01~AC-25 逐条结果

| AC | 结果 | 证据 |
|---|---|---|
| AC-01 NIC 直接父 | PASS | indep：NIC 集合 == canonical `?bare_metal_id=`；排除 B2 |
| AC-02 IP 经 NIC 间接 | PASS | indep：IP == 各活跃 NIC `?network_interface_id=` 并集；`IpAddressRead` 无 `bare_metal_id` |
| AC-03 VM 直接宿主 | PASS | indep：VM == canonical 深等 |
| AC-04 Container 直接载体 | PASS | indep：`(BARE_METAL,B)` 条目出现，载体二元组可见 |
| AC-05-a 含间接 | PASS | indep：经 VM 的 Container 出现；他机 / 他 VM 排除 |
| AC-05-b | NOT TESTED | 已作废分支（不适用），与裁定一致 |
| AC-06 Service 直接绑定 | PASS | indep：绑定 B 的 Service 出现，carriers 可见 |
| AC-07-a 含间接 + 去重 | PASS | indep：VM / Container 载体 Service 出现；`svc_multi` 计数 == 1 |
| AC-07-b | NOT TESTED | 已作废分支 |
| AC-08 关系依据可见 | PASS | indep：逐类断言 `bare_metal_id`/`network_interface_id`/载体二元组/`carriers` 交集 |
| AC-09 字面往返 | PASS | 仓库 T-10-02 在本次运行（30 passed）内通过；字面量无归一化 |
| AC-10 404 五类分别成立 | PASS | indep：不存在 B(999999) → 404 `details==[]`；**raw SQL 置 B.deleted_at 且子行仍在 → 404** |
| AC-11 Empty 五类分别成立 | PASS | indep：B 活跃全空 → 五类 `{items:[],total:0}`；NIC-only / NIC 无 IP 均 200 |
| AC-12 404 判定主体唯一 | PASS | indep：某类空 / 子资源软删 → **仍 200** |
| AC-13 三态可区分 | PASS | 前端测试（本次运行绿）+ 代码：页面级 `data-state=not-found` vs 类级 `.list-states[data-state=empty]`，文案不同；Empty 不触发全局会话失效 |
| AC-14 逐类软删子不出现 | PASS | indep：raw 软删 IP / Container → 该类不含、其余不受影响；软删 VM 连带其 Container / Service 正确移除 |
| AC-15 删除消失不级联 | PASS | 仓库 T-10-06 本次通过；indep AC-19 计数不变 |
| AC-16 主体软删 → 五类 404 | PASS | indep：raw 软删 B（子行仍在）→ 404 |
| AC-17 无需跨页面拼接 | PASS | 前端导航测试 16 passed；`App.vue` 五类详情入口 + 返回上下文接线完整 |
| AC-18 复用 canonical（深等） | PASS | **indep 自调 canonical 逐类集合深等全部相等** |
| AC-19 只读 | PASS | indep：8 表行数 + B 整行快照查询前后相等；OpenAPI 仅 GET / 无 body |
| AC-20 不新增 Cluster 视角 | PASS | 自生成 OpenAPI：`/api/clusters*` 恰 F009 四路径 |
| AC-21 无 `cluster_id` 列 / 过滤 | PASS | 迁移 diff 空；OpenAPI 参数恰 `{bare_metal_id}`；响应 schema 无 cluster 字段 |
| AC-22 无通用关系引擎 | PASS | 源码无递归 / 深度参数 / 关系类型参数；`/api/bare-metals/{id}/` 二段路径**恰为** `related`；M2 注入被检出 |
| AC-23 无状态 / 监控越界 | PASS | 五类 `*Read` schema 无 `status`/`state`；无计数端点 |
| AC-24 认证 | PASS | indep：未认证 → 401 `UNAUTHENTICATED` 且响应体不含资源数据 |
| AC-25 需求归属 | PASS | diff 范围仅聚合模块 / 挂载 / 前端关联区·导航 / docs / tests；无 CRUD / 导入 / 删除守卫重复实现 |

---

## 架构符合性（REQUIRED 1~8 / R1~R7）

| # | 结论 | 证据 |
|---|---|---|
| REQ#1 唯一 404 网关 | **PASS（对抗验证）** | 读 `service.py`：仅 `bare_metals.service.get_bare_metal_by_id` 抛 404；嵌套枚举全走 `*.repository.list_active`（不抛）。indep：全空类 / 全子资源软删 → **均 200** |
| REQ#2 无第二份软删 / 谓词 | PASS（守卫深度见 REV-2） | `grep deleted_at backend/app/resource_views/` → 无匹配；仅委托 repository |
| REQ#3 ≤3 跳无递归 | PASS | AST / 人工确认直线式组合，无递归、无深度 / 关系类型参数 |
| REQ#4 并集按 id 去重、升序 | PASS | indep：三载体 Service 只出现一次；各类 `id` 升序 |
| REQ#5 单请求单 session | PASS（含 NOTE，见 REV-3） | 单路由 / 单 `get_db_session`；隔离级别为默认 READ COMMITTED |
| REQ#6 schema 复用封闭 | PASS | 自生成 OpenAPI：顶层恰 5 键；元素 `$ref` 为 canonical `*Read`；无越界字段 |
| REQ#7 `EXPECTED_GET_ROUTES` 追加 | PASS | diff 仅 **+1 行**（既有成员全保留）；M6 删成员被 `test_g010_1` + `test_g_f_only_read_only_get_routes` 检出 |
| REQ#8 `/api` 下走既有认证 | PASS | `main.py` `prefix="/api"`；indep 未认证 401 |
| R1 第二软删路径 | 缓解有效 | 无 `deleted_at` 表达式；G-010-5 绿 |
| R2 子资源 404 渗入 | 缓解有效 | 全空 / 子软删仍 200 |
| R3 聚合 / canonical 漂移 | 缓解有效 | canonical 深等全等 |
| R4 被误读为子资源端点 | 缓解有效 | M2 注入 → G-010-2 / G-010-7 检出 |
| R5 路由列表被替换 | 缓解有效 | M6 注入 → 检出 |
| R6 响应无界 | 已知 OPEN#6 | 非本次范围 |
| R7 前端重复实现过滤 | 缓解有效 | 前端测试断言请求 URL 恰 `{/api/bare-metals/{id}, …/related}` |

## 契约符合性

- **契约字面值**：契约示例为 `"technology_type": "Ethernet"` / `"purpose": "Business"`，与 canonical 大小写敏感封闭集一致。indep：canonical 拒绝大写 `ETHERNET` → `400`；实现返回 canonical 字面值。
- 元素 schema **逐字段复用** canonical `*Read`：实现用 `model_validate`（NIC/IP/VM）与 `from_model`（Container/Service），与 canonical 路由**同一构造器**。
- 无 query 参数、无请求体；错误码 404 / 400 / 401；404 覆盖「不存在」与「已软删」且 `details==[]`；Empty 与 Not Found 语义分明。
- 完整快照：非分页、按 id 升序、按 total 取全循环，未静默截断（210 / 205 实测）。

## 数据库与迁移

- `git diff 1baedc0 9dff02b -- backend/migrations/` **为空**；`0001`–`0008` 逐文件 sha256 在 base / HEAD / 工作区**三方相等**。
- `backend/app/deletion/service.py` sha256 `c46c6d2e…` 在 base / HEAD / 工作区**三方相等**。
- `resource_views/**` 无 `deleted_at` / 无 `cluster_id`；无新表 / 列 / 索引 / 约束；`database: false` 与真实 diff 相洽。

## 可维护性与测试充分性

- `resource_views/**` 无未使用代码、无第二套业务规则；与 `cluster_views/` 结构一致；4 文件职责清晰（router / service / schemas / init）。
- 后端 30 passed、全量 **965 passed**（与 Test Report 一致）；前端 562 passed。测试**直接构造真实数据 + 真实 DB + 绕过应用层 raw SQL 预置软删**，未依赖排序偶然；AC-18 用 canonical 端点交叉比对，**不是迎合实现**。
- 评审 Guard 注入复核：M1 → `test_product_api_surface_is_closed`（allow-list，**真正防线**）+ `test_g_f_only_read_only_get_routes`；M2 → `test_g010_2` / `test_g010_7` / `test_g_f_…`；M3b（写入）→ `test_g010_5` ×2；M6 → `test_g010_1` + `test_g_f_…`。**均真实可失败**，注入后逐字节还原 / 仓库全程 clean。
- 既有 guard **只增不减**：`test_auth_guards.py` 仅 +2 行（追加路径）；无断言放宽；前端测试改动仅为适配新的并行请求数，未削弱。

---

## Findings

### REV-1

```text
Severity: LOW
Layer:    Plan / Metadata
Location: docs/project/v1/project-plan.yaml > features[F010].git.head_commit
Problem:  计划记录 head_commit = 6109d4c（实现提交），但 Feature 真实 HEAD = 9dff02b（测试提交），
          且同一节点已置 implementation.test: COMPLETE / current_stage: REVIEW —— 二者自相矛盾。
Evidence: git rev-parse HEAD → 9dff02b…；git show 9dff02b:docs/project/v1/project-plan.yaml → head_commit: 6109d4c…
Impact:   不影响代码正确性；但与 git-workflow 的「Feature HEAD 必须与测试 / Review 基线一致」不符，历史上同类均作修正项处理。
Expected: Merge / DONE 前把 F010 head_commit 更新为 9dff02b（或合并后写 merge_commit）。
```

### REV-2

```text
Severity: NOTE
Layer:    Test / Guard coverage
Location: tests/test_resource_views_guards.py::test_g010_5 / tests/deletion_guard_helpers.scan_deleted_at_writes
Problem:  G-010-5 只检测 deleted_at 的「写入」形态；架构 REQUIRED #2 表述为「新模块不得出现任何 deleted_at
          表达式（含第二份活跃过滤谓词）」。实测：向 resource_views/service.py 注入**只读**的
          .deleted_at.is_(None) 谓词时，G-010-5 / G-010-6 均**不失败**（12 passed）。
Evidence: 注入 M3（read 谓词）→ 12 passed；注入 M3b（write: obj.deleted_at=None）→ test_g010_5 ×2 FAILED。
Impact:   纵深防御存在缺口：若未来有人在聚合模块另写一份活跃过滤谓词，不会被静态 guard 检出。
          当前实现**确无**任何 deleted_at 表达式（grep 无匹配），故**不构成实现缺陷**。
Expected: 可选加「resource_views 源码不得含 deleted_at 字样」的 token guard，或把 REQUIRED #2 表述收窄为「不得写入」。
          属加性加固，不阻塞合并。
```

### REV-3

```text
Severity: NOTE
Layer:    Backend / Transaction
Location: backend/app/resource_views/service.py + backend/app/api/deps.py
Problem:  Architecture REQUIRED #5 声称「单一 session 内保证跨类一致快照」。实际隔离级别为 PostgreSQL 默认
          READ COMMITTED，同一事务内各语句各自取快照；并发写（软删）期间，offset 分页可能跳过 / 重复行
          （重复已由去重吸收，**跳过则是静默少项**）。
Evidence: service.py 的 _snapshot 为 offset/limit 取全循环；deps.py 单 session 默认隔离级别；架构同时声明「无需加锁」。
Impact:   并发软删下聚合快照可能瞬时不自洽（不会产生错误 404 / 500）。对本只读、低写并发的内部平台风险很低，
          且与既有 F009 / F002 同一取向。
Expected: 不需在本次修复；若产品要求严格一致快照，由 Architect 决定是否使用 REPEATABLE READ。
```

除上述外，**无 BLOCKER / HIGH / 必须当前修复的 MEDIUM**。

## Existing Defects（复核 Tester 报告）

Tester 报告 `Defects: None`。评审独立复核其两项「非缺陷」记录：

| Tester 结论 | 评审评估 | 是否阻塞 |
|---|---|---|
| 对「有活跃子资源」的 NIC / VM 直接 `DELETE` 返回 `409`（父删子拦，R-DELETE-004） | 属实且属既有正确行为；`resource_views` 不重复实现删除守卫 | 否 |
| `BOUNDARY_TOKENS` 为 `()`，未批准路由的真正防线是 `APPROVED_API_PREFIXES` allow-list | 属实。M1 注入确认 allow-list guard 检出，deny-list 恒真未失败 | 否 |

## Non-blocking Follow-ups

1. **REV-1**：修正 plan `head_commit` 为 `9dff02b`（Merge / DONE 前）。
2. **REV-2**：可选加「resource_views 无 `deleted_at` 字样」静态 guard（加性加固）。
3. **REV-3**：如要求严格一致快照，由 Architect 裁定隔离级别（当前无需）。
4. Architecture OPEN#6：聚合级分页 / 超大规模——无已确认需求，留待后续。

## Unreviewed Areas

- 真实浏览器级 E2E（无 Playwright / 浏览器自动化）；已以真实后端 + 真实 Vue 组件渲染测试替代。
- 作废分支 AC-05-b / AC-07-b（按用户裁定不适用）。
- 单机关联规模远超 210 项的性能与聚合分页。

---

## 结论

```text
APPROVED WITH FOLLOW-UP
```

**理由**：无 BLOCKER、无 HIGH、无必须当前修复的 MEDIUM；AC-01~AC-25（作废分支除外）均有评审**自己执行**的独立证据；`resource_views` 为既有 canonical 过滤原语的**真实复用**（评审自调 canonical 端点逐类深等，含多载体去重与完整快照）；唯一 404 网关经对抗验证成立；guard 经注入证明**可失败**且只增不减；迁移与删除服务逐字节未改；前端只消费聚合端点、三态可分。三项 LOW / NOTE 均为非阻塞跟进项。

批准**仅对** Feature HEAD `9dff02b` / Base `1baedc0` 有效；后续代码、契约或 Base 变化须重新测试与 Review。

GIT: NONE
