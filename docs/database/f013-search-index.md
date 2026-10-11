# F013 全局搜索与 Dashboard — DATABASE 设计（索引 / Migration）

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：`docs/features/F013/architecture.md`（DR-171–DR-189，§6 候选索引集合，§9 数据库影响）、`docs/api/F013.md` 草案 v0、`docs/features/F013/product.md`（A12/A20、I-15、I-17、§10 交核）；`docs/database/f001-baseline.md` v1（DB-D2/DB-D4/DB-D7）、`f003-cluster.md` v2（DB-D30）、`f004-resource.md` v1（DB-D36/DB-D37/DB-D38/DB-D41）、`f007-interface.md` v1（DB-D77）、`f008-network.md` v1（DB-D89）、`f009-ip-pool.md` v1（DB-D106）、`f010-ip-address.md` v1（DB-D111–DB-D127，DB-D124）、`f011-service.md` v1（DB-D130/DB-D131/DB-D137）、`f012-service-endpoint.md` v1（DB-D152）；`backend/alembic/versions/0001_baseline.py`（`pg_trgm` 已在基线启用）、`0012_service_endpoints.py`（当前 head）、`0004_resources.py`/`0003_clusters_audit.py`/`0011_services.py`；`backend/app/models/resource.py`、`cluster.py`、`service.py`、`ip_address.py`；requirements-v3.md revision 3（§4/§4.1、§17、§21、§25、§26、§27）；`docs/architecture/d01-conventions.md` §5；`.pi/skills/data-integrity/SKILL.md`。
- **覆盖**：迁移 `0013_search_indexes` 与 4 条 GIN trigram 索引的签核（DB-D157–DB-D166）；`host(address)` 取舍裁定；匹配算子/阈值/EXPLAIN 证据要求；跨 Feature `errata`（含 DR-189 误标的更正）与受影响断言测试清单；Backend/Tester 可依赖保证与验证项。**不覆盖**：搜索/Dashboard 业务实现、`docs/api/F013.md` 定稿、各域列表 `q` 行为变更、TEST 执行。

---

## 1. 设计决策汇总（DB-D157–DB-D166）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D157 | 迁移 `0013_search_indexes`，`down_revision="0012_service_endpoints"`；**仅新增 GIN trigram 索引，无任何表/列/约束/触发器变更**；单一 head、无回填、无数据迁移、up/down 对称可逆；**不含 `CREATE/DROP EXTENSION`** | DESIGN（DR-184，§26） |
| DB-D158 | `ix_resources_hostname_trgm`：`resources (hostname gin_trgm_ops)` | DESIGN（§17/§26） |
| DB-D159 | `ix_clusters_code_key_trgm`：`clusters (code_key gin_trgm_ops)` | DESIGN（§17/§26） |
| DB-D160 | `ix_clusters_name_trgm`：`clusters (name gin_trgm_ops)` | DESIGN（§17/§26） |
| DB-D161 | `ix_services_name_key_trgm`：`services (name_key gin_trgm_ops)` | DESIGN（§17/§26） |
| DB-D162 | **4 条索引全部为非 partial（full）**，不附加 `WHERE deleted_at IS NULL`；理由见 §3 | DESIGN（DR-180/DR-189） |
| DB-D163 | **IP 索引裁定：`0013` 不建任何 IP 索引**（不建 `host(address)` GIN、不建 `address` 单列 btree）；理由与延期条件见 §4；`inet` 不能直接套 `gin_trgm_ops` | DESIGN（DR-184/DR-189，裁定 I-15 IP 部分） |
| DB-D164 | 不重复启用 `pg_trgm`（0001 已启用），不 DROP `pg_trgm`/`btree_gist`（F001 DB-D4）；`0013` 迁移体内不出现 `CREATE/DROP EXTENSION` | DESIGN（DB-D2/DB-D4） |
| DB-D165 | 匹配算子/阈值候选、GIN 命中 EXPLAIN 证据要求、与归一化键的一致性约束（§5）；正确性不依赖索引，缺索引仅性能退化 | DESIGN（§17/§26/D01 §5） |
| DB-D166 | 跨 Feature `errata`：修订 DB-D30/DB-D41/DB-D137；澄清 DB-D89/DB-D124/DB-D77/DB-D106/DB-D152 无实质变更；**更正 DR-189 对 DB-D38 的误标**；列出受影响断言测试（§7） | DESIGN（DR-189） |

> 状态语义：`DESIGN` = 由已确认规则（§17/§26/§27 + DR-184）必然产生的技术要求，本 DATABASE Gate 签核。本 Feature 不新增业务规则、不新增表/字段。

---

## 2. 索引集合（逐条）

全部为 GIN、opclass `gin_trgm_ops`、非唯一、非 partial。`pg_trgm` 的 `gin_trgm_ops` 由 0001 基线提供，`0013` 仅消费。

| 索引名 | 表 | 列 | `USING` / opclass | partial | 服务查询 | 依据 |
| --- | --- | --- | --- | --- | --- | --- |
| `ix_resources_hostname_trgm` | `resources` | `hostname` | `gin (hostname gin_trgm_ops)` | 否 | hostname 模糊/子串（A2/A3） | §17/§26；`hostname` 已由 `ck_resources_hostname_ascii_lower` 存 ASCII 小写，且 `hostname_key = hostname`（DB-D36/DB-D37） |
| `ix_clusters_code_key_trgm` | `clusters` | `code_key` | `gin (code_key gin_trgm_ops)` | 否 | Cluster code 模糊（A6） | §17/§26；`code_key = translate(btrim(code),'a-z','A-Z')`（DB-D22，仅 ASCII 折叠） |
| `ix_clusters_name_trgm` | `clusters` | `name` | `gin (name gin_trgm_ops)` | 否 | Cluster name 模糊（A6） | §17/§26；`name` 保留展示大小写，pg_trgm 相似度/`ILIKE` 大小写不敏感 |
| `ix_services_name_key_trgm` | `services` | `name_key` | `gin (name_key gin_trgm_ops)` | 否 | Service name 模糊（A7） | §17/§26；`name_key = lower(btrim(name))`（DB-D130，仅 ASCII 折叠） |

设计要点：

- **索引建在归一化键上**（`code_key`/`name_key`）；`resources.hostname` 本身即归一化展示值。这样索引列与 §4.1/§7/D01 §5 的唯一性/匹配口径**同一列**，避免“匹配用归一化键、索引用展示列”造成口径漂移。`clusters.name` 例外保留展示列，因为 §5 未给 Cluster name 归一化键，且 trigram 匹配天然大小写不敏感。
- **不建**：`networks`/`interfaces`/`ip_pools`/`ip_addresses`/`service_endpoints` 及四类对象除上表外的列。§17 只要求 hostname/IP/Cluster/Service；Networks 的 `name`、`cidr`，Interfaces 的 `name`，IPPool 的 `name` 等不在确认范围，不预建无需求支撑的索引（AGENTS §2.6）。
- **不改唯一约束**：GIN trigram 索引不提供唯一性，`uq_clusters_code_key`（全量唯一）、`uq_resources_cluster_id_hostname_key`、`uq_services_resource_id_name_key`（部分唯一）全部保持不变。（与 DR-189 的 DB-D38 误标相关，见 §7-E4。）

DDL 形态（供迁移实现参考，非迁移文件正文）：

```sql
CREATE INDEX ix_resources_hostname_trgm
    ON resources USING gin (hostname gin_trgm_ops);
CREATE INDEX ix_clusters_code_key_trgm
    ON clusters  USING gin (code_key gin_trgm_ops);
CREATE INDEX ix_clusters_name_trgm
    ON clusters  USING gin (name gin_trgm_ops);
CREATE INDEX ix_services_name_key_trgm
    ON services  USING gin (name_key gin_trgm_ops);
```

---

## 3. partial 取舍（DB-D162）

**裁定：4 条索引全部为非 partial（full table）。**

- **ADMIN `deleted=include|only` 影响（决定性理由）**：F013 搜索对 ADMIN 开放 `deleted∈{exclude,include,only}`（DR-180 / §21）。若索引带 `WHERE deleted_at IS NULL`，则 `include/only` 查询无法命中该索引（planner 仅在查询谓词与索引谓词可证明相容时才使用 partial index），已软删对象只能全表扫描。非 partial 索引对三种 `deleted` 模式均可用。
- **成本评估**：软删行仍进入 GIN 索引的额外开销相对可控；一期数据规模下“覆盖全部可见性模式”的收益高于索引体积收益。
- **与既有约定一致**：`ix_*_deleted_at` 为全量 btree（F003/F004/F008/…），partial 仅用于**业务唯一**（`WHERE deleted_at IS NULL`）。可见性过滤不属于唯一性，不套 partial 语义。
- 语义不变：索引不改变检索结果，仅影响计划；`deleted_at` 过滤仍由查询谓词承担。

---

## 4. IP 索引取舍与专业裁定（DB-D163，DB-D124 errata）

### 4.1 技术约束
`ip_addresses.address` 是 PostgreSQL `inet`（`family=4 AND masklen=32`，DB-D111）。`gin_trgm_ops` 的操作数类型是 `text`，**`inet` 不能直接建 trigram GIN 索引**；若要做 IP 文本模糊，必须建函数表达式索引，最自然的表达式是 `host(address)`（返回点分十进制 `text`，`host(inet)` 在 PG 中为 immutable，可作表达式索引）。

### 4.2 需求边界
- **CONFIRMED**：§17/§33 要求“某 IP 是哪台机器”。architecture §4.2 将 IP 命中定义为“先按裸 IPv4 **精确匹配** `address`；前缀/trigram **兜底**”标记为 `PROPOSED→CONTRACT`（未确认）。
- **CONFIRMED 部分（精确匹配）**：查询可用 `address = CAST(:q AS inet)`（`inet` 等值），**正确性不依赖索引**。

### 4.3 裁定
1. **`0013` 不为 `ip_addresses` 建任何索引**，`host(address)` GIN 与 `address` 单列 btree 均**不建**：
   - 前缀/trigram 兜底是 `PROPOSED`（未定稿），为未确认的匹配形态预建表达式 GIN 索引违反“不预建无需求支撑的索引”；
   - 精确匹配的全局热路径目前由既有 `ix_ip_addresses_cluster_id`（FK RESTRICT）与部分唯一 `uq_ip_addresses_cluster_id_address (cluster_id,address) WHERE deleted_at IS NULL` 部分覆盖；**跨 Cluster 的全局等值查询无法利用以 `cluster_id` 为前导列的索引**，会退化为顺序扫描——这是**已知性能限制，非正确性缺陷**。
2. **延期条件（写清楚，交 Tester 触发）**：真实 PG 上对 `/api/v1/search` 的 IP 精确查询做 `EXPLAIN (ANALYZE)`，若 `ip_addresses` 顺序扫描被判定为瓶颈，则在**后续迁移**（变更控制内）追加 `ix_ip_addresses_address`（`btree (address)`，`inet_ops`）或（若 CONTRACT 确认前缀/trigram 兜底）`ix_ip_addresses_host_trgm`（`GIN (host(address) gin_trgm_ops)`）；两者均为新增索引、无表结构变更，可对称回滚。
3. **本裁定的 DB-D124 errata**：DB-D124 的“不建 pg_trgm/GIN”在 `0013` 范围内**保持成立**；其“不建 address 单列 btree”部分在 `0013` 内**也未改变**（仅记录延期触发条件）。故 DB-D124 **无需**改写，只在 §7 加交叉引用说明 F013 已评估并延期。

> 结论：`0013` 保持“仅 GIN trigram 索引”的窄范围；IP 精确/前缀索引作为**已识别的非阻塞性能项**记录，触发条件与候选形态明确，避免在未定稿的匹配语义上过度建索引（AGENTS §2.6）。

---

## 5. 与搜索实现的关系（DB-D165）

### 5.1 可用算子与阈值候选
`gin_trgm_ops` 支持以下可被 GIN 加速的算子/表达式（交 Backend 在 CONTRACT/实现中选择，本设计不新增业务规则）：

| 候选 | 形态 | 语义 | 建议 |
| --- | --- | --- | --- |
| 子串 `ILIKE` | `col ILIKE '%' \|\| :q \|\| '%'` | 包含子串（A2 `gpu07`→`gpu0701`） | **主选**：最贴合 §17 示例的“模糊/子串”；大小写不敏感 |
| 相似度 `%` | `col % :q` | `similarity(col,:q) ≥ pg_trgm.similarity_threshold`（默认 0.3） | 次选（容错/拼写近似）；阈值可用 `SET LOCAL pg_trgm.similarity_threshold` 或显式比较 |
| 词相似 `word_similarity` / `<%` | `:q <% col` | 词级近似 | 可选，中文/长名场景按需 |
| 排序打分 | `similarity(col,:q) DESC` | 仅排序，不暴露 | 支持 DR-175 相似度降序；不改变候选集 |

**实现约束**：
- 优先用 `ILIKE '%q%'` 过滤（可走 GIN），需要时再以 `similarity()` 排序；**相似度不得暴露**（DR-175）。
- **短查询限制**：GIN trigram 只能对含 ≥3 个可提取字符的 pattern 生效；`q` 长度 1–2 时 planner 可能退化为顺序扫描。此为 pg_trgm 固有行为，**正确性不受影响**（architecture §7 已确认“匹配正确性不依赖索引”）。
- **候选集合并/去重/排序**（DR-174/DR-175，四条 typed 结果）属应用层 SQL，不落库；本设计仅提供索引支撑。

### 5.2 归一化一致性（D01 §5）
查询串 `q` 在送入各列匹配前必须按该列口径归一化，且**与唯一性同规则**：

| 目标列 | 归一化（应用侧，ASCII-only） | 与谁一致 |
| --- | --- | --- |
| `resources.hostname` | `trim` + ASCII A–Z→a–z | `hostname`/`hostname_key` CHECK（DB-D36） |
| `clusters.code_key` | `trim` + ASCII a–z→A–Z | `ck_clusters_code_key_matches`（DB-D22） |
| `services.name_key` | `trim` + ASCII A–Z→a–z | `ck_services_name_key_matches`（DB-D130） |
| `clusters.name` | 原样（`btrim` 后比较） | 无归一化键；trigram 大小写不敏感 |

`clusters.name` 的“无独立键”意味着其模糊匹配可能与 `code_key` 口径不同；这属 §5 既有边界，不新增键列。

### 5.3 GIN 命中证据要求（交 TEST / Tester）
- 真实 PG（非 SQLite/Mock）对四类代表查询执行 `EXPLAIN (ANALYZE)`，确认出现 `Bitmap Index Scan on ix_..._trgm`（`Recheck Cond` 含对应 operator）。
- 记录并接受：`q` 长度 < 3 时可能不走 GIN（顺序扫描，预期）。
- 断言索引存在：`pg_indexes` 中 4 条 `indexdef ILIKE '%USING gin%'` 且含 `gin_trgm_ops`；索引方法为 `gin`，非唯一、非 partial。

---

## 6. 迁移 `0013_search_indexes`（DB-D157 / DB-D164）

- `revision = "0013_search_indexes"`、`down_revision = "0012_service_endpoints"`；**单一 head**（`alembic heads` 唯一 = `0013_search_indexes`）。
- revision 名可等价使用版本号前缀；本文以 `0013_search_indexes` 为约定 revision id（与既有 `00NN_<slug>` 命名一致）。
- **upgrade**（4 步，仅建索引）：
  1. `CREATE INDEX ix_resources_hostname_trgm ON resources USING gin (hostname gin_trgm_ops);`
  2. `CREATE INDEX ix_clusters_code_key_trgm ON clusters USING gin (code_key gin_trgm_ops);`
  3. `CREATE INDEX ix_clusters_name_trgm ON clusters USING gin (name gin_trgm_ops);`
  4. `CREATE INDEX ix_services_name_key_trgm ON services USING gin (name_key gin_trgm_ops);`
- **downgrade**（对称逆序）：`DROP INDEX` 上述 4 条；**不 DROP `pg_trgm` / `btree_gist`**（F001 DB-D4）。
- **无回填、无数据迁移、无表结构变更**；`op.create_index(..., postgresql_using="gin", postgresql_ops={col: "gin_trgm_ops"})` 显式手写（autogenerate 不识别 opclass/`USING`）。
- **不重复启用扩展**：`pg_trgm` 由 `0001` 启用；迁移体内不出现 `CREATE EXTENSION`。
- **ORM 同步（交 Backend）**：在 `resource.py`/`cluster.py`/`service.py` 的 `__table_args__` 增加等价的 `Index(..., postgresql_using="gin", postgresql_ops={...})`，使 `Base.metadata` 与迁移一致，避免 autogenerate 漂移。属 Backend 职责，本设计只提要求。
- **数据安全**：纯新增索引，对既有数据无破坏；downgrade 只删索引，不删数据。生产回滚不需要备份（与既有建表迁移不同），但仍建议遵循 F001 备份流程。

---

## 7. `errata`：跨 Feature 一致性（DB-D166 / DR-189）

### E1. 直接修订（该表/列在 `0013` 新增 GIN）

| 编号 | 文档与位置 | 原文要点 | errata |
| --- | --- | --- | --- |
| **DB-D30** | `docs/database/f003-cluster.md` §1 表行、§2 line 40、§4 ② line 69、§8 I-4 line 107；`docs/features/F003/architecture.md:101`；`docs/api/F003.md:84` | “pg_trgm GIN 不在 F003 引入；F004/F013 评估后追加…不建 pg_trgm GIN” | F013 `0013` 在 `clusters` 建 `ix_clusters_code_key_trgm`/`ix_clusters_name_trgm`。DB-D30 的“F003 不引入”历史陈述仍真；**追加**“F013/Gate 已落地 clusters trigram”。§4 ②/I-4 更新为已闭合。 |
| **DB-D41** | `docs/database/f004-resource.md` §1 DB-D41、§3 line 51、§7 line 77、§8 V-DB-28；`docs/features/F004/architecture.md:41,120` | “不引入 pg_trgm GIN（沿用 DB-D30，F013）”“hostname ILIKE 无索引” | F013 建 `ix_resources_hostname_trgm`；删除“resources 无 pg_trgm GIN”断言（V-DB-28）。`hostname ILIKE` 现在由 GIN trigram 加速（≥3 字符）。 |
| **DB-D137** | `docs/database/f011-service.md` §1 DB-D137、§2 line 58、§3.5 line 117–126、§7 line 187、V-DB-122 line 202；`docs/features/F011/architecture.md:114` | “不建 pg_trgm/GIN、不建 name/name_key 单列 B-tree” | F013 建 `ix_services_name_key_trgm`；**“不建 name/name_key 单列 B-tree”仍然成立**（GIN ≠ btree）。V-DB-122 的“无 GIN”断言改为“存在 name_key GIN、无单列 btree”。 |

### E2. 澄清（文档含“不建 GIN”，但 `0013` 未在其表新增索引；无实质变更，仅加交叉引用）

| 编号 | 文档位置 | 说明 |
| --- | --- | --- |
| **DB-D89** | `docs/database/f008-network.md` §1 line 20、索引节 | `networks` 未纳入 F013 §17 搜索目标，`0013` 不建 `networks` GIN；原文保持成立，标注“F013 未变更”。 |
| **DB-D124** | `docs/database/f010-ip-address.md` §1 line 24、§3.5 line 231、§7 line 292、V-DB-107 line 309 | 见 §4：`0013` 不建 IP 索引；原文成立，追加“F013 已评估 IP 精确/前缀索引并延期，触发条件见 `docs/database/f013-search-index.md` §4”。 |
| **DB-D77** | `docs/database/f007-interface.md` §1 line 24、§4 line 57 | `interfaces` 不在 F013 搜索目标；原文成立，加交叉引用。 |
| **DB-D106** | `docs/database/f009-ip-pool.md` §1 line 22、§3 line 79 | `ip_pools` 不在 F013 搜索目标；原文成立，加交叉引用。 |
| **DB-D152** | `docs/database/f012-service-endpoint.md` §1 line 21、§3 line 53 | `service_endpoints` 不在 F013 搜索目标；原文成立，加交叉引用。 |

### E3. 更正 DR-189 的误标：`DB-D38` **不是**“无 GIN”决策

- `DB-D38`（`docs/database/f004-resource.md` §1 line 16）是 `uq_resources_cluster_id_hostname_key UNIQUE(cluster_id, hostname_key) WHERE deleted_at IS NULL` 的**部分唯一约束**决策，与 GIN 无关。
- architecture `docs/features/F013/architecture.md:47,150,187` 与 §9/§12 将 `DB-D38` 列入需 errata 的“无 GIN”决策，属**编号误标**；实际目标应为 `DB-D41`（resources 索引）。
- **裁定**：**不修订 DB-D38**；以 DB-D41 为 resources errata 目标。协调器在 CONTRACT 阶段同步 architecture 文档该清单（本文档给出修订建议，不直接改他文档）。

### E4. 受影响断言测试（`0013` 成为 head 后必须同步；均属 Backend/Tester 责任）

**(a) “无 GIN”正向断言（会 FAIL，需改为断言存在 trigram 索引）**

| 文件 | 行 | 断言 | 处理 |
| --- | --- | --- | --- |
| `backend/tests/integration/test_resource_constraints.py` | `300`–`309`（`test_no_pg_trgm_gin_on_resources`） | `resources` 上 `USING gin` 索引集合为空 | 改为断言 `ix_resources_hostname_trgm` 存在且 `gin_trgm_ops` |
| `backend/tests/integration/test_service_constraints.py` | `221`–`226`（GIN 断言块，任务标注 `:225`） | `services` 上 `USING gin` 索引为空 | 改为断言 `ix_services_name_key_trgm` 存在 |

**(b) 精确索引集合断言（会 FAIL，需加入新索引名）**

| 文件 | 行 | 断言 | 处理 |
| --- | --- | --- | --- |
| `backend/tests/integration/test_service_constraints.py` | `45`–`52`（`SERVICE_INDEXES`）、`210`（`indexes == SERVICE_INDEXES`） | `services` 索引集合精确相等 | `SERVICE_INDEXES` 加入 `ix_services_name_key_trgm` |

> `test_resource_constraints.py:410`（`RESOURCE_INDEX_NAMES <= indexes`）与 `test_cluster_constraints.py:331`（`INDEX_NAMES <= indexes`）为**子集断言**，不会因新增索引 FAIL；`clusters` 无“无 GIN”断言（全文无 `USING gin` 断言），故无需改。`test_network_constraints.py`/`test_interface_constraints.py`/`test_ip_pool_constraints.py`/`test_ip_address_constraints.py`/`test_service_endpoint_constraints.py` 的“无 GIN”断言因其表未被 `0013` 索引，保持 PASS。

**(c) head revision 硬编码断言（会 FAIL，`0012_service_endpoints` → `0013_search_indexes`；跨 Feature 迁移链同步）**

| 文件 | 行 |
| --- | --- |
| `test_virtual_machine_constraints.py` | `470, 471, 492, 524, 539, 541` |
| `test_service_constraints.py` | `134, 135, 150` |
| `test_service_endpoint_constraints.py` | `212, 213, 229` |
| `test_interface_constraints.py` | `141, 142, 160` |
| `test_ip_address_constraints.py` | `182, 183, 210` |
| `test_bare_metal_constraints.py` | `434, 435, 441, 457, 515` |
| `test_ip_pool_constraints.py` | `139, 140, 169` |
| `test_network_constraints.py` | `128, 129, 143` |

> `test_migrations.py` 使用动态 `head_revision()`，无需改；其 `_declared_baseline_extensions() == {"pg_trgm"}` 与“扩展存在”断言不受 `0013` 影响（`0013` 不改扩展）。`test_service_endpoint_constraints.py:218` 的 `downgrade("0011_services")` 是显式目标版本，不受 head 变化影响。

---

## 8. 数据完整性对应表（Database 视角，精简）

| 规则依据及版本 | 作用域/读取入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证（计划） |
| --- | --- | --- | --- | --- | --- |
| §17/§26 模糊搜索 | `GET /api/v1/search`（hostname/code/name） | 4 条 GIN trigram 索引存在、非唯一、非 partial | 归一化查询；`%`/`ILIKE`；去重排序 | 索引仅性能；正确性不依赖 | V-DB-139/140/142 |
| §21 未删默认 + ADMIN `include/only` | 搜索（DR-180） | 索引非 partial，覆盖含软删全集 | 查询谓词 `deleted_at` 过滤 | 软删/恢复不改索引结构 | V-DB-141 |
| §26/0001 扩展 | 迁移 | `pg_trgm` 已在 0001；`0013` 不含扩展 DDL | — | 不重复启用、不 DROP | V-DB-143 |
| §27 迁移链 | Alembic | 单 head `0013_search_indexes`；对称 up/down；无回填 | — | 结构可逆 | V-DB-139/143 |
| §4.1/§7/D01 §5 归一化 | 键列匹配 | 索引建在归一化键/已归一化列 | 应用逐码位 ASCII 折叠（禁 `str.lower()`/`upper()`） | 与应用同口径 | V-DB-142 |
| §4 稳定 ID | 结果跳转 | 无（PK 既有） | 结果携带 UUID | — | F013 功能测试 |

---

## 9. Backend / Tester 可依赖保证与验证项

**保证（DB 层）**：`resources.hostname`、`clusters.code_key`、`clusters.name`、`services.name_key` 各有一条 `USING gin (… gin_trgm_ops)` 非唯一非 partial 索引；`0013` 不含表/列/约束/触发器变更、不含 `CREATE/DROP EXTENSION`；单 head、无回填、up/down/up 对称；`pg_trgm`/`btree_gist` 前后一致。

**不保证**：`q` 长度 < 3 时走索引（pg_trgm 固有）；`q` 匹配结果（正确性由应用层算子决定）；IP 精确/前缀查询的索引支撑（本 Gate 延期，见 §4）；Dashboard 计数/容量的索引支撑（沿用各域既有索引，本 Feature 不新增）。

**计划测试项（真实 PG，V-DB-139–V-DB-143，无 PASS）**：
- **V-DB-139** 迁移 up/down/up：`0013` 后单 head=`0013_search_indexes`；down 后 4 索引消失、既有表/数据保留；re-up 恢复；down_revision=`0012_service_endpoints`。
- **V-DB-140** 索引目录：`pg_indexes` 中 4 条索引 `indexdef` 含 `USING gin` 与 `gin_trgm_ops`；`indisunique=false`、无 `WHERE` 谓词（非 partial）。
- **V-DB-141** `deleted=include/only` 覆盖：软删行仍可被 trigram 查询命中（证明索引非 partial 有意义）；`EXPLAIN` 在 `include/only` 下可走 GIN。
- **V-DB-142** `EXPLAIN (ANALYZE)`：`q`≥3 字符代表查询出现 `Bitmap Index Scan on ix_..._trgm`；`q` 长度 1–2 记录预期顺序扫描。归一化：`CN001`/` cn001 ` 与 `cn001` 命中等价（A3）。
- **V-DB-143** 迁移边界：`0013` 源码不含 `CREATE EXTENSION`/`DROP EXTENSION`；迁移前后 `pg_extension`（`pg_trgm`,`btree_gist`）一致；`alembic heads` 唯一。
- **V-DB-144**（跨 Feature，连带）上一节 §7-E4 的测试清单更新后，`test_resource_constraints`/`test_service_constraints`/各 head 断言全部复跑通过。

---

## 10. 未决项与风险

- **I-1（LOW，兼容性，非阻塞）**：`clusters.name` 无归一化键，模糊匹配与 `code_key` 口径不完全一致；属 §5 已确认边界，本 Feature 不新增键列。
- **I-2（MEDIUM，性能，非阻塞）**：跨 Cluster 全局 IP 精确查询可能顺序扫描（§4.3）。触发条件与候选索引形态已定，交 Tester 以 `EXPLAIN` 证据决定是否追加后续迁移。
- **I-3（LOW，交 Backend）**：ORM 模型需同步声明 GIN 索引，避免 metadata 漂移（§6）。
- **I-4（NOTE，交协调器）**：DR-189 的 `DB-D38` 误标需在 CONTRACT 同步 architecture 文档；`errata` 正文（§7）由协调器按变更控制同步至 F003/F004/F008/F009/F010/F011/F012 的 DB/architecture 文档与测试报告。
- **I-5（NOTE）**：本 Gate 为只读签核，全部为计划验证，无 PASS。

---

## 11. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D157–DB-D166）：迁移 `0013_search_indexes`（down_revision=`0012_service_endpoints`）；4 条非 partial GIN trigram 索引；`host(address)`/IP 索引延期裁定；匹配算子/阈值/EXPLAIN/归一化要求；跨 Feature errata（修订 DB-D30/D41/D137，澄清 DB-D89/D124/D77/D106/D152，更正 DB-D38 误标）与受影响测试清单；V-DB-139–V-DB-144。 |