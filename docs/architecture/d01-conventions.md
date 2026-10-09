# D01 共享约定基座 — 字段、归一化、时间与省略语义

- **状态**：READY（专业设计签核）
- **版本**：v7
- **签核**：Architect，2026-10-09（v7 修订；v6 2026-10-09；v5 2026-10-09；v4 2026-10-09；v3 2026-10-08；v2 2026-10-07；v1 2026-10-06）
- **依据**：requirements-v3.md revision 3（§4、§4.1、§5、§7–§12、§35.2 Q10-A/Q10-B、§35.3 D01）；docs/api/F003.md v2；docs/api/F004.md v3；docs/api/F007.md v1；docs/database/f003-cluster.md v2；docs/database/f004-resource.md v1；docs/database/f005-bare-metal.md v1；docs/database/f006-virtual-machine.md v1；docs/database/f007-interface.md v1；F004/F005/F006/F007 product/architecture；F001 DR-06 / DB-D13。
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
- **BareMetalDetail 硬件数值（F005，v4 补充）**：cpu_sockets/cpu_cores/memory_mb 为正整数或 null（1..2147483647）；gpu_count 为非负整数或 null（0..2147483647，0=明确无 GPU）；memory_mb 单位 MiB，原样存储不换算。契约见 docs/api/F004.md v3 §2.4，DB 见 database/f005-bare-metal.md DB-D46。
- **VirtualMachineDetail 容量数值（F006，v5 补充）**：vcpu/memory_mb 为正整数或 null（1..2147483647）；disk_gb 为非负整数或 null（0..2147483647，0=明确无磁盘）；memory_mb 单位 MiB、disk_gb 单位 GiB，原样存储不换算；一期不校验 VM 总 vCPU/内存是否超过 Host 容量。契约见 docs/api/F004.md v3 §2.5，DB 见 database/f006-virtual-machine.md DB-D55/DB-D56。
- **Network 地址字段（F008，v7 补充）**：cidr 为 IPv4 CIDR，host 位归一化为网络地址（PG cidr 语义）；gateway 为可空 IPv4，取值域见 §5.7；非数值计量、单位不适用。契约见 docs/api/F008.md v1 §2.2，DB 见 database/f008-network.md DB-D83/DB-D84。
- **Interface 数值（F007，v6 补充）**：speed_mbps/mtu 为正整数或 null（1..2147483647）；speed_mbps 单位 Mbps（标称速率）、mtu 单位字节；均为登记值、非实时探测，未知存 null 不以 0 代替。契约见 docs/api/F007.md v1 §2.2，DB 见 database/f007-interface.md DB-D69。

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
| Interface name | 同 Resource（未删除） | 区分（保留输入） | 禁止 | trim（不折叠大小写）；(resource_id,name) 部分唯一 WHERE deleted_at IS NULL | 是 |
| IPPool/Service name | 各自作用域 | 不敏感（保留展示） | 允许单个普通空格（不自动合并） | 归一化键+部分唯一 | 是 |
| Network name | 同 Cluster（未删除） | 不敏感（仅 ASCII A-Z→a-z 折叠，保留展示） | 允许普通空格（不自动合并） | name_key=ASCII_lower(btrim(name))；(cluster_id,name_key) 部分唯一 WHERE deleted_at IS NULL | 是 |

### 5.1 Cluster code 字符集与大小写折叠（D01 裁定，F003 I-1；v2 修订 F003-REV-1）

服务端 trim 首尾空白；trim 后非空；禁止内部空白与控制字符；允许中文及其它 Unicode 字符；长度（Unicode code point）1–64；保留展示大小写。

**code_key 仅对 ASCII `a-z` 折叠为 `A-Z`，其余码位原样保留**（应用与 DB 同一口径）：

- 应用：对 `btrim(code)` 逐字符，仅 `[a-z]`→`[A-Z]`；不得使用 `str.upper()`（其对 ß→SS、ﬁ→FI 等多码位映射，且随 Unicode 版本变化）。
- DB：`translate(btrim(code), 'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ')`；不得使用 `upper()`（其大小写映射依赖 collation/locale）。
- 理由：应用与 DB 完全一致，与 locale / Unicode 大小写表解耦，结果可预测。中文等无大小写字符不受影响；`ß`/`ﬁ` 等保持原样（如 `straße`→`STRAßE`，不与 `STRASSE` 折叠为同一键）。ASCII 范围的大小写不敏感唯一由 code_key 承载。

依据 §5 未限定 code 字符集（示例含中文候选）与 §4.1 通用规则。若后续 Product 确认 ASCII-only，改严格正则；无历史数据时成本低。

### 5.2 长度口径

Cluster code 64；Cluster name 255；**Resource hostname 253（FQDN 表示上限，RFC 1035）**；**BareMetal 硬件字符串字段（manufacturer/model/serial_number/cpu_model/gpu_model）255（v4 新增，见 §5.4）**；**VirtualMachine hypervisor 255（v5 新增，见 §5.5）**；**Interface name 64、mac_address ≤64（v6 新增，见 §5.6）**；**Network name 255（v7 新增，见 §5.7）**；其它对象字符/长度在各 Feature Database/Contract 依本节规则收窄（Unicode code point）。

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

### 5.5 VirtualMachine 字段口径（D01 裁定，F006 DB I-1；v5 新增）

适用范围：docs/api/F004.md v3 §2.5 的 virtual_machine 嵌套对象字段（host_resource_id、vcpu、memory_mb、disk_gb、hypervisor）。VM 即 Resource（1:1），公共字段（含 metadata）沿用 Resource 口径，本节不重复定义。

宿主引用 host_resource_id：必填 UUID，创建时非 null，PATCH 显式 null→422；须引用存在、未软删、resource_type=BARE_METAL 且与 VM 同 Cluster 的 Resource；违反统一 422（field="virtual_machine.host_resource_id"）。换 Host 仅限同 Cluster，写 UPDATE Audit（before/after host_resource_id）。

数值口径（镜像 docs/database/f006-virtual-machine.md DB-D55）：vcpu 为正整数或 null（1..2147483647），0/负非法；memory_mb 为正整数或 null（1..2147483647）；disk_gb 为非负整数或 null（0..2147483647，0=明确无磁盘）。未知值存 null，绝不以 0 代替。memory_mb=MiB、disk_gb=GiB，原样存储不换算；1 GiB=1024 MiB。

字符串口径（hypervisor，DR-64）：trim 首尾空白→trim 后非空→禁控制字符（Unicode Cc/Cf，应用层；DB 为 ASCII backstop，沿用 F003 I-6/F004 I-4）→长度（Unicode code point）≤255；trim 后非空或 null；空串/纯空白→422（不转 null）；区分大小写、保留展示（不折叠）；**一期无枚举，不得据值推导行为**。

无跨字段规则：容量字段各自独立可空；不做 vcpu×memory 推导、不做与 Host 容量比较（§9/T39）。

metadata：归 Resource 公共 metadata（docs/api/F004.md v3 §2.2/§3），virtual_machine 嵌套对象不接收、不暴露独立 metadata 键（I-3/DR-69）。

镜像：DB 列/约束见 docs/database/f006-virtual-machine.md v1（DB-D53–D63）；API 契约见 docs/api/F004.md v3 §2.5。本字段字典供 F014 导入复用。VM 与 Host 的删除保护、恢复重检与引用检查见 §6/§21，DB 触发器与应用检查器见 f006 文档。

### 5.6 Interface 字段口径（D01 裁定，F007 DB I-1；v6 新增）

适用范围：docs/api/F007.md v1 的 Interface 独立对象字段（name、interface_type、mac_address、speed_mbps、mtu、parent_interface、enabled、description、metadata）。Interface 为独立对象（非 Resource 1:1 明细），resource 归属与生命周期见 §6/§21 及 F007 Contract。

名称口径（name，DR-73/DB-D65）：服务端 trim 首尾空白 → trim 后非空 → 禁内部空白（Unicode White_Space）与控制字符（Unicode Cc/Cf，应用层；DB 为 ASCII backstop）→ 长度（Unicode code point）1–64；**区分大小写、保留输入大小写、不折叠**（eth0 与 ETH0 为不同名称）；同 Resource 内未软删部分唯一 (resource_id,name) WHERE deleted_at IS NULL；软删后名称可复用，恢复重检。唯一比较用 trim 后原值，不建独立归一化键列。

类型口径（interface_type，DR-74/DB-D67）：∈{PHYSICAL,VIRTUAL,BOND,BRIDGE,VLAN,LOOPBACK,OTHER}，默认 OTHER；不根据接口名推断；显式 null/非法值→422。

MAC 口径（mac_address，DR-75/DB-D68）：trim 首尾空白 → trim 后非空或 null → 禁控制字符（Cc/Cf，应用层；DB 为 ASCII backstop）→ 长度（Unicode code point）≤64；**不做格式正则校验、保留输入大小写、一期无全局唯一、允许两 Interface 同 MAC**；空串/纯空白→422（不转 null）。

数值口径（speed_mbps/mtu，DR-76/DB-D69）：speed_mbps 为接口标称速率、单位 Mbps，mtu 单位字节；两者均为正整数或 null（1..2147483647）；0/负/超限/非整数→422；未知值存 null，不以 0 代替；不表示实时流量或实时 MTU 探测。

parent_interface（DR-78）：可空 UUID，须属于同 Resource、不能指向自身、不能形成循环（应用递归校验 + DB 触发器 trg_interfaces_parent_valid 兜底）；可 PATCH 修改父接口。

enabled（DR-77/DB-D71）：boolean，默认 true，登记状态非实时探测；显式 null→422。description：可空文本；无唯一。

metadata（DR-83/DB-D72）：**归 Interface 自有**（§10 权威），JSON object、默认 {}、整值替换；非 object/null→422；不并入 Resource 公共 metadata（覆盖 product I-5 原 PROPOSED）。

归属与不可变性（DR-79/DB-D74）：resource 创建必填、须引用存在未软删 Resource（缺失/不存在/软删→422），**创建后不可改**（PATCH 出现→422）；DB 触发器 trg_interfaces_immutable_resource 兜底。

镜像：DB 列/约束见 docs/database/f007-interface.md v1（DB-D64–D79）；API 契约见 docs/api/F007.md v1。本字段字典供 F014 导入复用。

### 5.7 Network 字段口径（D01 裁定，F008 DB I-2；v7 新增）

适用范围：docs/api/F008.md v1 的 Network 独立对象字段（cluster、name、cidr、gateway、status、auto_allocate、description、metadata）。

名称口径（name，DR-90/DB-D81）：trim 首尾空白 → trim 后非空 → 禁控制字符（Unicode Cc/Cf，应用层；DB 为 ASCII backstop）→ 长度（Unicode code point）1–255；允许中文及内部普通空格且不自动合并；仅 ASCII A-Z→a-z 折叠、非 ASCII 原样、保留展示大小写；name_key=ASCII_lower(btrim(name))（应用逐码位、DB translate、禁 lower()/str.lower()，locale 无关）；同 Cluster 未软删 (cluster_id,name_key) 部分唯一 WHERE deleted_at IS NULL；软删后可复用，恢复重检冲突不覆盖。

cidr（DR-91/DB-D83）：合法 IPv4 CIDR，PG 原生 cidr；host 位接受并归一化为网络地址（'10.0.0.5/24'→'10.0.0.0/24'）；仅 IPv4（family=4）；非 IPv4/非法→422；同 Cluster 未软删不重叠（排他约束），INACTIVE 参与。

gateway（DR-93/DB-D84）：可空 IPv4（inet）；填写时①属该 CIDR 基础可用地址（/0–/30 排网络/广播；/31 两址可用；/32 必空）②非 §11.1 禁用范围（0.0.0.0/8、127.0.0.0/8、169.254.0.0/16、224.0.0.0/4、240.0.0.0/4）；违反→422 field="gateway"；从可分配集合排除供 F009/F010/F013 共用；「已占用 IP 设为 gateway」冲突检测归 F009/F010（I-5）。

status/auto_allocate（DR-94/DB-D85）：status ∈{ACTIVE,INACTIVE} 默认 ACTIVE，INACTIVE 禁新增分配、仍参与重叠检查；auto_allocate boolean 默认 false，仅控自动分配、不绕过状态/地址约束；显式 null/非法→422。

metadata（DR-95/DB-D86）：Network 自有 JSONB，object、默认 {}、整值替换；非 object/null→422；不并入 Resource 公共 metadata（覆盖 product I-6 PROPOSED）。

cluster（DR-89/DB-D80）：创建必填 UUID 或 code，须引用存在未软删 Cluster，否则 422 field="cluster"；有未删除 Pool/IP 引用时不可改，无引用时可改并重检目标 Cluster（I-4）。

镜像：DB 列/约束见 docs/database/f008-network.md v1（DB-D80–D94）；API 契约见 docs/api/F008.md v1。本字段字典供 F014 导入复用。

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
| v5 | 2026-10-09 | §3 追加 VirtualMachineDetail 容量数值引用；§5.2 追加 hypervisor 长度 255；新增 §5.5 VirtualMachine 字段口径（host 必填/四条件、vcpu/memory_mb 正整数、disk_gb 非负且 0=明确无磁盘、MiB/GiB、hypervisor trim/≤255/无枚举、无跨字段、metadata 归 Resource） | F006 DB I-1 与 Contract v3 定稿 |
| v6 | 2026-10-09 | §3 追加 Interface 数值上限引用；§5.2 追加 Interface name 64 与 mac_address ≤64；§5 表 Interface name 行明确「未删除」范围与不折叠口径；新增 §5.6 Interface 字段口径（name 1–64 区分大小写 trim 禁内部空白、类型 7 值默认 OTHER 不推断、mac ≤64 无正则无唯一、speed_mbps/mtu 正整数或 null、parent 同 Resource 禁自引用/环、enabled 默认 true、metadata Interface 自有、resource 创建必填不可改） | F007 DB I-1 与 Contract v1 定稿（DR-87） |
| v7 | 2026-10-09 | §3 追加 Network 地址字段引用；§5.2 追加 Network name 255；§5 表新增 Network name 行；新增 §5.7 Network 字段口径（name 1–255 仅 ASCII 折叠、cidr host 位归一化、gateway 取值域 /31 /32 禁用 5 段、status/auto_allocate 默认、metadata 自有、cluster 创建必填与有引用不可改） | F008 DB I-2 与 Contract v1 定稿（DR-90/93/95/101） |
