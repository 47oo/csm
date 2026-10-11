# F012 Service Endpoint 监听端点 — DATABASE 设计

- **签核**：Database；设计版本 v1（2026-10-09）
- **上游依据**：requirements-v3.md revision 3（§4、§4.1、§13/§13.3、§14、§15、§16、§17、§18、§19、§21、§22、§23、§25、§26、§27、§28、§31 T22/T23/T24/T25/T26/T37/T40/T41、§32/§33、§35.2 Q06/Q10-A、§35.3 D01/D02）；`docs/features/F012/product.md`（A1–A21、I-1–I-7）；`docs/features/F012/architecture.md`（DR-155–DR-170）；`docs/api/F012.md` v1；`docs/database/f001-baseline.md` v1（DB-D2/DB-D4/DB-D6/DB-D7）、`f004-resource.md` v1（DB-D40）、`f007-interface.md` v1（DB-D74）、`f010-ip-address.md` v1（DB-D111–D127）、`f011-service.md` v1（DB-D128–D141）；`docs/architecture/d01-conventions.md` v10（目标 v11 §5.11）；`backend/alembic/versions/0010_ip_addresses.py`、`0011_services.py`
- **覆盖**：`service_endpoints` 表、字段/类型/必填/默认、约束/索引/FK 命名、监听唯一部分唯一（DR-159）、protocol/port 取值域（DR-160）、归属 backstop 触发（DR-158）、双 provider 引用检查落点（DR-161）、索引集合、迁移 `0012_service_endpoints`、真 PG 验证项（V-DB-126–V-DB-138）、D01 v11 §5.11 交核依据、已有数据影响。不覆盖 `docs/api/F012.md` 定稿、D01 v11 签核、F010/F011 挂钩实现、F013 展示聚合、TEST 执行与业务实现。

## 1. 设计决策汇总（DB-D142–DB-D156）

| ID | 决定 | 状态 |
| --- | --- | --- |
| DB-D142 | `service_endpoints` 独立可寻址对象表（非 Service / IPAddress 的 1:1 明细）：`id` UUID PK `pk_service_endpoints` 默认 `gen_random_uuid()`；软删/恢复/Activity/乐观锁 | CONFIRMED（§16/§21/DR-155）+DESIGN |
| DB-D143 | `service_id` UUID NOT NULL FK `fk_service_endpoints_service_id_services`→`services(id)` ON DELETE RESTRICT + `ix_service_endpoints_service_id`；引用须存在、未软删（应用 422 field="service"）；创建必填、创建后不可改（应用 422，DR-157）；**不建**不可变触发器 | CONFIRMED（§16/§21/DR-155/157）+DESIGN |
| DB-D144 | `ip_address_id` UUID NOT NULL FK `fk_service_endpoints_ip_address_id_ip_addresses`→`ip_addresses(id)` ON DELETE RESTRICT + `ix_service_endpoints_ip_address_id`；引用须存在、未软删且已绑定 Interface 且该 Interface 属 Service 所属 Resource（应用 422 field="ip_address" + 触发 backstop）；创建后不可改（应用 422，DR-157） | CONFIRMED（§14/§16/§21/DR-155/158）+DESIGN |
| DB-D145 | `protocol` varchar(8) NOT NULL + `ck_service_endpoints_protocol`：`protocol IN ('TCP','UDP')`；仅接受大写规范值（应用），存储大写 | CONFIRMED（§16/DR-160）+DESIGN |
| DB-D146 | `port` integer NOT NULL + `ck_service_endpoints_port`：`port BETWEEN 1 AND 65535` | CONFIRMED（§16/DR-160）+DESIGN |
| DB-D147 | `description` text NULL（无长度上限，同前序 Feature）；**不落** `metadata`/`name`/`status`/`listen_address`（DR-156/I-1/I-7） | DESIGN（D01 §5.11 拟）+CONFIRMED（§16 未列举 metadata） |
| DB-D148 | `version` integer NOT NULL DEFAULT 1 CHECK ≥1；`created_at`/`updated_at` timestamptz NOT NULL `now()`（`updated_at` 应用维护，无触发器）；`deleted_at` timestamptz NULL 软删 | DESIGN |
| DB-D149 | 同 IP 未删监听唯一：部分唯一 `uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id,protocol,port) WHERE deleted_at IS NULL`（DR-159 落地）；软删释放、恢复重检被拒 | CONFIRMED（§16/§27/DR-159）+DESIGN |
| DB-D150 | 归属 backstop：`fn/trg_service_endpoints_attribution`（BEFORE INSERT/UPDATE，**不检查软删、不加行锁**）：IP 须已绑定 Interface 且 `interfaces.resource_id == services.resource_id`；缺失行交 FK | CONFIRMED（§14/§16/§27/DR-158）+DESIGN |
| DB-D151 | **不建** `service_id`/`ip_address_id` 不可变触发器：不可改为 CONTRACT 层规则，应用 PATCH 出现不可变字段→422。沿用 F008/F009/F010/F011 先例 | DESIGN（DR-157 裁定） |
| DB-D152 | 索引集合：`uq_service_endpoints_ip_protocol_port`（部分唯一）+ `ix_service_endpoints_service_id`、`ix_service_endpoints_ip_address_id`、`ix_service_endpoints_deleted_at`；**不建** 独立 `protocol` 索引、**不建** pg_trgm/GIN、不建额外复合索引（F013 交叉引用：`service_endpoints` 不在 §17 搜索目标，F013 未建 service_endpoints 索引；见 docs/database/f013-search-index.md §7-E2） | DESIGN |
| DB-D153 | 迁移 `0012_service_endpoints`，`down_revision=0011_services`；**不重复启用** pg_trgm/btree_gist（0001/0008 已启用）；单一 head、全表新建无回填、对称可逆 | DESIGN（DR-165） |
| DB-D154 | F012 注册两个真实 provider：IP 侧（F010 `register_ip_address_reference_checker`）与 Service 侧（F011 `register_service_reference_checker`），返回未删 Endpoint 引用列表；DB 仅 FK RESTRICT 保证物理删除完整性，软删引用保护由应用 provider 承担 | CONFIRMED（§13.3/§16/§21/DR-161）+DESIGN |
| DB-D155 | D01 v10→v11 §5.11 的 DB 依据：service/ip_address 建必填活引用、创建后不可改；ip_address 须已绑定且属 Service.Resource；protocol∈{TCP,UDP}（大写）；port 1–65535；description 可空无上限；同 IPAddress 未删 (ip_address_id,protocol,port) 部分唯一；不落 metadata/name/status/listen_address | PROPOSED→CONTRACT/D01（I-3）+DESIGN |
| DB-D156 | 100% 新建对象，无已有数据迁移；downgrade 丢弃 `service_endpoints` 数据不可逆，生产回滚用 F001 全库备份 | DESIGN |

## 2. `service_endpoints` 表

| 列 | 类型 | 空 | 默认 | 约束 |
| --- | --- | --- | --- | --- |
| id | UUID | NOT NULL | gen_random_uuid() | PK `pk_service_endpoints` |
| service_id | UUID | NOT NULL | — | FK `fk_service_endpoints_service_id_services`→`services(id)` ON DELETE RESTRICT；`ix_service_endpoints_service_id` |
| ip_address_id | UUID | NOT NULL | — | FK `fk_service_endpoints_ip_address_id_ip_addresses`→`ip_addresses(id)` ON DELETE RESTRICT；`ix_service_endpoints_ip_address_id`；归属 backstop 触发 |
| protocol | varchar(8) | NOT NULL | — | `ck_service_endpoints_protocol`：IN ('TCP','UDP') |
| port | integer | NOT NULL | — | `ck_service_endpoints_port`：BETWEEN 1 AND 65535 |
| description | text | NULL | — | — |
| version | integer | NOT NULL | 1 | `ck_service_endpoints_version`：≥1 |
| created_at/updated_at | timestamptz | NOT NULL | now() | UTC；`updated_at` 应用维护 |
| deleted_at | timestamptz | NULL | — | 软删 |

CHECK 形态（`ck_` 由 naming convention 展开为 `ck_service_endpoints_<name>`）：

| 约束名 | 表达式 |
| --- | --- |
| ck_service_endpoints_protocol | `protocol IN ('TCP','UDP')` |
| ck_service_endpoints_port | `port BETWEEN 1 AND 65535` |
| ck_service_endpoints_version | `version >= 1` |

约束/索引：

- `uq_service_endpoints_ip_protocol_port` UNIQUE(ip_address_id, protocol, port) WHERE deleted_at IS NULL（部分唯一）。
- `ix_service_endpoints_service_id`、`ix_service_endpoints_ip_address_id`、`ix_service_endpoints_deleted_at`。
- **无**不可变触发器（DB-D151）；**无**独立 protocol 索引；**无** pg_trgm/GIN。

DDL（关键片段，供迁移使用）：

```sql
CREATE TABLE service_endpoints (
    id            uuid        NOT NULL DEFAULT gen_random_uuid(),
    service_id    uuid        NOT NULL,
    ip_address_id uuid        NOT NULL,
    protocol      varchar(8)  NOT NULL,
    port          integer     NOT NULL,
    description   text,
    version       integer     NOT NULL DEFAULT 1,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    CONSTRAINT pk_service_endpoints PRIMARY KEY (id),
    CONSTRAINT fk_service_endpoints_service_id_services
        FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT,
    CONSTRAINT fk_service_endpoints_ip_address_id_ip_addresses
        FOREIGN KEY (ip_address_id) REFERENCES ip_addresses(id) ON DELETE RESTRICT,
    CONSTRAINT ck_service_endpoints_protocol CHECK (protocol IN ('TCP','UDP')),
    CONSTRAINT ck_service_endpoints_port CHECK (port BETWEEN 1 AND 65535),
    CONSTRAINT ck_service_endpoints_version CHECK (version >= 1)
);

CREATE UNIQUE INDEX uq_service_endpoints_ip_protocol_port
    ON service_endpoints (ip_address_id, protocol, port)
    WHERE deleted_at IS NULL;

CREATE INDEX ix_service_endpoints_service_id    ON service_endpoints (service_id);
CREATE INDEX ix_service_endpoints_ip_address_id ON service_endpoints (ip_address_id);
CREATE INDEX ix_service_endpoints_deleted_at    ON service_endpoints (deleted_at);
```

不落字段（§16/DR-156/DR-147）：`metadata`、`name`、`status`、`listen_address` 文本、Unix Socket、端口范围/列表、VIP 标识、URL/路径/TLS、实时探测/健康状态、部署/同步标记。

## 3. 交核裁定

### 3.1 DR-159 同 IP 未删监听唯一（DB-D149）
采纳部分唯一 `uq_service_endpoints_ip_protocol_port UNIQUE(ip_address_id, protocol, port) WHERE deleted_at IS NULL`。唯一作用域 = 同一 IPAddress；不同 IP 对象（含不同 Cluster 同值地址）各自独立；软删释放索引项；恢复重入被部分唯一直接拒绝 → 应用 409 `unique_conflict{field:"port", ip_address_id, protocol, port}`，不覆盖。并发创建/改 protocol·port 由索引原子仲裁（仅一成功）。与 F010/F011 部分唯一同构。

### 3.2 DR-160 protocol/port 取值域（DB-D145/DB-D146）
`protocol varchar(8) NOT NULL` + `ck_service_endpoints_protocol`（IN ('TCP','UDP')）；「仅接受大写规范值、存储大写」为应用归一化责任（小写 `"tcp"` 应用即 422）；枚举扩展走迁移。`port integer NOT NULL` + `ck_service_endpoints_port`（1..65535，含端点）；越界/非整数/null 应用 422；边界 1、65535 接受。

### 3.3 DR-158 归属 backstop（DB-D150）—— 采纳新增触发
结论：采纳。§27 要求 Endpoint 归属由数据库兜底；结构性部分（IP 已绑定 Interface + 同 Resource）可由 DB 在写入时点可靠校验，与 F010 `trg_ip_addresses_interface_cluster` 同类，建 BEFORE INSERT/UPDATE 触发；应用仍为主校验（422 field="ip_address"）并负责软删存活与恢复依赖顺序。

触发检查（只在 Endpoint 写入时点）：① `ip_address_id` 对应 IP 的 `interface_id` 非空；② 该 `interfaces.resource_id == services.resource_id`（同 Resource ⇒ 同 Cluster）。**不检查软删**（留应用）；**不加行锁**（`services.resource_id`/`interfaces.resource_id`/`resources.cluster_id` 均不可变，链路值稳定；IP 转移窗口由 F010 在提交前调用 `check_ip_address_references`（F012 provider）拦截）。

```sql
CREATE OR REPLACE FUNCTION fn_service_endpoints_attribution()
RETURNS trigger AS $$
DECLARE
    ip_interface  uuid;
    res_service   uuid;
    res_interface uuid;
BEGIN
    SELECT ia.interface_id INTO ip_interface
      FROM ip_addresses ia WHERE ia.id = NEW.ip_address_id;
    IF NOT FOUND THEN RETURN NEW; END IF;      -- 交 FK

    SELECT s.resource_id INTO res_service
      FROM services s WHERE s.id = NEW.service_id;
    IF NOT FOUND THEN RETURN NEW; END IF;      -- 交 FK

    IF ip_interface IS NULL THEN
        RAISE EXCEPTION
            'service_endpoints.ip_address_id must be bound to an interface'
            USING ERRCODE = 'restrict_violation';
    END IF;

    SELECT i.resource_id INTO res_interface
      FROM interfaces i WHERE i.id = ip_interface;
    IF NOT FOUND THEN RETURN NEW; END IF;

    IF res_interface IS DISTINCT FROM res_service THEN
        RAISE EXCEPTION
            'endpoint ip interface must belong to the service resource'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_service_endpoints_attribution
BEFORE INSERT OR UPDATE ON service_endpoints
FOR EACH ROW EXECUTE FUNCTION fn_service_endpoints_attribution();
```

- 触发对任意 UPDATE 生效（含软删/恢复）。不检查软删故 `deleted_at` 置位不误拒；恢复时重跑归属校验作 DB 兜底。
- **未由 DB 承担**：service/ip_address 是否软删；IP 解绑/转移后残留 Endpoint 的一致化；恢复依赖顺序（409 `dependency_deleted`）。触发只保证 Endpoint 行写入时结构性归属成立。

### 3.4 DR-155/DR-157 FK 语义与不可变（DB-D143/DB-D144/DB-D151）
`service_id`/`ip_address_id` 均 NOT NULL FK ON DELETE RESTRICT；物理删被未删 Endpoint 引用的 Service/IP 被 RESTRICT 拒。创建后不可改：应用 PATCH 出现 `service`/`service_id`/`ip_address`/`ip_address_id`→422；**不建 DB 不可变触发器**（后果由 FK + 引用检查器兜底）。软删引用保护为应用 provider 责任（DB-D154）。

## 4. 迁移 `0012_service_endpoints`

- `revision = "0012_service_endpoints"`、`down_revision = "0011_services"`；单一 head。
- **不重复启用扩展**：pg_trgm（0001）、btree_gist（0008）已启用；本迁移不含 `CREATE EXTENSION`。
- 无回填（全表新建）。

upgrade：1. create_table（列 + PK + 2 FK + 3 CHECK）；2. 部分唯一索引；3. 三个普通索引；4. `op.execute` 建函数 + 触发。
downgrade（对称逆序）：drop 触发/函数 → drop 三普通索引 → drop 部分唯一索引 → drop_table；**不 DROP btree_gist / pg_trgm**。
校验：真库 `up → down → up`；`alembic heads` 唯一=0012；对象齐全；`pg_extension` 前后无新增；无回填。

## 5. 数据完整性对应表（Database 视角，精简）

| 规则依据及版本 | 作用域/写入入口 | 数据库保证 | 业务层保证 | 并发/生命周期边界 | 验证（计划） |
| --- | --- | --- | --- | --- | --- |
| §16/§27/DR-159 同 IP 未删 (protocol,port) 唯一 | POST/PATCH/restore | 部分唯一 `(ip_address_id,protocol,port) WHERE deleted_at IS NULL` | 409 `unique_conflict{field:"port"}`；软删释放；恢复重检 | 索引仲裁；跨 IP 独立 | V-DB-130/136/137 |
| §16/DR-160 protocol/port 取值域 | POST/PATCH | `ck_service_endpoints_protocol`、`ck_service_endpoints_port` | 422 field="protocol"/"port"；仅大写 | 枚举扩展走迁移 | V-DB-128/129 |
| §14/§16/§27/DR-158 归属 | POST/restore | `trg_service_endpoints_attribution`（不检查软删、不加锁）+ FK RESTRICT | 422 field="ip_address"；软删存活/依赖顺序 | IP 转移窗口由 F010 provider 拦 | V-DB-132 |
| §16/§21/DR-155 service/ip 引用与不可改 | POST/PATCH | FK NOT NULL RESTRICT；无不可变触发器 | 缺/不存在/软删→422；PATCH 不可变字段→422 | 物理删 RESTRICT | V-DB-133 |
| §13.3/§16/§21/DR-161 Endpoint 引用 IP | IP 解绑/转移/释放 | 无（FK RESTRICT 仅物理） | F010 provider→409 reference_exists；不级联 | F012 注册真实 provider | 端到端 T22 |
| §16/§21/DR-161 Endpoint 引用 Service | DELETE Service | 无（FK RESTRICT 仅物理） | F011 provider→409 reference_exists；不级联 | F012 注册真实 provider | 端到端 T23 |
| §21/§27 软删/恢复 | DELETE/RESTORE | deleted_at + 部分唯一 + 归属触发重跑 | 恢复重检 service/IP 存活、归属、监听唯一；失败不覆盖 | 索引仲裁；不级联 | V-DB-130/136 |
| §23 乐观锁 | PATCH/DELETE/restore | version CHECK + 条件 UPDATE | rowcount=0→409 VERSION_CONFLICT | 真并发 | V-DB-135 |
| §22 Audit | 四 action | 复用 audit_logs | 同事务；object_type="service_endpoint" | — | F012 集成 |
| §26/§27 真实 PG | 迁移/约束 | 0012 up/down/up、单 head、无回填、扩展不重复启用 | — | — | V-DB-126/138 |

## 6. D01 v10→v11 §5.11 交核依据（DB-D155）
- service/ip_address：创建必填 UUID；NOT NULL FK RESTRICT；引用须存在未软删（应用 422）；ip_address 须已绑定 Interface 且 `interfaces.resource_id == services.resource_id`（应用 422 + 触发 backstop）；创建后不可改（应用 422，DB 无不可变触发器）。
- protocol：varchar(8) NOT NULL；∈{TCP,UDP}；仅大写；显式 null/非法→422。
- port：integer NOT NULL；1–65535；越界/非整数/null→422。
- description：text NULL，无上限；显式 null 清空、省略保持。
- 唯一：同 IPAddress 未删 `(ip_address_id,protocol,port)` 部分唯一 WHERE deleted_at IS NULL；软删释放、恢复重检不覆盖；不同 IP 对象独立。
- 不落：metadata/name/status/listen_address；§5 名称归一化表不适用。

## 7. Backend 可依赖保证与测试项

**保证（DB 层）**：id 唯一；service_id/ip_address_id 非空指向存在 Service/IPAddress（FK），物理删被 RESTRICT 拒；protocol 恒 ∈{TCP,UDP}；port 恒 1–65535；description 可空无上限；version ≥1 默认 1；Endpoint 行写入时 IP 必已绑定 Interface 且接口 Resource == Service Resource（触发）；同 IP 未删 (ip_address_id,protocol,port) 唯一、跨 IP 允许、软删释放、恢复冲突拒；索引集合存在且无 pg_trgm/GIN、无独立 protocol 索引；0012 有真实 downgrade、单 head、无回填、扩展不重复启用。

**不保证（应用/Contract 层）**：service/ip_address 软删时点校验（应用 422）；不可变（应用 422）；Service/IP/Interface 软删引用保护（F012 provider）；IP 转移后残留 Endpoint 一致化（F010 provider 拦截）；恢复依赖顺序（409 dependency_deleted）；listen_address/Unix Socket/共享 VIP 语义。

**计划测试项（真实 PG，V-DB-126–V-DB-138，无 PASS）**：
- **V-DB-126** 迁移 up/down/up；down_revision=0011_services；单 head=0012；对象齐全（3 CHECK/1 PK/2 FK/1 部分唯一/3 索引/1 触发+函数）；无回填；扩展无新增。
- **V-DB-127** 默认/NOT NULL。
- **V-DB-128** `ck_protocol`：TCP/UDP 接受；tcp/udp/SCTP/空串/NULL 拒。
- **V-DB-129** `ck_port`：1/65535 接受；0/65536/-1/NULL 拒。
- **V-DB-130** 部分唯一：同 IP 重复拒；同 IP 不同 protocol/port 接受；不同 IP 相同 (protocol,port) 接受；软删重建；恢复冲突拒；并发双会话仅一成功。
- **V-DB-131** FK RESTRICT：物理删有未删 Endpoint 的 Service/IP 拒；软删 Service/IP 行仍在。
- **V-DB-132** 归属触发：未绑定/跨 Resource→`restrict_violation`；匹配成功；软删/普通 UPDATE 不误拒；恢复重跑。
- **V-DB-133** service/ip 不可改断言：无触发器；DB 层 UPDATE 不被阻止（应用 422）。
- **V-DB-134** 索引目录：部分唯一谓词正确；三索引存在；无 pg_trgm/GIN、无独立 protocol 索引。
- **V-DB-135** version 默认 1、<1 拒；乐观锁双会话仅一成功。
- **V-DB-136** 恢复重检 DB 层：软删同名 (protocol,port) 后重建，恢复旧对象被部分唯一拒；归属触发恢复时重跑。
- **V-DB-137** 引用集：DB 无 soft-delete 约束；reference_exists 由 F012 两 provider 承担（查询形状与返回）。
- **V-DB-138** 迁移边界：0012 不含 CREATE EXTENSION；downgrade 后再 upgrade；既有表无结构改动。

## 8. 已有数据影响
- 全表新建，无已有数据迁移；不新增列到既有表、不回填。
- 不修改既有表结构（services/ip_addresses/interfaces/resources/networks 不变；不新增/修改 F010/F011 触发器）。
- 新增入向引用（RESTRICT）：service_id→services、ip_address_id→ip_addresses；有未删 Endpoint 时物理删 Service/IP 被拒。
- 扩展：不新增/不删除；pg_trgm/btree_gist 前后一致。
- 回滚风险：downgrade 丢弃 service_endpoints 数据不可逆；生产回滚用 F001 全库备份。
- 单 head 链：0011→0012。

## 9. 未验证项与风险
- **DR-158 触发 backstop（NOTE）**：只在 Endpoint 写入时点生效，不拦截 `ip_addresses.interface_id` 被解绑/转移至异 Resource；该窗口由 F010 在 IP 事务内调用 `check_ip_address_references`（F012 provider）闭合。实现须真正注册 provider 且被 F010 调用，否则 T22 无法闭合（交 Backend/协调器）。
- **幽灵行（NOTE）**：归属触发对任意 UPDATE 生效；若绕过 provider 造成 IP 解绑而 Endpoint 未删，其后软删该 Endpoint 会被触发拒绝，属预期 backstop 行为。
- D01 v11 §5.11（非阻塞）：待 CONTRACT/D01 建立并签核；本设计提供 DB 依据。
- I-4 object_type 统一（非阻塞）：canonical=`"service_endpoint"`；F010 errata-03 属 CONTRACT/Backend/Tester。
- I-2 字段可变性（DR-157 已裁定）：service/ip_address 不可改（应用 422，无 DB 触发器）；protocol/port 可 PATCH 并重检监听唯一。
- 软删可见性（NOTE，交 Tester/Backend）：默认过滤为 ORM/Service 责任。
- 独立 `protocol` 索引未建（NOTE）：若列表 protocol 单独过滤 EXPLAIN 需要再评估。
- 只读签核，全部为计划验证无 PASS。

## 10. 设计版本历史

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1 | 2026-10-09 | 初次签核（DB-D142–DB-D156）；`service_endpoints` 首次建表；DR-159 部分唯一 `(ip_address_id,protocol,port) WHERE deleted_at IS NULL`；DR-160 `ck_protocol`/`ck_port`；DR-158 归属 backstop 触发 `trg_service_endpoints_attribution`（不检查软删、不加锁）；DR-155/157 FK RESTRICT、不可改为应用 422 无触发器；DR-161 双 provider 落点；索引集合；迁移 `0012_service_endpoints`；D01 v11 §5.11 DB 依据；V-DB-126–V-DB-138；已有数据影响。 |