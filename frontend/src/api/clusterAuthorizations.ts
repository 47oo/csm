/**
 * 集群范围授权 API（F026，Contract：docs/api/F026.md v1，READY）。
 *
 * 三个端点全部 USER_ADMIN（仅 ADMIN）：
 * - GET  /users/{user_id}/cluster-authorizations   列表（status/cluster_id/q + 分页排序）
 * - POST /users/{user_id}/cluster-authorizations   授予（201）
 * - POST /cluster-authorizations/{id}/revoke       撤销（200，无请求体）
 *
 * 不提供 PATCH / DELETE / detail / batch / restore；本 client 不提供对应方法。
 * F026 只管理授权事实；对既有业务数据的范围过滤在 F027 交付。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { SortOrder } from "./clusters.ts";

export type AuthorizationStatus = "ACTIVE" | "REVOKED";
export type AuthorizationSortField = "granted_at" | "revoked_at";

export interface AuthorizationUserRef {
  id: string;
  username: string;
  role: "VIEWER" | "EDITOR" | "ADMIN";
  status: "ACTIVE" | "DISABLED";
}

export interface AuthorizationClusterRef {
  id: string;
  code: string;
  name: string;
  status: "ACTIVE" | "INACTIVE";
  deleted_at: string | null;
}

export interface ClusterAuthorizationRow {
  id: string;
  user: AuthorizationUserRef;
  cluster: AuthorizationClusterRef;
  status: AuthorizationStatus;
  effective: boolean;
  granted_at: string;
  granted_by: string | null;
  granted_by_username: string | null;
  revoked_at: string | null;
  revoked_by: string | null;
  revoked_by_username: string | null;
}

export interface ClusterAuthorizationListResponse {
  items: ClusterAuthorizationRow[];
  page: number;
  page_size: number;
  total: number;
}

export interface ClusterAuthorizationEnvelope {
  cluster_authorization: ClusterAuthorizationRow;
}

export interface ListClusterAuthorizationsQuery {
  status?: AuthorizationStatus;
  cluster_id?: string;
  q?: string;
  page?: number;
  page_size?: number;
  sort?: AuthorizationSortField;
  order?: SortOrder;
}

export function listClusterAuthorizations(
  userId: string,
  query: ListClusterAuthorizationsQuery = {},
): Promise<ClusterAuthorizationListResponse> {
  const search = new URLSearchParams();
  if (query.status !== undefined) search.set("status", query.status);
  if (query.cluster_id !== undefined && query.cluster_id !== "") {
    search.set("cluster_id", query.cluster_id);
  }
  if (query.q !== undefined && query.q !== "") search.set("q", query.q);
  if (query.page !== undefined) search.set("page", String(query.page));
  if (query.page_size !== undefined) search.set("page_size", String(query.page_size));
  if (query.sort !== undefined) search.set("sort", query.sort);
  if (query.order !== undefined) search.set("order", query.order);
  const qs = search.toString();
  return request<ClusterAuthorizationListResponse>(
    `/users/${encodeURIComponent(userId)}/cluster-authorizations${qs ? `?${qs}` : ""}`,
  );
}

export function grantClusterAuthorization(
  userId: string,
  clusterId: string,
): Promise<ClusterAuthorizationEnvelope> {
  return request<ClusterAuthorizationEnvelope>(
    `/users/${encodeURIComponent(userId)}/cluster-authorizations`,
    { method: "POST", body: { cluster_id: clusterId } },
  );
}

export function revokeClusterAuthorization(
  authorizationId: string,
): Promise<ClusterAuthorizationEnvelope> {
  return request<ClusterAuthorizationEnvelope>(
    `/cluster-authorizations/${encodeURIComponent(authorizationId)}/revoke`,
    { method: "POST" },
  );
}

export interface ClusterAuthorizationActionError {
  message: string;
  code: string | null;
  alreadyGranted: boolean;
  alreadyRevoked: boolean;
  fields: Record<string, string>;
}

export function describeClusterAuthorizationError(
  error: unknown,
): ClusterAuthorizationActionError {
  if (!isApiError(error)) {
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      alreadyGranted: false,
      alreadyRevoked: false,
      fields: {},
    };
  }
  const result: ClusterAuthorizationActionError = {
    message: displayError(error),
    code: error.code,
    alreadyGranted: false,
    alreadyRevoked: false,
    fields: {},
  };
  if (error.status === 401) {
    result.message = "未认证或会话已过期（AUTH_REQUIRED）；请重新登录。";
  } else if (error.status === 403) {
    result.message = "没有权限管理集群授权（需 USER_ADMIN，服务端已拒绝）。";
  } else if (error.status === 404) {
    result.message = "账号或授权不存在（NOT_FOUND）；请刷新后重试。";
  } else if (error.status === 409) {
    const reason = (error.details?.reason as string | undefined) ?? "";
    result.alreadyGranted = reason === "already_granted";
    result.alreadyRevoked = reason === "already_revoked";
    result.message = result.alreadyGranted
      ? "该账号已有此集群的有效授权（可能已被他人授予），已拒绝重复授予。"
      : result.alreadyRevoked
        ? "该授权已被撤销（可能已被他人操作），请刷新列表。"
        : displayError(error);
  } else if (error.status === 422) {
    result.fields = envelopeFieldErrors(error.details);
    result.message = "请求校验失败（VALIDATION_ERROR）；请检查目标账号与集群。";
  }
  return result;
}
