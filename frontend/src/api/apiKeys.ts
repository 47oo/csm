/**
 * API Key 机器凭据 API（F017，Contract：docs/api/F017.md v1，READY）。
 *
 * 端点（Contract §4，全部 USER_ADMIN，仅 ADMIN；§1.2 权限矩阵）：
 * - GET  /api-keys              列表（user_id/status/q 过滤 + 分页 + 排序，§4.1）
 * - GET  /api-keys/{id}         详情（§4.2；id 非 UUID / 不存在 → 404 NOT_FOUND）
 * - POST /api-keys              创建（201 {"api_key":ApiKeyRow+"plaintext"}；§4.3）
 * - POST /api-keys/{id}/revoke  吊销（200 {"api_key":ApiKeyRow}；§4.4，无请求体）
 *
 * 不提供（Contract §4.5；404/405）：无更新端点（label / 有效期创建后不可改）、
 * 无删除、无恢复 / 重新启用（吊销立即且永久失效）——本 client 同样不提供
 * 对应方法。
 *
 * 注意：
 * - ApiKeyRow 永不包含 key_hash 或明文（§2/§5）；plaintext 仅出现在创建 201
 *   响应（CreatedApiKeyRow，§4.3），页面必须一次性展示、关闭后即从内存清除，
 *   不写日志 / 不入本地存储（§5 一次性明文纪律）。
 * - status 由服务端派生（revoked_at≠null → REVOKED，优先于 expires_at≤now →
 *   EXPIRED，否则 ACTIVE，§2）；列表 status 过滤按该派生值（§3）。
 * - 创建（§4.3）：user_id 须引用存在且 ACTIVE 的账号（不存在 / 非 UUID /
 *   非 ACTIVE → 422 字段级错误）；label trim 后非空、禁控制字符（Unicode
 *   Cc/Cf）、1..255 code point、不要求唯一（F017-OPEN-3 默认）；validity_days
 *   可选缺省 90、整数 1..365 含端点、无「永不过期」取值。
 * - 吊销（§4.4）：未知 / 非 UUID id → 404；已吊销 → 409 CONFLICT
 *   {reason:"already_revoked"}（不写审计、不改状态）；已过期未吊销 → 允许。
 * - 401 先于 403（§1）；401 由 client 全局处理器清登录态，错误仍抛给调用方。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node type
 *   stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { SortOrder } from "./clusters.ts";

/** 派生状态（Contract §2：服务端派生，REVOKED 优先于 EXPIRED）。 */
export type ApiKeyStatus = "ACTIVE" | "REVOKED" | "EXPIRED";

/** 列表排序字段白名单（Contract §3：默认 created_at；同刻 id 升序稳定）。 */
export type ApiKeySortField = "created_at" | "expires_at" | "label";

/**
 * ApiKeyRow（Contract §2）。列表 / 详情 / 吊销共用；绝不包含 key_hash 或
 * 明文（§5）；revoked_at 为 null 表示未吊销。
 */
export interface ApiKeyRow {
  id: string;
  user_id: string;
  username: string;
  label: string;
  status: ApiKeyStatus;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  created_by: string;
  created_by_username: string;
}

/** 创建 201 响应行（ApiKeyRow + plaintext；仅此一次返回，Contract §4.3/§5）。 */
export interface CreatedApiKeyRow extends ApiKeyRow {
  plaintext: string;
}

/** 列表响应（Contract §4.1：{items,page,page_size,total}；空结果 total=0）。 */
export interface ApiKeyListResponse {
  items: ApiKeyRow[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §4.2/§4.4：{"api_key":ApiKeyRow}）。 */
export interface ApiKeyEnvelope {
  api_key: ApiKeyRow;
}

/** 创建响应信封（Contract §4.3：{"api_key":CreatedApiKeyRow}）。 */
export interface CreatedApiKeyEnvelope {
  api_key: CreatedApiKeyRow;
}

/** GET /api-keys 查询参数（省略项不发，由服务端默认值生效，Contract §4.1）。 */
export interface ListApiKeysQuery {
  /** 绑定账号 id（UUID，可选；按账号过滤）。 */
  user_id?: string;
  status?: ApiKeyStatus;
  /** label 大小写不敏感子串（trim 后空 / 超 255 → 422）。 */
  q?: string;
  page?: number;
  page_size?: number;
  sort?: ApiKeySortField;
  order?: SortOrder;
}

/** API Key 列表：GET /api/v1/api-keys（USER_ADMIN，仅 ADMIN）。 */
export function listApiKeys(query: ListApiKeysQuery = {}): Promise<ApiKeyListResponse> {
  const search = new URLSearchParams();
  if (query.user_id !== undefined && query.user_id !== "") {
    search.set("user_id", query.user_id);
  }
  if (query.status !== undefined) {
    search.set("status", query.status);
  }
  if (query.q !== undefined && query.q !== "") {
    search.set("q", query.q);
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
  return request<ApiKeyListResponse>(`/api-keys${queryString ? `?${queryString}` : ""}`);
}

/** API Key 详情：GET /api/v1/api-keys/{id}（USER_ADMIN）。id 非 UUID / 不存在 → 404。 */
export function getApiKey(id: string): Promise<ApiKeyEnvelope> {
  return request<ApiKeyEnvelope>(`/api-keys/${encodeURIComponent(id)}`);
}

/** POST /api-keys 请求体（Contract §4.3）。user_id/label 必填；validity_days 可选（缺省 90）。 */
export interface CreateApiKeyPayload {
  user_id: string;
  label: string;
  validity_days?: number;
}

/**
 * 创建 API Key：POST /api/v1/api-keys（USER_ADMIN）；201 {"api_key":CreatedApiKeyRow}。
 * plaintext 仅此一次返回（§4.3/§5）；user_id 不存在 / 非 ACTIVE、label 非法、
 * validity_days 越界 → 422 VALIDATION_ERROR{fields}。
 */
export function createApiKey(payload: CreateApiKeyPayload): Promise<CreatedApiKeyEnvelope> {
  return request<CreatedApiKeyEnvelope>("/api-keys", { method: "POST", body: payload });
}

/**
 * 吊销 API Key：POST /api/v1/api-keys/{id}/revoke（USER_ADMIN；无请求体，
 * Contract §4.4）。成功 200 {"api_key":ApiKeyRow}（revoked_at 已置、
 * status="REVOKED"）；已吊销 → 409 CONFLICT{reason:"already_revoked"}；
 * 未知 / 非 UUID id → 404。吊销立即生效且不可恢复 / 重新启用。
 */
export function revokeApiKey(id: string): Promise<ApiKeyEnvelope> {
  return request<ApiKeyEnvelope>(`/api-keys/${encodeURIComponent(id)}/revoke`, {
    method: "POST",
  });
}

/**
 * 面向页面的列表查询错误描述（Contract §4.1：401/403/422/500）：
 * - 401：无有效凭据（会话过期等；client 已触发全局处理器清登录态）；
 * - 403：无 USER_ADMIN；422：查询参数校验失败；
 * - 500 / 网络层错误：兑底文案，不伪装成空列表。
 */
export interface ApiKeyQueryError {
  message: string;
  code: string | null;
}

/** 把列表查询错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeApiKeyQueryError(error: unknown): ApiKeyQueryError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return { message: "无法连接服务器，请稍后重试", code: null };
  }

  const result: ApiKeyQueryError = {
    message: displayError(error),
    code: error.code,
  };

  if (error.status === 401) {
    result.message = "未认证或会话已过期（AUTH_REQUIRED）；请重新登录后再查询。";
  } else if (error.status === 403) {
    result.message =
      "没有权限查看 API Key（需 USER_ADMIN 权限，服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.message = "查询参数校验失败（VALIDATION_ERROR）；请修正过滤条件后重试。";
  }
  return result;
}

/**
 * 面向页面的写操作错误描述（Contract §4.3/§4.4）：
 * - 409 CONFLICT already_revoked：alreadyRevoked=true（可能已被他人吊销，
 *   提示刷新列表，不静默重试）；
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（user_id / label /
 *   validity_days，键为服务端字段名，页面经 apiKeyFormFieldFromPath 映射）；
 * - 403：无 USER_ADMIN；404：Key 不存在（列表数据过期，请刷新）。
 */
export interface ApiKeyActionError {
  message: string;
  code: string | null;
  /** 409 CONFLICT already_revoked（重复吊销；刷新列表后重做）。 */
  alreadyRevoked: boolean;
  /** 字段级错误（422 fields；键为服务端字段名 user_id/label/validity_days）。 */
  fields: Record<string, string>;
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeApiKeyActionError(error: unknown): ApiKeyActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      alreadyRevoked: false,
      fields: {},
    };
  }

  const result: ApiKeyActionError = {
    message: displayError(error),
    code: error.code,
    alreadyRevoked: false,
    fields: {},
  };
  const details = error.details ?? {};

  if (
    error.status === 409 &&
    error.code === "CONFLICT" &&
    details["reason"] === "already_revoked"
  ) {
    result.alreadyRevoked = true;
    result.message =
      "该 API Key 已被吊销（可能已被其他人操作）。请刷新列表查看最新状态；" +
      "系统不会自动重试。";
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message =
      "没有权限管理 API Key（需 USER_ADMIN 权限，服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "API Key 不存在（列表数据可能已过期，请刷新；NOT_FOUND）。";
  }
  return result;
}
