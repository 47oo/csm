/**
 * 认证 API 客户端（F013）。
 *
 * 唯一契约依据：docs/api/f013-auth.md（READY）。
 * - 端点恰为三个：POST /api/auth/login（唯一豁免端点）、POST /api/auth/logout、
 *   GET /api/auth/session；
 * - AuthenticatedUser 字段集合封闭（契约 §4）：仅 id / username，不存在其他字段；
 * - Cookie（csm_session，HttpOnly）由浏览器按 Set-Cookie 管理，本层不读不写任何令牌；
 * - 登录路径不做长度 / 复杂度校验（R-AUTH-004 不属登录路径，契约 §8），
 *   username / password 原样提交（契约 §5.1：不 trim、不变换）；
 * - 登录失败三情形（用户名不存在 / 口令错误 / 账号停用）在服务端返回完全相同的
 *   401（R-AUTH-006），本层不做任何区分尝试，消费方按 error.code 分支即可。
 */
import { apiRequest } from './http'

/** 已认证用户表示（契约 §4；登录成功与会话校验返回同一结构）。 */
export interface AuthenticatedUser {
  /** 不可变代理主键。 */
  id: number
  /** 登录名，原样返回（不做大小写折叠 / 归一化）。 */
  username: string
}

/** 登录请求体（契约 §5.1）：两个字段均必填 string，原样提交。 */
export interface LoginBody {
  username: string
  password: string
}

/**
 * 登录（契约 §5.1，唯一豁免端点）。
 *
 * 成功 → 200 + AuthenticatedUser（会话 Cookie 由浏览器管理）；
 * 凭据失败（用户名不存在 / 口令错误 / 账号停用，三者不可区分）→
 * 401 UNAUTHENTICATED。
 *
 * 登录自身负责 401 语义（停留登录页并提示失败），因此抑制全局 401 跳转。
 */
export function login(body: LoginBody): Promise<AuthenticatedUser> {
  return apiRequest<AuthenticatedUser>('/api/auth/login', {
    method: 'POST',
    body,
    suppressAuthRedirect: true,
  })
}

/**
 * 登出（契约 §5.2）。成功 → 204（无响应体）；会话已失效 → 401 UNAUTHENTICATED。
 *
 * 契约要求调用方把 204 与 401 归一为同一处理（清理本地状态 + 跳转登录页），
 * 该归一由调用方（App.vue 登出按钮）完成。
 */
export function logout(): Promise<void> {
  return apiRequest<void>('/api/auth/logout', { method: 'POST' })
}

/**
 * 读取当前会话身份（契约 §5.3）。用于启动时判断「当前是否已登录」。
 *
 * 200 → AuthenticatedUser；无有效会话 → 401 UNAUTHENTICATED（由调用方引导登录页）。
 *
 * 启动期探测自身负责 401 语义（未登录是正常分支，不是异常跳转），因此抑制全局 401 跳转。
 */
export function getCurrentSession(): Promise<AuthenticatedUser> {
  return apiRequest<AuthenticatedUser>('/api/auth/session', {
    method: 'GET',
    suppressAuthRedirect: true,
  })
}
