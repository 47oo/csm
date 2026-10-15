# F018 全局搜索字段组合展示 — PRODUCT 阶段报告

## 1. Feature 元信息

- **Feature**：F018 全局搜索字段组合展示（FEATURE，P1，M9 搜索字段组合）
- **阶段**：PRODUCT；**结论**：`READY FOR ARCHITECT`（2026-10-15）
- **依赖**：F013（全局搜索与 Dashboard，已 DONE；`docs/api/F013.md` v1 READY）
- **layers / api_required**（已批准计划）：`database=false`、`backend=true`、`frontend=true`、`api_required=true`
- **依据**：
  - `docs/product/requirements-v3.md` revision 5：§17.1（搜索结果字段组合）、T50–T53、§17、§18、§23、§28、§33、§35.1。
  - `docs/project/project-plan.yaml` plan_revision 6：F018 条目（用户 2026-10-15 批准并授权自动实施）。
  - 用户已确认 BQ1–BQ5（见 §6）。

## 2. 范围

### 2.1 范围内（CONFIRMED）

1. 仅作用于全局搜索结果（§17）：`GET /api/v1/search` 的 `resource` 行扩展为携带固定超集的关联展示字段。
2. 可组合字段集合：`hostname`、`resource_type`、`role`、`status`、`cluster`、Interface `name`、Interface `interface_type`、IP `address`、Network `name`。「网络类型」按 **Network 名称**解释；需要网卡类型时单独选择 Interface `interface_type`。
3. 固定超集返回：`resource` 结果行返回上述字段的固定超集（含关联 Interface / IPAddress / Network），使前端任意字段组合无需再次请求。
4. 每 IP 一行展开：单台 Resource 的关联按「每个已绑定 IP 一行」展开，行内含 Interface name / interface_type、IP address、Network name。
5. 关联行排序（确定性全序）：`interface.name ASC → IP 地址数值 ASC → id ASC`。
6. 上限与截断提示：每台 Resource 的关联行展示上限为 10；服务端同时返回截断前总数；超出时界面显式提示「还有 N 条」，不静默截断。
7. 前端字段选择器与本地偏好：全局搜索结果增加字段选择器与多值展开；偏好仅存浏览器本地（localStorage）；未选择时保持现有展示，无回归。
8. 软删与权限继承：关联字段严格继承结果行的软删口径与权限。
9. 只读：仍为只读操作，无写入口、不产生 Audit（§22）。

### 2.2 明确排除（CONFIRMED，本期不做）

- 不扩展到各域列表页（仅全局搜索结果）。
- 不做导出；不做命名 / 共享视图。
- 不做账号级服务端偏好（偏好仅浏览器本地）。
- 不引入新实体、关系、状态、权限或错误码；字段语义沿用 §7、§10、§11、§13 与 F007 / F008 / F010 各域口径。
- 不改匹配语义 / 结果集 / 去重 / 顶层排序 / 分页与 `total`。
- 无 Schema / 索引 / 迁移。
- 本报告不裁定接口参数名、响应字段命名与序列化形态（由 Architect / Contract 定稿）。

## 3. 用户可观察验收标准

| # | 验收标准 | 映射 |
| --- | --- | --- |
| A1 | `GET /api/v1/search` 的每个 `resource` 结果行返回固定超集，包含关联 Interface（name、interface_type）、IPAddress（address）、Network（name），以及 hostname、resource_type、role、status、cluster | T50 |
| A2 | resource 行关联顺序确定为 `interface.name ASC → IP 地址数值 ASC → id ASC`（全序，重复查询稳定） | T50 |
| A3 | 每台 Resource 关联行最多 10 行，并同时返回截断前的关联总数 | T50 |
| A4 | 多网卡 / 多 IP 按「每个已绑定 IP 一行」正确展开；同一 IP 不重复、不多造行 | T51 |
| A5 | 无任何可展示关联时关联集合为空（不伪造占位行） | T51 |
| A6 | 关联超过上限时界面显式提示「还有 N 条」（N = 截断前总数 − 10），不静默截断 | T51 |
| A7 | 关联继承软删口径：`exclude` 不展示已软删关联；`include/only` 无 `VIEW_DELETED` 仍 403 `FORBIDDEN{reason:"permission"}`；无 `VIEW_DELETED` 用户不得见到任何已删关联 | T52 |
| A8 | 未绑定 Interface 的 IP 不出现在任何 Resource 的关联行中 | T52 |
| A9 | 改变展示字段组合不改变结果集、去重、顶层排序、分页与 `total` | T53 |
| A10 | 搜索仍只读：无写入口、无副作用、不产生 Audit；重复调用幂等 | T53 |
| A11 | 前端提供字段选择器（九个字段），偏好写入 localStorage 并在刷新后沿用 | §17.1 / BQ4 |
| A12 | 未选择字段组合时保持现有展示（F013 行为），无回归 | §17.1 |

## 4. 边界与非功能要求

1. 只读无审计：不新增写入口，不写 Audit，无副作用。
2. 排序确定性：`interface.name ASC → IP 地址数值 ASC → id ASC` 全序；IP 按地址数值而非字符串排序。
3. 上限与提示一致：上限恒为 10；服务端返回截断前总数；总数 ≥ 展示行数；超限时 N = 总数 − 10。
4. 固定超集、不按需裁剪：无论选择哪些字段，`resource` 行返回同一超集。
5. localStorage 安全回退：存储不可用或写入失败时字段选择器不抛错、不阻断搜索；退化为会话内默认展示，不回退到服务端持久化。
6. 不破坏既有契约：匹配语义、结果集、去重、顶层排序、分页与 `total` 保持 F013 v1 行为；错误码不新增。
7. 统计口径不可改写：`interface_type`、IP 地址、Network 名称沿用各域权威定义。
8. 性能边界（交设计落实）：关联按分页结果批量取数（不逐行 N+1）；正确性不依赖新增索引（`database=false`）。

## 5. 对既有需求与契约的影响要点

1. `docs/api/F013.md` 需修订为 v2：`resource` 嵌套对象扩展关联数组与截断前总数；既有字段语义不变。
2. 不影响 F013 v1 已定稿裁定：去重键 `(object_type, id)`、typed 行方案、顶层排序、分页与 `total` 不变；仅 `resource` 行展示字段扩充。
3. 不改软删 / 权限口径：沿用 F013 v1 §1.3 / §4 与 §21 / §23；`deleted` 行为与 403 语义不变。
4. 无 Schema 影响：不新增表 / 列 / 约束 / 索引 / 迁移；关联查询命中既有索引。
5. 前端影响限定在全局搜索结果视图。
6. 需求正文已就位：§17.1 与 T50–T53 已在 requirements revision 5 记录。

## 6. Blocking Questions

None。

已关闭的用户决策（CONFIRMED）：

- BQ1：仅作用于全局搜索结果。
- BQ2：字段集合如上；「网络类型」= Network 名称。
- BQ3：多 IP 每行展开、每 Resource 上限 10、超出显示「还有 N 条」并返回截断前总数。
- BQ4：偏好仅浏览器本地，无导出 / 命名视图。
- BQ5：关联严格继承软删与权限口径。

## 7. 结论

范围与验收标准已按 §17.1、T50–T53 与已确认 BQ1–BQ5 明确，无 Blocking Questions。

**READY FOR ARCHITECT**。下一步：扩展 `resource` 行 schema、确定性排序与批量取数边界；将 `docs/api/F013.md` 修订为 v2；前端承接字段选择器与 localStorage 回退。`database=false`，不产生迁移。