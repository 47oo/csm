# D01 共享约定基座 — 字段、归一化、时间与省略语义

- **状态**：READY（专业设计签核）
- **版本**：v4
- **签核**：Architect，2026-10-09（v4 修订；v3 2026-10-08；v2 2026-10-07；v1 2026-10-06）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§5、§7–§12、§35.2 Q10-A/Q10-B、§35.3 D01）；docs/api/F003.md v2；docs/api/F004.md v2；docs/database/f003-cluster.md v2；docs/database/f004-resource.md v1；docs/database/f005-bare-metal.md v1；F004/F005 product/architecture；F001 DR-06 / DB-D13。
- **覆盖**：API 与导入共用的字段格式、稳定 ID、时间、单位、nullable/PATCH 省略语义、名称归一化口径。F003 首落地签核；后续 Feature 引用本文件不重复定义；数据库列级设计仍归各 Feature Database 文档。

## 1. 稳定 ID（§4 / DB-D13）

- 业务对象主键为 PostgreSQL 原生 UUID，默认 gen_random_uuid()；不启用 pgcrypto/uuid-ossp。
- 内部关联与审计标识一律用稳定 UUID，不用 hostname/name/code 字符串拼接。
- 对象改名/改 code 不改 id；审计 object_id 恒等于对象 id。

## 2. 时间契约（F001 DR-06 / DB-D19）

- 存储 timestamptz，UTC。
- 接口 ISO-8601 带偏移，例 2026-10-06T12:00:00+00:00。
- 展示按 DISPLAY_TIMEZONE（默认 UTC）呈现；后端不做隐式本地化。
- updated_at 由业务写路径维护（非 DB 触发器）；created_at 默认 now()。

## 3. 单位与数值（§8/§9/§26）

- *_mb = MiB，*_gb = GiB；1 GiB = 1024 MiB。不混用 MB/GB。
- 容量/数量字段为整数；未知值存 null，不得以 0 表示未知（gpu_count/disk_gb 的 0 表示明确无该项）。
- 通用整型上限 0..2147483647（非负项）或按各域正整数约束收窄（F005/F006 落实）；具体范围在各 Feature Database 文档。
- **BareMetalDetail 硬件数值（F005，v4 补充）**：cpu_sockets/cpu_cores/memory_mb 为正整数或 null（1..2147483647）；gpu_count 为非负整数或 null（0..2147483647，0=明确无 GPU）；memory_mb 单位 MiB，原样存储不换算。契约见 docs/api/F004.md v2 §2.4，DB 见 database/f005-bare-metal.md DB-D46。

## 4. nullable 与 PATCH 省略语义（§4.1）

- 创建：默认值仅在创建时字段省略时生效。
- 更新（PATCH）：字段省略=保持原值不重置为默认；使用 Pydantic exclude_unset。
- 显式 null 仅可清空 nullable 字段；对必填/非 nullable 字段显式 null→422。
- 结构字段（如 metadata）为整值替换语义。
- 不可变字段（如 Cluster code）出现在更新请求体→422。
- 未知/只读字段出现在请求体→422。

## 5. 名称归一化与作用域（§4.1/§5/§7，Q10-B）

统一规则：所有名称去除首尾空白→非空校验→禁控制字符（Unicode Cc/Cf）；长度上限按对象。唯一性比较用归一化键；仅未删除对象参与唯一（Cluster code 例外：全量含软删）。

| 对象 | 唯一范围 | 大小写 | 内部空白 | 归一化键 | 删除后复用 |
| --- | --- | --- | --- | --- | --- |
| Cluster code | 全局（含软删） | 仅 ASCII 字母不敏感（非 ASCII 原样） | 禁止（含内部） | code_key=ASCII_upper(btrim(code))，全量唯一 | 否 |
| Cluster name | 无唯一 | 保留 | 允许普通空格 | 仅 trim+校验 | n/a |
| Resource hostname | 同 Cluster（未删除） | 不敏感（仅 ASCII A-Z→a-z，存小写；非 ASCII 原样） | 禁止 | hostname_key=ASCII_lower(btrim(hostname))；部分唯一 WHERE deleted_at IS NULL | 是 |
| Interface name | 同 Resource | 区分（保留） | 禁止 | trim；部分唯一 | 是 |
| Network/IPPool/Service name | 各自作用域 | 不敏感（保留展示） | 允许单个普通空格（不自动合并） | 归一化键+部分唯一 | 是 |

### 5.1 Cluster code 字符集与大小写折叠（D01 裁定，F003 I-1；v2 修订 F003-REV-1）

服务端 trim 首尾空白；trim 后非空；禁止内部空白与控制字符；允许中文及其它 Unicode 字符；长度（Unicode code point）1–64；保留展示大小写。

**code_key 仅对 ASCII `a-z` 折叠为 `A-Z`，其余码位原样保留**（应用与 DB 同一口径）：

- 应用：对 `btrim(code)` 逐字符，仅 `[a-z]`→`[A-Z]`；不得使用 `str.upper()`（其对 ß→SS、ﬁ→FI 等多码位映射，且随 Unicode 版本变化）。
- DB：`translate(btrim(code), 'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')`；不得使用 `upper()`（其大小写映射依赖 collation/locale）。
- 理由：应用与 DB 完全一致，与 locale / Unicode 大小写表解耦，结果可预测。中文等无大小写字符不受影响；`ß`/`ﬁ` 等保持原样（如 `straße`→`STRAßE`，不与 `STRASSE` 折叠为同一键）。ASCII 范围的大小写不敏感唯一由 code_key 承载。

依据 §5 未限定 code 字符集（示例含中文候选）与 §4.1 通用规则。若后续 Product 确认 ASCII-only，改严格正则；无历史数据时成本低。

### 5.2 长度口径

Cluster code 64；Cluster name 255；**Resource hostname 253（FQDN 表示上限，RFC 1035）**；**BareMetal 硬件字符串字段（manufacturer/model/serial_number/cpu_model/gpu_model）255（v4 新增，见 §5.4）**；其它对象字符/长度在各 Feature Database/Contract 依本节规则收窄（Unicode code point）。

### 5.3 Resource hostname 字符集、长度与折叠（D01 裁定，F004 I-1）

服务端 trim 首尾空白 → trim 后非空 → 禁止内部空白（Unicode White_Space）与控制字符（Cc/Cf）→ 长度（Unicode code point）1–253 → 存归一化小写展示值。允许中文及其它 Unicode（宽松规则，与 §5.1 Cluster code 同源）；允许 `.`（FQDN）；短名与 FQDN 按完整字符串识别，不合并别名。

**大小写折叠仅对 ASCII `A-Z` 折叠为 `a-z`，其余码位原样保留**（应用与 DB 同一口径，locale 无关）：

- 应用：对 `btrim(hostname)` 逐码位，仅 `[A-Z]`→`[a-z]`；**不得使用 `str.lower()`**（对 `İ`/`ß` 等映射随 Unicode 版本变化且与 DB 不一致）。
- DB：`translate(btrim(hostname),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')`；**不得使用 `lower()`**（依赖 collation/locale）。
- `hostname_key = ASCII_lower(btrim(hostname))`；同 Cluster `(cluster_id, hostname_key)` 部分唯一 `WHERE deleted_at IS NULL`（软删可重用、跨 Cluster 允许、恢复重检冲突）。与 Cluster code 全量唯一（含软删）口径相反，不可互换。

依据 §7「去除首尾空白并统一转小写保存」「支持短主机名和 FQDN」「禁内部空白和不合法字符」，及 §35.3 D01。宽松字符集不收紧现有命名，无需 Product 核对。

### 5.4 BareMetal hardware 字段口径（D01 裁定，F005 DB I-1；v4 新增）

适用范围：docs/api/F004.md v2 §2.4 的 hardware 嵌套对象 9 个硬件字段。硬件字段为描述性属性、非业务名称，**不设唯一性与归一化键**。

字符串口径（DR-52）：服务端 trim 首尾空白 → trim 后非空 → 禁控制字符（Unicode Cc/Cf，应用层；DB 为 ASCII backstop，沿用 F003 I-6/F004 I-4）→ 长度（Unicode code point）≤255；trim 后非空或 null；**空串/纯空白→422（不转 null）**；显式 null→清空该 nullable 子字段；区分大小写、保留展示（不折叠）。

数值口径（DR-50/DB-D46）：cpu_sockets/cpu_cores/memory_mb 为正整数或 null（1..2147483647）；gpu_count 为非负整数或 null（0..2147483647，0=明确无 GPU）；未知值存 null，绝不以 0 代替。

cpu_cores 语义（§8/T39）：整台裸金属物理核心总数、不含超线程；不自动探测、不做 cpu_sockets×cpu_cores 等跨字段推导。

镜像：DB 列/约束见 docs/database/f005-bare-metal.md v1（DB-D46/DB-D52）；API 契约见 docs/api/F004.md v2 §2.4。本字段字典供 F014 导入复用。

## 6. 归属与引用

对象「所属对象」（如 Resource 的 Cluster、Pool 的 Network）在创建时必填；具体可空性按各条款。引用以稳定 UUID 表达；删除前做未删除引用检查，不隐式级联（§21）。

## 7. 变更与引用

本文件为 D01 共享约定的单一权威来源；API Contract、数据库设计与导入校验引用之，不复制发散。修改本节约定需 Architect 签核；涉及已确认业务口径时交 Product 核对。

## 8. 修订记录

| 版本 | 日期 | 变更 | 原因 |
| --- | --- | --- | --- |
| v1 | 2026-10-06 | 首版（F003 落地签核） | — |
| v2 | 2026-10-07 | 明确 code_key 仅 ASCII 字母折叠、非 ASCII 原样保留；同步 §5 表与 §5.1 | F003-REV-1 |
| v3 | 2026-10-08 | §5 表 Resource hostname 行、§5.2 长度、新增 §5.3；裁定 hostname 1–253、宽松字符集、仅 ASCII A-Z→a-z 折叠、部分唯一 | F004 DB I-1 与 Contract 定稿 |
| v4 | 2026-10-09 | §3 追加 BareMetal 硬件数值上限引用；§5.2 追加硬件字符串长度 255；新增 §5.4 BareMetal hardware 字段口径 | F005 DB I-1 与 Contract v2 定稿 |
