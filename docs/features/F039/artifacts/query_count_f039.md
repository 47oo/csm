# F039 A1/A8 — 查询计数基准（真 PG 实测，2026-10-29）

## 1. 环境

| 项 | 值 |
| --- | --- |
| PostgreSQL | 16.15（`127.0.0.1:55432`，user `csm`） |
| 测试库 | `csm_f037_test`（DB-D10 guard：名称含 `test`，`TEST_DATABASE_URL` 与 `DATABASE_URL` 不同） |
| Python / pytest | 3.12.7 / 7.4.4 |
| SQLAlchemy / psycopg | 2.0.34 / 3.2.13 |
| 实现树 | 工作树（HEAD `831276e` + 未提交的 `backend/app/services/{dashboard,ip_capacity}.py` 变更） |
| 基线树 | `git archive f66d1f3 backend` → `/tmp/f039_base_test`（只读导出）；`git hash-object` 与 `git rev-parse f66d1f3:...` 相等：`dashboard.py` `f0ca4d28267c346cd3d63f6d2dee03f811c8be60`、`ip_capacity.py` `7e01365cf38630d10b031736b56267ac7eea7aaa` |

## 2. 计数口径（与 TD-F039 §1.1 一致）

- `before_cursor_execute` 监听 engine，只统计首关键字为 `SELECT` 的语句，`finally: event.remove`；
  `BEGIN/COMMIT/SAVEPOINT/DDL/DML` 不计。
- `q_svc(N)` = `dashboard_service.get_dashboard(session, page=1, page_size=N)`（不含认证与 §23.2 范围解析）。
- `q_http(N)` = `GET /api/v1/dashboard?page_size=N`，常数开销 `C = q_http − q_svc`。
- 夹具：1 Cluster + 50 Network（每网络 gateway `.1`、RESERVED `.2-.10`、AUTO `.100-.120` 与 `.130-.140`、
  未绑定 IP `.100/.101/.130/.200`），决定性数据、无随机种子；N 轴由 `page_size ∈ {1,10,50}` 切换。
- 基线在同一 PG 实例、同一探针、**独立解释器**（`cwd=/tmp/f039_base_test/backend`，
  `PYTHONPATH=/tmp/f039_base_test/backend`）运行，禁同树混跑。

## 3. 实测：`N → q_svc`（实现后 vs 基线）

| N (`page_size`) | 实现后 `q_svc` | 基线 `q_svc`（f66d1f3） | 实现后 `q_http` | 基线 `q_http` |
| --- | --- | --- | --- | --- |
| 1 | **11** | 14 | **12** | 15 |
| 10 | **11** | 68 | **12** | 69 |
| 50 | **11** | 308 | **12** | 309 |

- 实现后：`q_svc(1) == q_svc(10) == q_svc(50) == 11`，`C = 1`（N=1/10/50 全部相同），`q_http(50) = 12`。
- 基线：斜率 `+6 / Network`、常量 8，`q_svc(1) ≠ q_svc(50)`（14 ≠ 308）；`C` 亦为 1。
- `K` 钉死为 **11**（上限 `<= 20` 满足）；`K` 未据此上调，断言为字面量。

### 3.1 AUTO 池轴（单 Network，逐池追加，`page_size=1`）

| AUTO 池数 P | 0 | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- | --- |
| 实现后 `q_svc` | 11 | 11 | 11 | 11 | 11 |
| 基线 `q_svc` | 12 | 13 | 14 | 15 | 16 |

实现后每步 `len(row["auto_pools"]) == P`（0→4），语句数不变；基线 `+1 / 池`。

### 3.2 F010 `GET /networks/{id}/capacity`（本次改动的前置约束：语句数不增）

| AUTO 池数 P | 0 | 1 | 2 |
| --- | --- | --- | --- |
| 实现后（HTTP 级，含认证/路由与 `4+P` 服务语句） | 6 | 7 | 8 |
| 基线（同探针） | 6 | 7 | 8 |

→ 端点路径未被 F039 增加语句；该路径不使用批量上下文，仍按池 +1（architecture §2 的“响应与语句数不增”成立）。

## 4. 非空证据：同一 A1 用例在基线树上必须失败

把实现树的 `tests/integration/test_f039_query_count.py` 原样拷入基线树后运行 A1 用例（`cwd=/tmp/f039_base_test/backend`）：

```text
>       assert observed == {1: K, 10: K, NETWORK_AXIS: K}, observed
E       AssertionError: {1: 14, 10: 68, 50: 308}
E       assert {1: 14, 10: 68, 50: 308} == {1: 11, 10: 11, 50: 11}
>       assert http_counts[NETWORK_AXIS] == K + overhead
E       assert 309 == (11 + 1)
2 failed, 9 deselected in 50.95s
```

→ A1 判据非平凡：start_commit 代码上必然 FAIL，实现树上 PASS。

## 5. `load_capacity_context` 语句数与 EXPLAIN

- 批量预取在 2-Network 夹具上实测 **3 条** SELECT（B1/B2/B3），`context` 提供的行装配为零额外语句
  （断言于 `test_a8_batch_statements_have_index_paths`）。
- EXPLAIN 计划、索引名与 `enable_seqscan=off` 对照见 `explain_f039.md`（同目录）；两次运行均无 `Seq Scan`。

## 6. 复现命令

```bash
# 实现树
cd backend && TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test' \
  python -m pytest tests/integration/test_f039_query_count.py tests/integration/test_f039_scope.py -q -s

# 基线树（只读导出 + 独立解释器）。探针模块见同目录 test_f039_baseline_probe.py：
# 它只记录数值、不断言 K，并断言基线上 A1 判据为假（14 != 308 / 池轴非常数）。
rm -rf /tmp/f039_base_test && mkdir -p /tmp/f039_base_test && git archive f66d1f3 backend | tar -x -C /tmp/f039_base_test
cp backend/tests/integration/test_f039_query_count.py /tmp/f039_base_test/backend/tests/integration/
cp docs/features/F039/artifacts/test_f039_baseline_probe.py /tmp/f039_base_test/backend/tests/integration/
cd /tmp/f039_base_test/backend && TEST_DATABASE_URL='postgresql+psycopg://csm:csmtest@127.0.0.1:55432/csm_f037_test' \
  PYTHONPATH=/tmp/f039_base_test/backend python -m pytest tests/integration/test_f039_baseline_probe.py -q -s
```
