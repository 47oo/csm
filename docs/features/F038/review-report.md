# F038 导入解压 / 解析内存边界加固（R05）— REVIEW 报告

- **结论**：**APPROVED WITH FOLLOW-UP**（无 BLOCKER / HIGH / 必须修复 MEDIUM；可进入 Merge Gate）
- **候选 HEAD**：`6d9144b899b644228a90cd8a2db921c2288e6500`；**Base**：`refs/heads/v3.4` = `8e609ca2e5b88c30804b6f6ad54a8a57d7906556`（= `start_commit` = merge-base）
- **版本**：v1（2026-10-29，正式 Review，独立复核，reviewer 只读产出、协调器持久化）
- **阈值口径基线**：`architecture.md` v1 + §13 + **§14（repair round 1，冲突以 §14 为准）**；Test 交接 `TE-F038-2` = `READY FOR REVIEW`

## 1. 范围

`git diff --name-status "refs/heads/v3.4"...HEAD`：**10 文件 / +4404 −53**，9 提交（`7860b43..6d9144b`）：

| 类别 | 文件 |
| --- | --- |
| 实现 | `backend/app/services/resource_import.py`（+120/−27）、`resource_interface_ip_import.py`（+9/−4） |
| 测试 | `backend/tests/integration/test_f038_parse_bounds.py`（A） |
| 报告 | `docs/features/F038/{product,architecture,implementation,test-report}.md`（A） |
| 计划 | `docs/project/{project-plan.yaml,backlog.md,milestones.md}`（状态与派生视图） |

零 diff 守卫（实测 0 文件）：`docs/api/`、`docs/database/`、`frontend/`、`backend/alembic/`、`backend/pyproject.toml`、`backend/Dockerfile`、`backend/tests/integration/test_f037_import_parse_errors.py`。工作区 clean；`validate_project_state.py`（含 `--feature F038`）与 `render_project_views.py` 只读校验通过；工作流—计划基线一致性（`DELIVERY_BRANCH=v3.4` / `git.base_branch` / `refs/heads/v3.4`）一致，无基线漂移。

## 2. 独立执行（真实 PostgreSQL：容器 `csm-f037-pg`，`127.0.0.1:55432`，库名含 `test`）

| 执行项 | 实测 | 报告值 | 结论 |
| --- | --- | --- | --- |
| `-k "m3a or m4b or m4d or m4e or m6"` | 8 passed / 68 deselected（28.89s） | 8 passed（42.87s） | 一致 |
| 整模块 `test_f038_parse_bounds.py` | **76 passed**（128.13s，无 skip ⇒ I 层真跑真库；日志显示 `DROP SCHEMA` + `alembic upgrade head` 0001→0015） | 76 passed | 一致 |
| `test_f037_import_parse_errors.py` | **52 passed**（文件零 diff） | 52 passed | 一致 |
| R2+R3 | 101 passed（381.21s） | 70+31 | 一致 |
| R4 / R5 / R6 | 48 / 4 / 3 passed | 同 | 一致 |
| 单测独立性（`i5`、`u4+u5` 单独跑） | 2 / 2 passed | — | 无顺序依赖 |
| `ruff check`（应用代码 / 测试模块） | 应用 All checks passed；测试 **3× F811** | TD-I-12 已登记同值 | 陈述属实（F-2） |
| 基线模块独立性 | `/tmp` 基线 sha256 == `git show 8e609ca:…` | 声明不入库 | M 层基线真实 |

**Reviewer 自建反事实/差分探针（`/tmp`，不入库）**：
- **A** 独立差分 fuzz（155 例，自建基线语义，不引用仓库参考实现）：**0 处不一致**；
- **B** 「值只在第 ≥ keep_cells 列」样本（1 / 5000 / 5001 行、全空 6000 行、纯空格行）：**5/5 一致**（证明整行判定未收窄）；
- **C** dimension 变体 7 例（无 / 偏小 / 偏大 / 5001 行 / 尾部空行 / 伪造宽）：**7/7 与基线语义一致**；
- **D** 判据判别力反事实：`T-1c`（`keep_cells=651` 不裁列）**25.356 > 3.579 MiB ⇒ FAIL**；`T-1b′`（`8e609ca` 真实无界保留）**31.553 > 13.812 MiB ⇒ FAIL** ⇒ 新判据**不是恒真**。

## 3. 层次结论

| 层 | 结论 |
| --- | --- |
| 产品与领域 | **符合**：AQ-2=A 边界成立（无新增拒绝；上限 5,242,880 / 5000 / 1000 与 `reason` 集合不变）；S1–S8 / B1–B13 逐条有实测映射；S3 的 ON-1 errata 已在 `product.md` 落稿（报告级澄清，不改需求） |
| 架构与依赖 | **符合**：按 §4.2 / §13.7（IMP-1..IMP-10）落稿；`_finalise` 在白名单作用域外；无新依赖 / I/O / 日志 |
| 数据完整性 | **无影响**：零 DDL、零事务边界变化；I9 实测 S-W1/S-W2/S-W4/S-W5/S-W6a × 4 端点后 7 表计数逐表不变；未新增唯一性 / 关系 / 生命周期规则 |
| 数据库 | **NOT_REQUIRED（复核成立）**：`backend/alembic/`、`docs/database/` 零 diff |
| API / Contract | **零 diff 且顺序不变**：401→403→`format`422→413→**解析 422**→**行数 413**→表头/列 422→逐行 |
| 前端 | **NOT_REQUIRED**：`frontend/` 零 diff |
| 后端实现 | **正确**：排空性（无 `break`/`return`）、`record[:keep_cells]`（无 `list(record)`）、`_is_blank_record` 整行判定、`_PARSE_FAILURES==8`、`except Exception` 仍 2 处（基线文件相同）、L7″ 干净 |
| 测试充分性 | **充分**（1 项登记缺口 F-1）：U/I/M/S/R 五层；差分独立（`/tmp` 基线 sha256 校验 + 自建 155 例）；无迎合实现（3 项 FAIL 走 Architect §14 重裁且生产代码零变更） |
| 安全 | **通过**：无新输入面、无内容泄漏（响应体 0 命中 marker / `Traceback` / `<worksheet`）；无 `field_size_limit` / `strict=True` / lxml 依赖 |
| 变更与批准 | **符合**：plan revision 25 覆盖 F038；`pending_changes: []`；requirements revision 16；AQ-2=A 有用户批准来源；§14 为 Architect 专业签核（DR-F038-07..11，含「生产代码零变更」） |

## 4. §14 重裁正当性（R-13 防放宽）— PASS

- `1.5` / `8` / `2 MiB` / `1.2` / `64 MiB` **均未变**（源码 grep 逐条核对；唯一新增常数 G-A2 的 `8B + 4 MiB` 为收紧用）。
- `F(x)` 为探针实测（`decode("utf-8-sig")` → `io.StringIO(newline="")` → 遍历丢弃；同进程同字节、两次取较大值、按 key 缓存 + `_FLOOR_PINNED`），复现 `F/B = 5.045 / 5.011 / 5.009 / 5.216`；受 G-A1（`F ≥ B`）/ G-A2（`F ≤ 8B+4MiB`）双向夹逼 ⇒ 无法抬高地板稀释判据。
- T-1b 删 `Δbytes`：允许的保留量增长由 **4.794 → 2.053 MiB**（收紧）；旧式在零保留时仍差 9.31 MiB 地板 ⇒ 构造性不可满足。
- 新增 T-1c 有判别力（反事实 FAIL）；xlsx 族原样复现（11.4382× / 155.7250×，`T-1` 1.868 ≤ 3.711、1.970 ≤ 4.716）。
- `legal` 族参数退役未留实质缺口（该族 `work(fixed)≈work(baseline)` 本无判别力；由 T-3 0.9865 + U5 + I8 承担；报告已标 `NOT TESTED（已退役）`，未冒充通过）。

## 5. 缺陷与跟进

**无必须修复项。**

| ID | 级别 | 内容 | Owner | 必须修复 |
| --- | --- | --- | --- | --- |
| F-1 | MEDIUM（不阻塞） | `architecture.md` §13.9 要求补充的「无 `<dimension>` / `dimension` 与实际不一致」两例既未实现也未在 test-report 的 `NOT TESTED` 表登记（审核链出现静默消失）；Reviewer 7 例实测零差异 ⇒ 属**记录缺口**而非正确性缺陷 | Tester | 否（须登记） |
| F-2 | LOW | 测试模块 3× ruff F811（`role_client_factory` 导入/形参重名），应用代码 ruff 全通过 | Tester / Backend | 否 |
| F-3 | NOTE | 「删除 Δbytes = 收紧」成立的是允许保留量增长；度量口径已从 raw peak 改为工作集，公式与两侧数值已同时公布，无误导 | Architect | 否 |
| F-4 | NOTE | `execution.repair_rounds: 0` 与 F038 实际使用 1 轮修复存在解释空间；`git.head_commit` 需在 Merge 后写入 | 协调器 | 否 |
| F-5 | NOTE | 文档含本地测试库口令串（`docs/` 下已有 25 份同类记录，既有惯例）；如对外发布可考虑脱敏 | 协调器 | 否 |

**旧缺陷复核**：DEF-01 / DEF-02（HIGH）**维持 CLOSED**，归责 Architect 阈值口径成立；TD-I-9 / TD-I-10 **CLOSED 成立**；TD-I-3 依据改写正确（5312.4093× 已复现）；TD-I-8 勘误算术正确（16,370 = 16,384 − 14，用例用构造式断言）；R-15 未发生；R-6 补充两例为原报未涉及的**登记缺口**（F-1）。

## 6. FOLLOW-UP（均不阻塞合并）

| ID | 内容 | Owner |
| --- | --- | --- |
| FU-1（←F-1） | 在 `test-report.md` §2.11 补登 R-6 两例（`NOT TESTED`，附 §13.9 依据）；可引用本报告 §2-C 的 7 例实证，但不得表述为架构要求已被原测试覆盖 | Tester / 协调器 |
| FU-2 | 清理测试模块 3× F811 | Tester / Backend |
| FU-3 | 确认 `repair_rounds` 语义；Merge 后写入 `git.head_commit` / `git.merge_commit` | 协调器 |
| FU-4 | **ON-6**：CSV 地板 `F ≈ 5N` 的消解（增量解码）属 `_parse_csv` 行为面改造，按 `change-control.md` §4 另立 Feature；不得作为 F038 变通 | Product / Architect |
| FU-5 | 如仓库对外可见，考虑脱敏本地测试口令 | 协调器 |

**给 F045 整体验收的提示**：F038 的 A2/S1 证据是「相对倍数 + 规模不敏感 + 绝对哨兵」，不含真实 OOM、不含无 lxml 镜像、S-W2 原规模为 `ESTIMATE`；整体验收不得把局部 PASS 拼成跨功能结论。

## 7. 未审查项

未逐行通读 2,226 行测试模块全文（已通读关键区段并 100% 执行）；未做多轮噪声分布评估；未验证真实 OOM / 无 lxml / S-W2 原规模（`NOT TESTED`）；未验证 5000 行写入端点与 S-W2b 单侧断言（`NOT TESTED`，登记 R-14）；未评审 F001–F037 历史证据内容；未跑 Compose 与前端构建（`layers.frontend=false`，归 F045）；未核验批准来源真伪（仅核对字段与覆盖范围一致）；反事实探针位于 `/tmp`，不入库。

## 8. 声明

- 本 Review 只读：未修改任何实现、测试、契约、计划或产品规则；跑测后再次确认工作区 clean 且 HEAD 未变。
- 结论 **APPROVED WITH FOLLOW-UP**：核心验收满足、必要验证可信、无 BLOCKER / HIGH / 必须修复 MEDIUM、无未决产品问题。
- 批准仅覆盖候选 HEAD `6d9144b` 与 Base `refs/heads/v3.4` = `8e609ca`；基线或候选变化须重新 Review。
- 报告中的建议不自行成为产品或架构决定（F-3 / FU-4 属 Architect / 用户权限）。
