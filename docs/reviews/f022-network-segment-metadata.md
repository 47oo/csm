# Review Report — F022 网段自定义名称 / 子网掩码 / VLAN 标注

> Verdict: **APPROVED WITH FOLLOW-UP**
> Author Role: reviewer（独立审查；协调器在 Merge 后持久化）
> Date: 2026-09-21
> Feature: F022（E02，P1，`depends_on: [F020]` = DONE）
> Branch: `feature/F022-network-segment-metadata`
> Base: `develop` = `dae7fe9b92b991a51a348a00b40037e4957b79fa`
> start_commit: `dae7fe9`（= merge-base）
> 已审查 HEAD: `fbfc9684ab80a63438415ee1c126f2cb6e79ebb4`
> merge commit: `b467e891741f7780c480fbd0f750646cbe4e55ec`（父 `dae7fe9` 与 `fbfc968`）

---

## Review Status

```text
APPROVED WITH FOLLOW-UP
```

无 BLOCKER / HIGH / 必须当前修复的 MEDIUM；仅 LOW / NOTE follow-up。批准绑定候选 HEAD `fbfc968` 与 Base `dae7fe9`。

## Scope Reviewed

- Branch `feature/F022-network-segment-metadata`；Base `develop` = `dae7fe9`；start_commit/merge-base = `dae7fe9`（祖先关系已确认）。
- 提交序列：`6627eaa` → `4f0bfa9`（requirements）→ `b4ddf33`（架构+契约）→ `a66b755`（DB 设计）→ `65e0cce`（实现）→ `38e8792`（checkpoint）→ `fbfc968`（测试）。
- 工作区 clean；差异 42 文件 / +4065 −314。
- 独立重跑：后端 F022 专项 33 passed；api + DB schema guard + migrations 110 passed；前端 spec 99 passed。另复核 Tester 的 91/91 HTTP 集成、32/32 raw DB 证伪、并发 1×201/11×409。

## Product Compliance

AC-01 ~ AC-30 全部满足，无 Scope Creep。字段封闭（响应 9 / POST 请求 6）；三字段可选且往返一致；`name` 同 Cluster 活跃唯一（应用层 409 + DB partial unique 23505 兜底）、跨 Cluster 可重复、区分大小写、软删释放、无长度/trim/空串约束；`subnet_mask` dotted-quad 合法掩码、不强制自洽、仅 IPv4；`vlan` 1–4094、不唯一、DB CHECK 兜底；唯一性恰 `{ux_ip_address_ranges_cluster_name_active}`；既有语义（重叠/软删/删除守卫/无状态/IPv4 规范化/R-IP-001~010/F005 立场/分配不过滤）逐条不变；无 CIDR/IPv6/网关/DHCP/DNS/使用率/description 等；契约无「禁止却实现」分裂。

## Architecture Compliance

符合 C-01~C-08、R-01~R-10：`name` 唯一性由 DB partial unique 最终保证；大小写敏感无 `COLLATE`/`lower()`；`vlan` DB CHECK 兜底；`23505` 经既有 `sqlstate.py` 单一映射（键集合不变）；`deleted_at` 写入路径仍唯一；IPv4/掩码解析唯一实现于 `ipv4.py`；既有 guard 受控演进未删除业务断言；与 ADR-0002/0003/0004/0005 一致。

## Database Review

Migration `0010_f022_ip_range_metadata`：`down_revision="0009_f020_ip_address_ranges"`，单一线性 head；`0001`–`0009` 逐字节未改；3 个可空列、无 `server_default`、无回填；`ux_ip_address_ranges_cluster_name_active (cluster_id, name) WHERE deleted_at IS NULL AND name IS NOT NULL`（无 `COLLATE`/`lower(`）；`ck_ip_address_ranges_vlan_range CHECK (vlan IS NULL OR vlan BETWEEN 1 AND 4094)`；无新表 / 触发器 / CASCADE / COLLATE / extension；**`alembic_version.version_num` 列宽未被改动**（revision id 缩短为 27 字符以适配 `varchar(32)`）；downgrade 严格逆序，upgrade 幂等、可重建、`alembic check` 无漂移；`SQLSTATE_MAP` 键集合不变。

## Backend Review

Router 无新端点/参数；`response_model` 恰 9 字段。Service 分层清晰：create（Cluster 锁 → IPv4/bounds → 掩码/VLAN 校验 → name 预检 → 重叠预检 → 插入）；update（`FOR UPDATE`，`model_fields_set` 判定；`start/end` null→400；三可选字段 null→清空；空 body→400；无部分写入）。掩码 `parse_subnet_mask` 复用 `parse_ipv4`；`vlan` `StrictInt` + DB CHECK；name 应用层预检 + partial unique 最终权威；既有不变式与 F021 分配路径未改；错误语义区分正确。

## Frontend Review

严格使用契约（Read 9 字段、Create 可选、Update 可空清空）；列表 / 详情 null → `—`；登记/编辑录入三字段快照提交；三态互异；按 `error.code`（结合 `details[].code`）分支含 `CONFLICT + DUPLICATE`，不解析 `message`；无客户端业务校验；无新增 CRUD / 筛选排序 / 不必要依赖。

## Test Review

AC 真实覆盖：真实 uvicorn + 真实 PostgreSQL HTTP 集成 91/91、真实前端 client 5/5、直连 DB 证伪 32/32、并发 1×201/11×409/0×5xx；新增 `tests/test_f022_metadata_extra.py` 专门证伪「绕过应用层预检 → partial unique 23505→409」；对抗注入（DROP index / CHECK）证明关键 guard 可失败并逐字节还原；既有 guard 只增不弱（仅移除已确认合法的 `name`/`vlan` 禁令牌）；执行顺序无关。独立重跑 33 + 110 + 99 全通过。

## Findings

### REV-1

```text
Severity: LOW
Layer: Test asset / Security hygiene
Location: docs/test-reports/assets/f022/integration_http.py:25 (PASSWORD = "tester-password-123")
Problem: 提交了硬编码测试账号口令（一次性测试库的一次性 admin，非生产密钥），违反「不得提交凭据」的卫生要求。
Impact: 无生产安全影响；若该模式被复制到携带真实环境信息的资产则有泄漏风险。
Expected: 改为从环境变量 / argv 读取，不落盘。
Suggested Owner: Tester
```

### REV-2

```text
Severity: LOW
Layer: Tests
Location: tests/test_f022_metadata_extra.py、tests/test_ip_address_range_metadata_guards.py（文件末尾缺换行）
Problem: 两个新增测试文件末尾缺换行符。
Impact: 无功能影响；轻微风格不一致。
Expected: 补末尾换行。
Suggested Owner: Tester
```

### REV-3

```text
Severity: NOTE
Layer: Product / Database（边界观察，非缺陷）
Location: ux_ip_address_ranges_cluster_name_active（谓词 deleted_at IS NULL AND name IS NOT NULL）
Problem: 空串 name = "" 满足 name IS NOT NULL，参与同 Cluster 活跃唯一性（两个活跃 "" 会 409）。
Impact: 与契约「字面等值唯一」自洽，不构成缺陷；前端把空输入映射为 null（不发送 ""），仅直连 API 调用方受影响。
Expected: 无需当前修复；建议 Product 知悉该边界。
Suggested Owner: Product Manager（知悉，非阻塞）
```

## Existing Defects

Tester 报告 Defects: None（观察项 O-01 / O-02）。O-01（23505 兜底路径无实现方测试）复核成立，Tester 已补回归测试通过，非缺陷；O-02（前端集成探针一次性抖动）判定非后端竞态，非缺陷。未发现被遗漏的 Defect。

## Non-blocking Follow-ups

1. FU-1：按 REV-1 移除 `docs/test-reports/assets/f022/integration_http.py` 的硬编码测试口令，改为环境变量 / 参数读取。
2. FU-2：按 REV-2 为两个新增测试文件补齐末尾换行。
3. FU-3（可选）：契约 §7.3 补一句「空串按字面参与唯一性」。

## Unreviewed Areas

- F021 分配语义自身的内部细节（范围外）；本 Feature 仅验证「分配不按掩码 / VLAN 过滤」与 F021 自 base 未改。
- 其它 Feature 未被触及的行为，依赖全量测试通过间接覆盖。
- 未对生产库执行任何操作；未在生产环境运行 Migration。

---

**Verdict**：`APPROVED WITH FOLLOW-UP`（批准绑定 HEAD `fbfc968` 与 Base `dae7fe9`；无 BLOCKER/HIGH；仅 LOW/NOTE follow-up，不阻塞 Merge）。