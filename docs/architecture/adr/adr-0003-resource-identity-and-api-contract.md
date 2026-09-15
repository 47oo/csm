# ADR-0003: 资源标识、URL 寻址与 API / 错误响应契约

## Status

`ACCEPTED`（2026-09-15 用户批准）

**决策记录**：用户于 2026-09-15 批准 DEC-011（方案 C：`id` 为规范路径 + Cluster `by-name` 只读别名）与 DEC-014（自定义 Problem 风格错误信封）。

同时裁定：**保留 R-CLUSTER-005**，不因 URL 改用 `id` 而调整该产品规则（见「与 R-CLUSTER-005 的关系」）。

## Context

需要统一的资源标识与 URL 寻址方案（DEC-011），因为全部资源 CRUD 与查询都依赖它。

产品侧 R-CLUSTER-005 明确：Cluster 名称用于 URL 路径寻址，因此名称不得包含 `/`。

同时需要一个统一的错误响应规范（DEC-014），以支撑 §21 数据一致性与 R-IMPORT-003 的「哪一行、哪个字段、什么原因」逐行报错。

产品侧还要求查询能区分 Resource Not Found 与 Empty Relationship（R-QUERY-004）。

## Decision

### 1. 标识

所有资源表使用**不可变代理主键** `id`（BIGINT identity）。外键一律引用 `id`，**任何场景都不得以名称作为外键**。

### 2. 寻址

- **规范路径使用 `id`**：`/api/clusters/{cluster_id}`；写操作（POST / PATCH / DELETE）一律走 id 路径。
- 额外提供**只读的名称寻址别名**，尊重 R-CLUSTER-005 的产品意图：
  - `GET /api/clusters/by-name/{cluster_name}`
  - `GET /api/clusters/by-name/{cluster_name}/bare-metals`
- `{cluster_name}` 按**大小写敏感**匹配（与 R-CLUSTER-002 一致）；已逻辑删除的 Cluster 不参与名称解析（与 R-DELETE-006 一致）。
- `by-name` 前缀消除「名称看起来像数字」的解析歧义。

### 3. 通用 API 规范

- REST + JSON + UTF-8，路径前缀 `/api`，集合用复数名词，字段用 `snake_case`；不引入 API versioning。
- 列表响应：`{ "items": [...], "total": <int>, "page": <int>, "page_size": <int> }`；查询参数 `page`（从 1 起，默认 1）与 `page_size`（默认 50，上限由后端界定）。
- 时间字段为 RFC 3339 字符串；`id` 为整数；`status` 为字符串枚举；`deleted_at` 不对外暴露。
- 可选字段在空值时**返回 `null`**（而非省略），以便前端使用固定 schema。

### 4. 错误信封

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求校验失败",
    "details": [
      {
        "row": 12,
        "field": "hostname",
        "code": "DUPLICATE",
        "message": "同一 Cluster 内 hostname 已存在"
      }
    ]
  }
}
```

- `code` 为**稳定的机器可读值**（`UPPER_SNAKE_CASE`）；前端按 `code` 决定展示与分支，**不解析 `message`**。
- `details[].row` 仅在导入等行式请求中出现；普通请求省略。
- `message` 为人类可读描述，可随文案调整，不构成契约。

### 5. 状态码语义

| 状态码 | 语义 | `code` |
|---|---|---|
| 200 | 成功 | — |
| 201 | 创建成功 | — |
| 204 | 删除成功 | — |
| 400 | 请求格式或字段校验失败 | `VALIDATION_ERROR` |
| 401 | 未认证 | `UNAUTHENTICATED` |
| 403 | 无权限（V1 极少触发） | `FORBIDDEN` |
| 404 | 资源不存在或已被逻辑删除 | `NOT_FOUND` |
| 409 | 业务冲突：唯一性冲突、父资源存在活跃子资源 | `CONFLICT` |
| 500 | 服务端错误 | `INTERNAL_ERROR` |

### 6. Empty / Not Found 语义（落地 R-QUERY-004，全项目统一）

- 父资源不存在或已删除 → **404**；
- 父资源存在但无子资源 → **200** 且 `items` 为空数组。
- 前端必须为两种情形渲染**不同的**空态 / 错误态。

### 7. 导入端点

逐行错误使用同一信封，`details[].row` 标识数据行。**「All-or-Nothing 还是 Partial Success」由产品 OPEN-005 决定，本 ADR 不裁定。**

## Consequences

- 前端与后端可并行开发，因为字段名、类型与错误结构已固定。
- 逐行导入错误无需额外协议即可表达。
- 读路径存在 id 与 by-name 两套，文档需明确 canonical 与 alias 的关系。
- 导入端点在 OPEN-005 确认前无法定稿最终成功语义。

## 与 R-CLUSTER-005 的关系

R-CLUSTER-005 的技术理由是「Cluster 名称用于 URL 路径寻址」。本 ADR 采用 id 作为规范路径后，该理由部分减弱。

**用户已于 2026-09-15 裁定：保留 R-CLUSTER-005，不作调整。**

因此：

- 该规则作为 **CONFIRMED 产品规则**由本架构**无条件保留并强制校验** —— Cluster 登记的写入路径拒绝包含 `/` 的名称（F001 验收标准）；
- 方案 C 的 `by-name` 只读别名使该规则继续有实际意义；
- `/` 禁令的技术理由现为：**保证 `by-name` 路径别名可用**，并为未来可能的资源外部引用保留可读寻址。

该规则**不**由 Architect 或实现方重新解释；如需修改必须重新进入产品规划。

## Alternatives Considered

- **全部用名称寻址**：Cluster 重命名会破坏 URL；软删除后同名重建会造成历史 URL 歧义；把可变业务属性当主键。
- **全部用 id 且不提供名称别名**：与 R-CLUSTER-005 的产品意图不符。
- **RFC 7807 `application/problem+json`**：标准、工具支持好；但对本项目最核心的「逐行错误列表」仍需自定义扩展成员，`type` URI 概念对内部工具价值有限。
- **每个端点自定义错误结构**：前后端契约不一致，导入错误与普通错误无法统一渲染，**直接排除**。
- **API versioning / 游标分页**：当前无需求，属过早泛化（§25）。

## Affected Features

F001 ~ F015；直接决定 **F001**、F009、F010、F011、F012。

Milestone: **M1**（DEC-011 / DEC-014）。

## Reversibility

**高代价**。契约一旦被前端、测试、文档引用，任何字段改名都会引发全项目一致性工作。URL 一旦被引用，变更即产生兼容性成本。