/**
 * 认证 API（F002，Contract：docs/api/F002.md v1，READY）。
 *
 * 会话载体为 csm_session HttpOnly Cookie（服务端不透明会话，Contract §2），
 * 前端不接触令牌本身。权限集合由后端按 §23 矩阵计算返回；
 * 前端不复制矩阵，仅据返回值显示 / 隐藏，不作为安全边界（鉴权在服务端）。
 */
import { request } from "./client";

/** 用户角色（Contract §4.1：VIEWER / EDITOR / ADMIN）。 */
export type Role = "VIEWER" | "EDITOR" | "ADMIN";

/** 用户状态（Contract §4.1：ACTIVE / DISABLED；账号停用非软删）。 */
export type UserStatus = "ACTIVE" | "DISABLED";

/**
 * 操作者（Contract §4.1 user 对象）。
 * permissions 为 capability 字符串数组（服务端排序返回，可为空数组），
 * 语义以服务端返回为准，前端不解释角色与权限的对应关系。
 */
export interface User {
  id: string;
  username: string;
  role: Role;
  status: UserStatus;
  permissions: string[];
}

/** POST /auth/login 200 响应（Contract §4.1）。 */
export interface LoginResponse {
  user: User;
  /** 会话绝对过期时间（ISO-8601 UTC，无滑动续期）。 */
  expires_at: string;
}

/** GET /auth/me 200 响应（Contract §4.3）。 */
export interface MeResponse {
  user: User;
}

/**
 * 登录：POST /api/v1/auth/login（无需会话）。
 * 成功 200，服务端 Set-Cookie csm_session；凭据错误 / 未知用户 / 停用账号
 * 统一 401 AUTH_INVALID_CREDENTIALS（不区分账号存在性）；缺字段 / 空白 → 422。
 */
export function login(username: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
  });
}

/**
 * 登出：POST /api/v1/auth/logout（需有效会话）。
 * 成功 204 无正文；服务端删除会话行并清除 Cookie。
 * 无有效会话 → 401 AUTH_REQUIRED。
 */
export function logout(): Promise<void> {
  return request<void>("/auth/logout", { method: "POST" });
}

/**
 * 当前操作者：GET /api/v1/auth/me（需有效会话；GET 无同源校验）。
 * 未认证 / 会话过期 / 用户停用 → 401 AUTH_REQUIRED。
 */
export function me(): Promise<MeResponse> {
  return request<MeResponse>("/auth/me");
}
