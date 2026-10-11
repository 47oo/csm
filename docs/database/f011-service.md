# F011 Service 服务登记 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§15、§16、§21、§22、§23、§25、§26、§27、§28、§31 T21/T23/T24/T25/T26/T37/T40/T41、§32/§33、§35.2 Q02-A/Q06/Q10-A/Q10-B、§35.3 D01/D02）；`docs/features/F011/product.md`（A1–A18、I-1–I-6）；`docs/features/F011/architecture.md`（DR-140–DR-154）；`docs/api/F011.md` 草案 v0；`docs/database/f001-baseline.md` v1（DB-D4/DB-D6/DB-D7）、`f004-resource.md` v1（DB-D35/DB-D41）、`f007-interface.md` v1、`f009-ip-pool.md` v1（DB-D95–D110）、`f010-ip-address.md` v1（DB-D111–D127）、`f008-network.md` v1；`docs/architecture/d01-conventions.md` v9（目标 v10 §5.10）；`backend/alembic/versions/0009_ip_pools.py`、`0010_ip_addresses.py`
- **覆盖**：`services` 表、字段/类型/必填/默认、约束/索引/FK 命名、name/name_key 归一化键与部分唯一（DR-141）、status（DR-142）、metadata（DR-143）、resource 归属（DR-144）、索引集合、FK 语义与引用检查落点（DR-146/147/148）、迁移 `0011_services`、真 PG 验证项（V-DB-112–V-DB-125）、D01 v10 §5.10 交核依据、已有数据影响。不覆盖 `docs/api/F011.md` 定稿、D01 v10 签核、ServiceEndpoint 本体（F012）、TEST 执行与实现。

## 1. 设计决策汇总（DB-D128–DB-D141）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D128 | `services` 独立对象表（非 Resource 1:1 明细）：`id` UUID PK `pk_services` 默认 `gen_random_uuid()`；软删/恢复/Activity/乐观锁；经 `resource_id` 关联 Resource，经 Resource 间接归属 Cluster（不落 cluster 直列） | CONFIRMED（§4/§15/§21/DR-140）+DESIGN |
| DB-D129 | `resource_id` UUID NOT NULL FK `fk_services_resource_id_resources`→`resources(id)` ON DELETE RESTRICT + `ix_services_resource_id`；引用须存在、未软删（应用 422 field="resource"）；创建必填、创建后不可改（应用 422，DR-144）；**不建**不可变触发器 | CONFIRMED（§4.1/§15/§21/DR-144）+DESIGN |
| DB-D130 | `name` varchar(255) NOT NULL + `ck_services_name_not_blank/_trimmed/_no_control/_length`；`name_key` varchar(255) NOT NULL + `ck_services_name_key_matches`（`ASCII_lower(btrim(name))`，DB `translate`，禁 `lower()`） | PROPOSED→CONTRACT(1–255)+DESIGN（DR-141/D01 §5.10） |
| DB-D131 | 部分唯一 `uq_services_resource_id_name_key` UNIQUE(resource_id, name_key) WHERE deleted_at IS NULL | CONFIRMED（§4.1/§27/DR-141）+DESIGN |
| DB-D132 | `status` varchar(16) NOT NULL DEFAULT 'UNKNOWN' + `ck_services_status` IN ('RUNNING','STOPPED','UNKNOWN')；人工维护、非探测、不由名称推导 | CONFIRMED（§15/T21/DR-142）+DESIGN |
| DB-D133 | `metadata` JSONB NOT NULL DEFAULT `'{}'::jsonb` + `ck_services_metadata_object`（`jsonb_typeof(metadata)='object'`）；Service 自有，整值替换，不并入 Resource | PROPOSED→CONTRACT/D01（DR-143/I-1）+DESIGN |
| DB-D134 | `description` text NULL（无长度上限，同 F003/F004/F007/F008/F009） | DESIGN（D01 §5.10 拟） |
| DB-D135 | `version` integer NOT NULL DEFAULT 1 CHECK ≥1；`created_at`/`updated_at` timestamptz NOT NULL `now()`（`updated_at` 应用维护，无触发器）；`deleted_at` timestamptz NULL 软删 | DESIGN |
| DB-D136 | **不建** `resource_id` 不可变触发器：不可改为 CONTRACT 层规则，应用 PATCH 出现 `resource`/`resource_id` → 422。沿用 F008/F009/F010 先例 | DESIGN（DR-144 裁定） |
| DB-D137 | 索引集合：`uq_services_resource_id_name_key`（部分唯一）+ `ix_services_resource_id`、`ix_services_status`、`ix_services_deleted_at`；**不建** pg_trgm/GIN、不建 name/name_key 单列 B-tree、不建额外复合索引 | DESIGN |
| DB-D138 | 迁移 `0011_services`，`down_revision=0010_ip_addresses`；**不重复启用** pg_trgm/btree_gist（0001/0008 已启用）；单一 head、全表新建无回填、对称可逆 | DESIGN（DR-151） |
| DB-D139 | F011 注册 Resource←未删 Service 引用检查器（与 F006/F007 同机制，收窄 F004 DELETE /resources）；Service 删除引用集由 `register_service_reference_checker` 扩展点承担（F011 默认空集，F012 注册真实 Endpoint provider）；DB 仅 FK RESTRICT 保证物理删除完整性 | CONFIRMED（§21/DR-146/DR-147）+DESIGN |
| DB-D140 | D01 v9→v10 §5.10 的 DB 依据：name 1–255、name_key=ASCII_lower(btrim(name))、status 默认/取值、description text 无上限、metadata Service 自有 object 默认 {}、resource 创建必填不可改；(resource_id,name_key) 部分唯一 | PROPOSED→CONTRACT/D01（I-1/I-3/DR-152）+DESIGN |
| DB-D141 | 100% 新建对象，无已有数据迁移；downgrade 丢弃 `services` 数据不可逆，生产回滚用 F001 全库备份 | DESIGN |

## 2. `services` 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK `pk_services` |
| resource_id | UUID | NOT NULL | — | FK `fk_services_resource_id_resources`→`resources(id)` ON DELETE RESTRICT；`ix_services_resource_id` |
| name | varchar(255) | NOT NULL | — | `ck_services_name_not_blank`/`_trimmed`/`_no_control`/`_length` |
| name_key | varchar(255) | NOT NULL | — | `ck_services_name_key_matches`（translate 口径） |
| status | varchar(16) | NOT NULL | `'UNKNOWN'` | `ck_services_status`：IN ('RUNNING','STOPPED','UNKNOWN') |
| description | text | NULL | — | — |
| metadata | JSONB | NOT NULL | `'{}'::jsonb` | `ck_services_metadata_object`（`jsonb_typeof(metadata)='object'`）；ORM 属性建议 `meta`（同 F004/F007，避免与 `MetaData` 冲突） |
| version | integer | NOT NULL | 1 | `ck_services_version`：≥1 |
| created_at/updated_at | timestamptz | NOT NULL | `now()` | UTC；`updated_at` 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

CHECK 形态（`ck_` 由 naming convention 展开为 `ck_services_<name>`）：

| 约束名 | 表达式 |
| --- | --- |
| ck_services_name_not_blank | `btrim(name) <> ''` |
| ck_services_name_trimmed | `name = btrim(name)` |
| ck_services_name_no_control | `name !~ '[[:cntrl:]]'`（ASCII backstop；内部普通空格允许，不合并） |
| ck_services_name_length | `char_length(name) BETWEEN 1 AND 255` |
| ck_services_name_key_matches | `name_key = translate(btrim(name), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')` |
| ck_services_status | `status IN ('RUNNING','STOPPED','UNKNOWN')` |
| ck_services_metadata_object | `jsonb_typeof(metadata) = 'object'` |
| ck_services_version | `version >= 1` |

约束/索引：

- `uq_services_resource_id_name_key` UNIQUE(resource_id, name_key) WHERE deleted_at IS NULL（部分唯一）。
- `ix_services_resource_id`、`ix_services_status`、`ix_services_deleted_at`。
- **无**不可变触发器（DB-D136）；**无** pg_trgm/GIN；**无** name/name_key 单列 B-tree。

DDL（关键片段，供迁移使用）：

```sql
CREATE TABLE services (
    id          uuid        NOT NULL DEFAULT gen_random_uuid(),
    resource_id uuid        NOT NULL,
    name        varchar(255) NOT NULL,
    name_key    varchar(255) NOT NULL,
    status      varchar(16) NOT NULL DEFAULT 'UNKNOWN',
    description text,
    metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    version     integer     NOT NULL DEFAULT 1,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    deleted_at  timestamptz,
    CONSTRAINT pk_services PRIMARY KEY (id),
    CONSTRAINT fk_services_resource_id_resources
        FOREIGN KEY (resource_id) REFERENCES resources(id) ON DELETE RESTRICT,
    CONSTRAINT ck_services_name_not_blank CHECK (btrim(name) <> ''),
    CONSTRAINT ck_services_name_trimmed   CHECK (name = btrim(name)),
    CONSTRAINT ck_services_name_no_control CHECK (name !~ '[[:cntrl:]]'),
    CONSTRAINT ck_services_name_length
        CHECK (char_length(name) BETWEEN 1 AND 255),
    CONSTRAINT ck_services_name_key_matches CHECK (
        name_key = translate(btrim(name),
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')),
    CONSTRAINT ck_services_status
        CHECK (status IN ('RUNNING','STOPPED','UNKNOWN')),
    CONSTRAINT ck_services_metadata_object
        CHECK (jsonb_typeof(metadata) = 'object'),
    CONSTRAINT ck_services_version CHECK (version >= 1)
);

CREATE UNIQUE INDEX uq_services_resource_id_name_key
    ON services (resource_id, name_key) WHERE deleted_at IS NULL;

CREATE INDEX ix_services_resource_id ON services (resource_id);
CREATE INDEX ix_services_status      ON services (status);
CREATE INDEX ix_services_deleted_at  ON services (deleted_at);
```

不落字段（§15/§16/DR-140/DR-143）：IP、端口、协议、监听地址（归 F012 ServiceEndpoint）；`cluster` 直接字段（经 Resource 间接）；`service_type` 枚举；实时探测状态；自动部署/同步标记。

## 3. 交核裁定

### 3.1 DR-141 name / name_key 归一化键与部分唯一（DB-D130/DB-D131）
name：trim→非空→禁控制字符（应用 Unicode Cc/Cf；DB `[[:cntrl:]]` ASCII backstop，允许内部普通空格且不合并）→长度 1–255→保留展示大小写。`name_key = ASCII_lower(btrim(name))`（仅 ASCII A-Z→a-z，非 ASCII 原样；应用逐码位、DB `translate`，禁 `lower()`）；`ck_services_name_key_matches` 锁定。唯一：`uq_services_resource_id_name_key` UNIQUE(resource_id, name_key) WHERE deleted_at IS NULL；同 Resource 未删唯一、跨 Resource 允许、软删释放、恢复重检不覆盖。与 F009 IPPool 同构（作用域列换为 resource_id）。

### 3.2 DR-142 status（DB-D132）
`varchar(16) NOT NULL DEFAULT 'UNKNOWN'` + CHECK 3 值；显式 null/非法→应用 422；枚举扩展走迁移（不用原生 ENUM）。DB 只保证取值域与默认；「人工维护、非探测、不由名称推导」为业务规则。

### 3.3 DR-143 metadata（DB-D133）
§15 已列 metadata → CONFIRMED 字段；归属 Service 自有 JSONB。NOT NULL DEFAULT `'{}'::jsonb` + `jsonb_typeof='object'` CHECK；非 object/null→应用 422；整值替换；响应暴露；不并入 Resource。物理列 `metadata`（ORM 属性建议 `meta`）。

### 3.4 DR-144 resource 归属与不可变（DB-D129/DB-D136）
`resource_id UUID NOT NULL` FK→`resources(id)` RESTRICT + `ix_services_resource_id`；引用须存在未软删（应用 422）；DB 不表达软删引用。**不可变：应用 422，不建 DB 触发器**（沿用 F008/F009/F010 先例；后果由 FK + 引用检查器兜底）；迁移以删除重建表达；无 resource_type 限制。

### 3.5 索引集合（DB-D137）

| 索引/约束 | 服务的查询或约束 | 说明 |
| --- | --- | --- |
| `uq_services_resource_id_name_key`（部分唯一） | 同 Resource 未删 name 唯一；恢复重检；`GET /services?resource_id=` 排序扫描 | 唯一载体；resource_id 前导 |
| `ix_services_resource_id` | 列表 resource_id 过滤；Resource←Service 引用检查器；FK RESTRICT | 全量 btree（含软删） |
| `ix_services_status` | 列表 status 过滤 | 低基数，已确认基线 |
| `ix_services_deleted_at` | deleted=include/only | 与既有 Feature 一致 |

不建 pg_trgm/GIN；不建 name/name_key 单列 B-tree；不新增复合索引。

### 3.6 生命周期、引用与跨 Feature 落点（DB-D139，DR-145/146/147/148）
- 软删/恢复：`deleted_at`；恢复重新进入部分唯一，冲突被拒→应用 409 unique_conflict{name}，不覆盖；另重检 Resource 未软删（应用 dependency_deleted）；不级联、不恢复 Endpoint。
- Service←ServiceEndpoint：DB 无约束；F011 `register_service_reference_checker`（默认空集）；F012 注册真实 provider；T23 端到端留 F012。
- Resource←Service：F011 注册未删 Service 检查器，阻塞 Resource 删除（409 reference_exists，references 含 service）；DB 仅 FK RESTRICT（物理）。
- 乐观锁：version CHECK + 条件 UPDATE。

### 3.7 并发与生命周期边界

| 场景 | DB 机制 | 应用机制 |
| --- | --- | --- |
| 创建/改名/恢复同名 | 部分唯一原子兜底 | 归一化键 → 409 unique_conflict{field:"name"}；软删释放；恢复冲突拒 |
| 乐观锁 | version CHECK + 条件 UPDATE | rowcount=0 → 409 VERSION_CONFLICT |
| resource 引用 | FK NOT NULL RESTRICT（物理） | 创建校验→422；PATCH 含 resource→422 |
| Resource 删除 | FK RESTRICT（物理） | F011 引用检查器→409 reference_exists |
| Service 删除 | 无（Endpoint 在 F012） | check_service_references（F011 空集）→409 reference_exists；不级联 |
| 恢复重检 | deleted_at + 部分唯一 | 重检 name→Resource；失败不覆盖 |
| 审计（§22） | 复用 audit_logs（0003） | 同事务；object_type="service"；四类 action |

## 4. 迁移 `0011_services`

- `revision = "0011_services"`、`down_revision = "0010_ip_addresses"`；单一 head。
- **不重复启用扩展**：pg_trgm 由 `0001`、btree_gist 由 `0008` 启用；本迁移不含 `CREATE EXTENSION`。
- 无回填（全表新建）。

upgrade 顺序：1. create_table（列 + PK + FK + 全部 CHECK）；2. 部分唯一索引 `uq_services_resource_id_name_key`；3. 三个普通索引。（无触发器、无函数。）

downgrade（对称逆序）：drop 三普通索引 → drop 部分唯一索引 → drop_table("services")；**不 DROP pg_trgm / btree_gist**（F001 DB-D4）。

校验计划：真库 `up → down → up`；`alembic heads` 唯一 = `0011_services`；对象齐全；`pg_extension` 前后无新增；无回填。

## 5. 数据完整性对应表（Database 视角，精简）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证（计划） |
| --- | --- | --- | --- | --- | --- |
| §4.1/§27/DR-141 name 同 Resource 未删唯一 | POST/PATCH/restore | 部分唯一 (resource_id,name_key) WHERE deleted_at IS NULL；name_key CHECK | trim；ASCII 折叠；409 unique_conflict{field:"name"} | 索引仲裁；软删释放；恢复冲突拒 | V-DB-115/116/123 |
| §4.1/T40 name 规范 | POST/PATCH | ck_services_name_*（ASCII backstop）+ 1–255 | trim→非空→禁 Cc/Cf；内部普通空格/中文保留不合并 | Cc/Cf 应用责任 | V-DB-114 |
| §4.1/§15/§21/DR-144 resource 引用与不可变 | POST/PATCH | FK NOT NULL RESTRICT；无不可变触发器 | 缺/不存在/软删→422；PATCH 含 resource→422 | 物理删 RESTRICT | V-DB-120/121 |
| §15/T21/DR-142 status | POST/PATCH | CHECK + DEFAULT 'UNKNOWN' | 省略→UNKNOWN；非法/null→422 | 枚举扩展走迁移 | V-DB-117 |
| §15/DR-143 metadata | POST/PATCH | JSONB NOT NULL DEFAULT '{}'；jsonb_typeof='object' | 非 object/null→422；整值替换 | — | V-DB-118 |
| §21/§16/DR-146 Endpoint 引用保护 | DELETE Service | 无（Endpoint 在 F012） | register_service_reference_checker（空集）→409 reference_exists；不级联 | F012 注册真实 provider | F011 桩 + F012 端到端（T23） |
| §21/DR-147 Resource←Service 引用 | DELETE Resource (F004) | FK RESTRICT（物理） | F011 注册检查器；未删 Service→409 reference_exists | 软删释放；恢复重检 | F004/F011 集成 |
| §21/DR-148 恢复重检 | restore Service | deleted_at + 部分唯一 | 重检 name 唯一、Resource 未软删；失败不覆盖 | 索引仲裁 | V-DB-116/123 |
| §23 乐观锁 | PATCH/DELETE/restore | version CHECK + 条件 UPDATE | rowcount=0→409 | 真并发 | V-DB-119 |
| §22 Audit | 四 action | 复用 audit_logs | 同事务；object_type="service" | — | F011 集成 |
| §26/§27 真实 PG | 迁移/约束 | 0011 up/down/up、单 head、无回填、扩展不重复启用 | — | — | V-DB-112/125 |

## 6. D01 v10 §5.10 交核依据（DB-D140）

- name：1–255；trim → 非空 → 禁 Cc/Cf；允许中文及内部普通空格、不合并；保留展示大小写；仅 ASCII A-Z→a-z 折叠。
- name_key：`ASCII_lower(btrim(name))`（应用逐码位、DB `translate`、禁 `lower()`，locale 无关）。
- 唯一作用域：同 Resource、仅未删除；载体 `uq_services_resource_id_name_key UNIQUE(resource_id,name_key) WHERE deleted_at IS NULL`；删除后复用；恢复重检不覆盖。D01 v9 §5 表「IPPool/Service name」合并行需拆为 Service 单列一行。
- status：∈{RUNNING,STOPPED,UNKNOWN}，默认 UNKNOWN，人工维护。
- description：可空文本，无长度上限。
- metadata：Service 自有 JSONB，object、默认 {}、整值替换。
- resource：创建必填、须存在未软删、创建后不可改（API 422；DB 无不可变触发器）。
- 不落字段：IP/端口/协议/监听地址、cluster 直列、service_type、实时探测状态、自动部署标记。

## 7. Backend 可依赖保证与测试项

**保证（DB 层）**：`id` 唯一（PK）；`resource_id` 非空指向存在 Resource（FK），物理删被引用 Resource 被 RESTRICT 拒；同 Resource 未删 `(resource_id,name_key)` 唯一、跨 Resource 允许、软删释放、恢复冲突被拒；name 已 trim 非空、无 ASCII 控制字符、1–255，内部普通空格与中文保留不合并；name_key 恒等于 `ASCII_lower(btrim(name))`；status 恒 3 值默认 UNKNOWN；metadata 恒 object 默认 {}；description 可空无上限；version ≥1 默认 1；索引集合存在且无 pg_trgm/GIN、无 name/name_key 单列 B-tree；0011 有真实 downgrade、单一 head、无回填、扩展不重复启用。

**不保证（应用/Contract 层）**：resource 软删时点校验（应用 422）；resource_id 不可变（应用 422）；Unicode Cc/Cf（DB 仅 ASCII backstop）；Endpoint 引用保护（F012 provider）；Resource←Service 软删引用保护（应用检查器）；status「非探测、不由名称推导」（业务规则）；`name ILIKE` 性能（正确性保证）。

**计划测试项（真实 PG，V-DB-112–V-DB-125，无 PASS）**：
- **V-DB-112** 迁移 up/down/up；down_revision=0010_ip_addresses；单 head=0011_services；对象齐全（9 CHECK、1 PK、1 FK、1 部分唯一 + 3 普通索引）；无回填；扩展无新增。
- **V-DB-113** 默认/NOT NULL：id/status/metadata/version/created_at/updated_at 默认；resource_id/name/name_key NOT NULL。
- **V-DB-114** name 边界：空/纯空白/首尾/ASCII 控制/256 拒；1 与 255 接受；内部普通空格与中文保留不合并。
- **V-DB-115** name_key CHECK：SSH/ssh 同键；`ß`/`ﬁ` 原样；与 translate 一致；不一致 name_key 被拒。
- **V-DB-116** 部分唯一：同 Resource 大小写重名拒；跨 Resource 允许；软删重建；存活同名拒；恢复冲突拒；并发仅一成功。
- **V-DB-117** status：省略→UNKNOWN；三值可存；非法/显式 NULL 拒。
- **V-DB-118** metadata：默认 {}；非 object 拒；显式 NULL 拒；整值替换。
- **V-DB-119** version 默认 1、<1 拒；乐观锁双会话仅一成功。
- **V-DB-120** FK RESTRICT：物理删有未删 Service 的 Resource 拒；软删 Service 行仍在；软删 Resource 不删 services 行。
- **V-DB-121** resource 不可改断言：无不可变触发器；UPDATE resource_id 在 DB 层不被阻止（应用 422）。
- **V-DB-122** 索引目录：部分唯一谓词正确；三索引存在；无 pg_trgm/GIN、无 name/name_key 单列 B-tree。
- **V-DB-123** 恢复重检 DB 层：软删同名后重建，恢复旧对象被部分唯一拒（不覆盖）；Resource 依赖留应用。
- **V-DB-124** Service 删除引用集：DB 无约束；reference_exists 由应用 provider 承担（F011 空集断言）。
- **V-DB-125** 迁移边界：0011 不含 CREATE EXTENSION；downgrade 后可再 upgrade；既有表无结构改动。

## 8. 已有数据影响

- 全表新建，无已有数据迁移；不新增列到既有表、不回填（DB-D141）。
- 不修改既有表结构（resources/clusters/interfaces/ip_pools/ip_addresses 不变）。
- 新增入向引用：`services.resource_id` FK→`resources(id)` RESTRICT；有 services 子行时物理删 Resource 被拒。
- 扩展：不新增/不删除；pg_trgm（0001）与 btree_gist（0008）前后一致。
- 回滚风险：downgrade 丢弃 services 数据不可逆；生产回滚依赖 F001 全库备份。
- 单 head 链：0010→0011。

## 9. 未验证项与风险

- DR-141/142/143/144（已闭合，交 CONTRACT/D01）：D01 §5.10 与 `docs/api/F011.md` 固化。
- DR-146（跨 Feature，非阻塞）：F011 Service 删除引用集为空集，Endpoint 端到端（T23/A10）留 F012。
- DB-D136（NOTE）：resource_id 不可改为应用层 422，无 DB 触发器；DB 只保证存在性。
- name 的 Unicode Cc/Cf（LOW，已知差异）：DB 仅 ASCII backstop，应用负责 Unicode 校验。
- 软删可见性为 ORM 责任（NOTE，交 Tester）。
- 只读签核，全部为计划验证无 PASS。

## 10. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D128–DB-D141）；`services` 首次建表；DR-141 name/name_key + 部分唯一 `(resource_id,name_key) WHERE deleted_at IS NULL`；DR-142 status 默认与 CHECK；DR-143 metadata JSONB object/默认；DR-144 resource 归属不可改（应用 422，无触发器）；索引集合（无 pg_trgm/GIN）；迁移 `0011_services`；D01 v10 §5.10 交核依据；V-DB-112–V-DB-125；已有数据影响。 |