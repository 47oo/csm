# D01 共享约定基座 — 字段、归一化、时间与省略语义

- **状态**：READY（专业设计签核）
- **版本**：v2
- **签核**：Architect，2026-10-07（v2 修订；v1 签核 2026-10-06）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§5、§7–§12、§35.2 Q10-A/Q10-B、§35.3 D01）；docs/api/F003.md v2；docs/database/f003-cluster.md v2；F001 DR-06 / DB-D13。
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
| Resource hostname | 同 Cluster（未删除） | 不敏感（存小写） | 禁止 | 小写+trim；部分唯一 WHERE deleted_at IS NULL | 是 |
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

Cluster code 64；Cluster name 255；其它对象字符/长度在各 Feature Database/Contract 依本节规则收窄（Unicode code point）。

## 6. 归属与引用

对象「所属对象」（如 Resource 的 Cluster、Pool 的 Network）在创建时必填；具体可空性按各条款。引用以稳定 UUID 表达；删除前做未删除引用检查，不隐式级联（§21）。

## 7. 变更与引用

本文件为 D01 共享约定的单一权威来源；API Contract、数据库设计与导入校验引用之，不复制发散。修改本节约定需 Architect 签核；涉及已确认业务口径时交 Product 核对。

## 8. 修订记录

| 版本 | 日期 | 变更 | 原因 |
| --- | --- | --- | --- |
| v1 | 2026-10-06 | 首版（F003 落地签核） | — |
| v2 | 2026-10-07 | 明确 code_key 仅 ASCII 字母折叠、非 ASCII 原样保留；同步 §5 表与 §5.1 | F003-REV-1 |
