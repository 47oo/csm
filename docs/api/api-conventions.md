# CSM API 约定

> Status: **READY**
> Source: `docs/architecture/adr/adr-0003-resource-identity-and-api-contract.md`（Status: `ACCEPTED`，2026-09-15）
> 本文件的规范已由用户批准（DEC-014）。导入端点语义已由用户裁定为 **All-or-Nothing**（原 BQ-3 / 产品 OPEN-005）。

---

## 1. 通用形式

- REST + JSON，UTF-8 编码
- 路径前缀 `/api`
- 集合资源用复数名词，字段用 `snake_case`
- 不引入 API versioning（当前无需求）

## 2. 资源标识与寻址

- 规范路径使用不可变代理主键 `id`：`/api/clusters/{cluster_id}`
- 写操作（POST / PATCH / DELETE）**一律**走 `id` 路径
- 只读名称别名（尊重 R-CLUSTER-005）：
  - `GET /api/clusters/by-name/{cluster_name}`
  - `GET /api/clusters/by-name/{cluster_name}/bare-metals`
- `{cluster_name}` 大小写敏感匹配；已逻辑删除的 Cluster 不参与名称解析

## 3. 列表与分页

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 50
}
```

| 参数 | 说明 |
|---|---|
| `page` | 从 1 起，默认 1 |
| `page_size` | 默认 50，上限由后端界定 |

## 4. 字段类型约定

| 类型 | 约定 |
|---|---|
| `id` | 整数 |
| 时间 | RFC 3339 字符串 |
| 状态 | 字符串枚举（仅 `bare_metal.status` 存在） |
| 可选字段空值 | 返回 `null`，不省略（便于前端使用固定 schema） |
| `deleted_at` | **不对外暴露** |

## 5. 错误信封

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

- `error.code` 为**稳定的机器可读值**（`UPPER_SNAKE_CASE`）。前端按 `code` 分支，**不解析 `message`**。
- `details[].row` 仅在导入等行式请求中出现（支撑 R-IMPORT-003）；普通请求省略。
- `message` 为人类可读描述，可随文案调整，不构成契约。

## 6. 状态码语义

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

## 7. Empty / Not Found 语义（R-QUERY-004）

| 情形 | 响应 |
|---|---|
| 父资源不存在或已逻辑删除 | **404** `NOT_FOUND` |
| 父资源存在但无子资源 | **200**，`items` 为空数组 |

前端必须为这两种情形渲染**不同**的空态 / 错误态。这是产品语义差异，不是展示细节。

## 8. 导入端点

- 逐行错误使用同一错误信封，`details[].row` 标识数据行（R-IMPORT-003）。
- **成功语义：All-or-Nothing**（用户于 2026-09-15 裁定，原产品 OPEN-005）：
  - 只要有任意一行校验失败，**整个导入不产生任何写入**，响应 `400` + `VALIDATION_ERROR`，`details[]` 列出**全部**失败行（不因首行失败而提前中止报错）；
  - `message` 应汇总失败行数，例如「导入失败：共 37 行校验未通过」；
  - 全部行通过时，在**单一事务**内完成全部写入，返回 `201` 与写入条数；
  - 严禁部分写入：若事务提交失败，必须回滚并返回 `500` `INTERNAL_ERROR`，不得留下部分数据。
- 该端点**不提供**「跳过错误行继续导入」模式。若未来需要，属新产品需求。
- 导入校验必须与页面人工录入使用**同一套**领域校验（R-IMPORT-002）。

## 9. 未定项

- 各资源的完整端点清单（随各 Feature 的 Architecture Handoff 定义）
- `page_size` 上限具体数值