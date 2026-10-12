/**
 * 用户与账号管理 API（F015，Contract：docs/api/F015.md v1，READY）。
 *
 * 端点（Contract §4，全部 USER_ADMIN，仅 ADMIN）：
 * - GET    /users            列表（role/status/q 过滤 + 分页 + 排序，§4.1）
 * - GET    /users/{id}       详情（§4.2；id 非 UUID → 404；不存在 404 NOT_FOUND）
 * - POST   /users            创建（201 {user:UserRow}；§4.3）
 * - PATCH  /users/{id}       更新角色 / 状态（body 必带 version 乐观锁，§4.4）
 *
 * 不提供（Contract §4.5；404/405）：无 register/signup/匿名建号；无
 * DELETE /users/{id}（账号以停用代替物理删除，I-9）；无改密 / 重置 / 首登
 * 强制改密端点（O-5 一期不实现）——本 client 同样不提供对应方法。
 *
 * 注意：
 * - UserRow 永不包含 password_hash（§4.1）；密码仅出现在创建请求体，绝不
 *   进入响应或 Audit（I-2；服务端 argon2 存 hash）。
 * - username：服务端 trim + 小写归一后须匹配 ^[a-z0-9._-]{3,64}$（§4.3）；
 *   重复 409 CONFLICT{reason:"unique_conflict",field:"username"}。
 * - password：创建必填非空；长度 8–128 为 Contract §8 的可实施默认（非产品
 *   业务规则），本地镜像见 AccountManagementPanel。
 * - PATCH：role/status 至少一个（都缺 422）；未知 / 只读字段 422；
 *   username/password_hash 不可出现（本类型不提供）；成功 200 version+1。
 * - 停用（DISABLED）同事务删该用户全部会话（旧 Cookie 401 AUTH_REQUIRED、
 *   登录 401 AUTH_INVALID_CREDENTIALS）；启用（ACTIVE）恢复登录；角色变更
 *   即时生效（§4.4）。
 * - 错误顺序（PATCH）：401→403→body(422)→对象(404)→版本(409)（§4.4）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { Role, UserStatus } from "./auth.ts";
import type { SortOrder } from "./clusters.ts";

/** 角色与用户状态复用 F002 auth 的同一类型定义（Contract §4.1 与 F002 §4.1 一致）。 */
export type { Role, UserStatus } from "./auth.ts";

/** 列表排序字段白名单（Contract §4.1：默认 created_at）。 */
export type UserSortField = "username" | "role" | "status" | "created_at" | "updated_at";

/**
 * UserRow（Contract §4.1）。与 F002 User（操作者视图）不同：管理视图含
 * version/created_at/updated_at、不含 permissions；永不包含 password_hash。
 */
export interface UserRow {
  id: string;
  username: string;
  role: Role;
  status: UserStatus;
  version: number;
  created_at: string;
  updated_at: string;
}

/** 列表响应（Contract §4.1：{items,page,page_size,total}）。 */
export interface UserListResponse {
  items: UserRow[];
  page: number;
  page_size: number;
  total: number;
}

/** 单对象响应信封（Contract §4.2/§4.3/§4.4：{"user":UserRow}）。 */
export interface UserEnvelope {
  user: UserRow;
}

/** GET /users 查询参数（省略项不发，由服务端默认值生效，Contract §4.1）。 */
export interface ListUsersQuery {
  role?: Role;
  status?: UserStatus;
  /** username 大小写不敏感子串（空 / 超长 → 422）。 */
  q?: string;
  page?: number;
  page_size?: number;
  sort?: UserSortField;
  order?: SortOrder;
}

/** 账号列表：GET /api/v1/users（USER_ADMIN，仅 ADMIN）。 */
export function listUsers(query: ListUsersQuery = {}): Promise<UserListResponse> {
  const search = new URLSearchParams();
  if (query.role !== undefined) {
    search.set("role", query.role);
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
  return request<UserListResponse>(`/users${queryString ? `?${queryString}` : ""}`);
}

/** 账号详情：GET /api/v1/users/{id}（USER_ADMIN）。id 非 UUID / 不存在 → 404。 */
export function getUser(id: string): Promise<UserEnvelope> {
  return request<UserEnvelope>(`/users/${encodeURIComponent(id)}`);
}

/** POST /users 请求体（Contract §4.3）。username/password/role 全部必填。 */
export interface CreateUserPayload {
  username: string;
  password: string;
  role: Role;
}

/**
 * 创建账号：POST /api/v1/users（USER_ADMIN）；201 {user:UserRow}。
 * 服务端 trim+小写归一 username、argon2 hash 密码（hash 不回显）；
 * 重复 username → 409 CONFLICT{unique_conflict,field:"username"}。
 */
export function createUser(payload: CreateUserPayload): Promise<UserEnvelope> {
  return request<UserEnvelope>("/users", { method: "POST", body: payload });
}

/**
 * PATCH /users/{id} 请求体（Contract §4.4）。
 * version 必填（乐观锁）；role/status 至少一个（都缺服务端 422）；
 * username/password_hash 不可出现（本类型不提供该形态）。
 */
export interface UpdateUserPayload {
  version: number;
  role?: Role;
  status?: UserStatus;
}

/**
 * 更新角色 / 状态：PATCH /api/v1/users/{id}（USER_ADMIN）；成功 200
 * {user:UserRow}（version+1）。停用同事务删该用户全部会话；角色变更即时生效。
 */
export function updateUser(id: string, payload: UpdateUserPayload): Promise<UserEnvelope> {
  return request<UserEnvelope>(`/users/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: payload,
  });
}

/**
 * 面向页面的写操作错误描述（Contract §4.3/§4.4/§6）：
 * - 409 CONFLICT unique_conflict：落为 username 字段级错误（field 恒为
 *   "username"，§4.3）。
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新最新数据后重新操作，绝不静默重试 / 覆盖。
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（username / password /
 *   role / version / status，Contract §4.3/§4.4）。
 * - 403：无 USER_ADMIN；404：账号不存在。
 */
export interface UserActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新最新数据后重改）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
  /** 字段级错误（422 fields / 409 CONFLICT unique_conflict 的 field）。 */
  fields: Record<string, string>;
}

/** 把写操作错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeUserActionError(error: unknown): UserActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
      fields: {},
    };
  }

  const result: UserActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
    fields: {},
  };
  const details = error.details ?? {};

  if (error.status === 409 && error.code === "VERSION_CONFLICT") {
    result.versionConflict = true;
    const current = details["current_version"];
    if (typeof current === "number") {
      result.currentVersion = current;
    }
    result.message =
      `该账号已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (reason === "unique_conflict") {
      // field 恒为 "username"（Contract §4.3）；形状不符时回退 username
      const field = details["field"];
      const fieldName = typeof field === "string" && field !== "" ? field : "username";
      result.fields[fieldName] =
        "username 与现有账号冲突（trim + 小写归一后唯一；已停用账号仍占用用户名）";
      result.message = `保存失败：${fieldName} 冲突。`;
    } else {
      result.message = `操作冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  } else if (error.status === 403) {
    result.message = "没有权限管理账号（需 USER_ADMIN 权限，服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "账号不存在（NOT_FOUND）。";
  }
  return result;
}
