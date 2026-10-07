/**
 * Cluster API（F003，Contract：docs/api/F003.md v1，READY）。
 *
 * 端点（Contract §6）：
 * - GET    /clusters                        列表（分页/排序/过滤/模糊/软删可见性，§4/§5）
 * - POST   /clusters                        创建（201 {"cluster":Cluster}）
 * - GET    /clusters/{id}                   详情（?deleted=true 需 VIEW_DELETED）
 * - PATCH  /clusters/{id}                   部分更新（body 必带 version；code 不可改）
 * - DELETE /clusters/{id}?version=N         软删（204；version 为 Query 参数，§6.5）
 * - POST   /clusters/{id}/restore?version=N 恢复（200 deleted_at=null）
 *
 * 注意：
 * - PATCH 仅携带变化字段（JSON.stringify 丢弃 undefined 属性；
 *   省略 = 保持原值不重置，Contract §6.4）；description 显式 null = 清空。
 * - 409 CONFLICT / VERSION_CONFLICT 的页面呈现语义见 describeClusterActionError；
 *   任何写失败都不自动重试（Contract §7）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（Vite 构建同样支持）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";

/** 集群状态（Contract §3：ACTIVE | INACTIVE，创建默认 ACTIVE）。 */
export type ClusterStatus = "ACTIVE" | "INACTIVE";

/** 软删可见性（Contract §5：exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
export type DeletedMode = "exclude" | "include" | "only";

/** 列表排序字段白名单（Contract §4；sort=code 实际按 code_key 排序）。 */
export type ClusterSortField = "code" | "name" | "status" | "created_at" | "updated_at";

/** 排序方向（Contract §4：默认 desc，附 id 升序稳定）。 */
export type SortOrder = "asc" | "desc";

/** Cluster 响应对象（Contract §3）。code_key 为内部列，不暴露。 */
export interface Cluster {
  id: string;
  code: string;
  name: string;
  status: ClusterStatus;
  description: string | null;
  metadata: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

/** 列表响应（Contract §4：{items, page, page_size, total}）。 */
export interface ClusterListResponse {
  items: Cluster[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §6.2/§6.3/§6.4/§6.6：{"cluster":Cluster}）。 */
export interface ClusterEnvelope {
  cluster: Cluster;
}

/** GET /clusters 查询参数（省略项不发，由服务端默认值生效，Contract §4）。 */
export interface ListClustersQuery {
  /** code/name 大小写不敏感子串匹配（ILIKE）。 */
  q?: string;
  /** code 精确过滤（服务端归一化后比 code_key；格式非法 422）。 */
  code?: string;
  status?: ClusterStatus;
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
  sort?: ClusterSortField;
  order?: SortOrder;
}

/** 列表查询：GET /api/v1/clusters（READ；deleted=include|only 另需 VIEW_DELETED）。 */
export function listClusters(query: ListClustersQuery = {}): Promise<ClusterListResponse> {
  const search = new URLSearchParams();
  if (query.q !== undefined && query.q !== "") {
    search.set("q", query.q);
  }
  if (query.code !== undefined && query.code !== "") {
    search.set("code", query.code);
  }
  if (query.status !== undefined) {
    search.set("status", query.status);
  }
  if (query.deleted !== undefined) {
    search.set("deleted", query.deleted);
  }
  if (query.page !== undefined) {
    search.set("page", String(query.page));
  }
  if (query.page_size !== undefined) {
    search.set("page_size", String(query.page_size));
  }
  if (query.sort !== undefined) {
    search.set("sort", query.sort);
  }
  if (query.order !== undefined) {
    search.set("order", query.order);
  }
  const queryString = search.toString();
  return request<ClusterListResponse>(`/clusters${queryString ? `?${queryString}` : ""}`);
}

/** POST /clusters 请求体（Contract §6.2：code/name 必填，其余可选默认）。 */
export interface CreateClusterPayload {
  code: string;
  name: string;
  status?: ClusterStatus;
  description?: string | null;
  metadata?: Record<string, unknown>;
}

/** 创建：POST /api/v1/clusters（WRITE）；201；code 冲突 409 CONFLICT{unique_conflict}。 */
export function createCluster(payload: CreateClusterPayload): Promise<ClusterEnvelope> {
  return request<ClusterEnvelope>("/clusters", { method: "POST", body: payload });
}

/** 详情：GET /api/v1/clusters/{id}（READ）。已删对象需显式 deleted=true 且具 VIEW_DELETED，否则 404（§5）。 */
export function getCluster(
  id: string,
  options: { deleted?: boolean } = {},
): Promise<ClusterEnvelope> {
  const search = new URLSearchParams();
  if (options.deleted) {
    search.set("deleted", "true");
  }
  const queryString = search.toString();
  return request<ClusterEnvelope>(
    `/clusters/${encodeURIComponent(id)}${queryString ? `?${queryString}` : ""}`,
  );
}

/**
 * PATCH /clusters/{id} 请求体（Contract §6.4）。
 * version 必填；其余字段省略 = 保持原值不重置；description 显式 null = 清空；
 * metadata 整值替换；code 不可改（前端不提供编辑 code，出现即 422）。
 */
export interface UpdateClusterPayload {
  version: number;
  name?: string;
  status?: ClusterStatus;
  description?: string | null;
  metadata?: Record<string, unknown>;
}

/** 部分更新：PATCH /api/v1/clusters/{id}（WRITE）；成功 200，version+1。 */
export function updateCluster(
  id: string,
  payload: UpdateClusterPayload,
): Promise<ClusterEnvelope> {
  return request<ClusterEnvelope>(`/clusters/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/** 软删：DELETE /api/v1/clusters/{id}?version=N（DELETE_OBJECT；204，不级联）。 */
export function deleteCluster(id: string, version: number): Promise<void> {
  const search = new URLSearchParams({ version: String(version) });
  return request<void>(`/clusters/${encodeURIComponent(id)}?${search.toString()}`, {
    method: "DELETE",
  });
}

/** 恢复：POST /api/v1/clusters/{id}/restore?version=N（RESTORE；200，仅恢复自身）。 */
export function restoreCluster(id: string, version: number): Promise<ClusterEnvelope> {
  const search = new URLSearchParams({ version: String(version) });
  return request<ClusterEnvelope>(
    `/clusters/${encodeURIComponent(id)}/restore?${search.toString()}`,
    { method: "POST" },
  );
}

/**
 * 面向页面的写操作错误描述（Contract §1.2/§7）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射；unique_conflict 落为字段级错误。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误。
 * - 403 / 404：明确文案（权限不足 / 对象不存在，不泄露存在性细节）。
 */
export interface ClusterActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
  /** 删除被引用阻止时的引用列表（CONFLICT reference_exists；F003 为空集）。 */
  references: { object_type: string; object_id: string; label: string }[];
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict: "code 与现有集群冲突（大小写不敏感；已删除的集群仍占用 code，不可复用）",
  reference_exists: "仍有其它对象引用该集群，无法删除",
  not_deleted: "该集群未处于已删除状态，无需恢复",
  dependency_deleted: "恢复失败：依赖的对象仍处于已删除状态",
};

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeClusterActionError(error: unknown): ClusterActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
      fields: {},
      references: [],
    };
  }

  const result: ClusterActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
    references: [],
  };
  const details = error.details ?? {};

  if (error.status === 409 && error.code === "VERSION_CONFLICT") {
    result.versionConflict = true;
    const current = details["current_version"];
    if (typeof current === "number") {
      result.currentVersion = current;
    }
    result.message =
      `该集群已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "code";
      result.fields[fieldName] = CONFLICT_REASON_MESSAGES["unique_conflict"];
      result.message = `保存失败：${fieldName} 冲突。`;
    } else if (typeof reason === "string" && reason in CONFLICT_REASON_MESSAGES) {
      result.message = `${CONFLICT_REASON_MESSAGES[reason]}（CONFLICT/${reason}）`;
      if (reason === "reference_exists") {
        result.references = parseReferences(details["references"]);
      }
    } else {
      result.message = `操作冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message = "没有权限执行该操作（服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "集群不存在，或已删除且您无权查看（NOT_FOUND）。";
  }
  return result;
}

/** 解析 CONFLICT reference_exists 的 references 列表（形状不符返回空数组）。 */
function parseReferences(value: unknown): ClusterActionError["references"] {
  if (!Array.isArray(value)) {
    return [];
  }
  const references: ClusterActionError["references"] = [];
  for (const item of value) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const { object_type, object_id, label } = item as Record<string, unknown>;
    if (
      typeof object_type === "string" &&
      typeof object_id === "string" &&
      typeof label === "string"
    ) {
      references.push({ object_type, object_id, label });
    }
  }
  return references;
}
