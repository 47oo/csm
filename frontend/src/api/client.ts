/**
 * API 客户端（F001 工程底座 + F002 认证横切扩展）。
 *
 * base path 固定为同源相对路径 /api/v1（需求 §25；架构 §1.2）：
 * 浏览器请求发往同源入口 Nginx，由其代理到 backend 服务，
 * 因此无需 CORS 配置，也不存在硬编码主机地址。
 * 本文件不含任何密钥或敏感信息。
 *
 * F002 扩展（Contract：docs/api/F002.md v1）：
 * - 所有请求 credentials: "include"，携带 csm_session HttpOnly Cookie（§2）。
 * - 非 2xx 解析统一错误信封 {"error":{code,message,details}}（§1.1）；
 *   响应体缺失 / 非 JSON / 形状不符时回退为仅含 HTTP 状态的 ApiError，不伪造信封内容。
 * - 401 = 尚无有效身份（§1.2）：先触发全局 401 处理器（应用壳注册，
 *   用于清登录态回登录页），错误仍照常抛给调用方呈现。
 * - 403 / 409 由调用方按 code / details 明确呈现；任何失败都不自动重试。
 *
 * F003 扩展（Contract：docs/api/F003.md v1）：
 * - method 增加 PATCH / DELETE（Cluster 部分更新 / 软删；仍同源携带 Cookie，不重试）。
 * - envelopeFieldErrors：提取 422 VALIDATION_ERROR 的 details.fields 字段级错误。
 *
 * F014 扩展（Contract：docs/api/F014.md v1）：
 * - requestUpload：multipart/form-data 上传（资源导入 validate / resources 端点）。
 *   不手动设置 Content-Type（由 fetch 生成含 boundary 的 multipart 头）；
 *   错误信封 / 401 全局处理 / 204 / 不重试语义与 request 完全一致。
 */

const API_BASE_PATH = "/api/v1";

/** 统一错误信封的 details（Contract §1.1：无附加信息时为 {}）。 */
export type ApiErrorDetails = Record<string, unknown>;

/** 非 2xx 响应时抛出的错误；code / details 来自统一错误信封，无法解析时为 null。 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: ApiErrorDetails | null;

  constructor(
    message: string,
    status: number,
    code: string | null = null,
    details: ApiErrorDetails | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** 判断未知错误是否为 ApiError。 */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** 全局 401 处理器：任意请求收到 401 时调用。 */
type UnauthorizedHandler = () => void;

let unauthorizedHandler: UnauthorizedHandler | null = null;

/**
 * 注册 / 注销全局 401 处理器（传 null 注销）。
 * 应用壳用它清登录态并回到登录页；登录接口自身收到 401（凭据错误）时
 * 页面已在登录页，重复触发无副作用。
 */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

/** 统一错误信封形状（Contract §1.1）。 */
interface ErrorEnvelope {
  code: string;
  message: string;
  details?: unknown;
}

/** 尝试把错误响应体解析为统一信封；失败返回 null（不抛错、不掩盖原始状态码）。 */
async function parseErrorEnvelope(response: Response): Promise<ErrorEnvelope | null> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return null;
  }
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const error = (body as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) {
    return null;
  }
  const { code, message, details } = error as {
    code?: unknown;
    message?: unknown;
    details?: unknown;
  };
  if (typeof code !== "string" || typeof message !== "string") {
    return null;
  }
  return { code, message, details };
}

/** details 归一化：仅接受对象，其余（缺失 / 标量）归为 null。 */
function toDetails(details: unknown): ApiErrorDetails | null {
  if (typeof details === "object" && details !== null) {
    return details as ApiErrorDetails;
  }
  return null;
}

/** 请求选项。 */
export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  /** 请求体（JSON 序列化）；undefined 表示无正文。 */
  body?: unknown;
}

/**
 * 发起 API 请求（同源 /api/v1 + Cookie）。
 * - 非 2xx：解析信封后抛 ApiError；401 先触发全局处理器再抛出。
 * - 204：返回 undefined（无正文，Contract §4.2）。
 * - 不重试：网络错误由 fetch 直接 reject（非 ApiError），调用方按未知错误呈现；
 *   任何失败都不自动重发（不静默重试覆盖，Contract §6）。
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_PATH}${path}`, {
    method: options.method ?? "GET",
    headers: {
      Accept: "application/json",
      ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    // csm_session 为 HttpOnly Cookie（Contract §2），必须随同源请求发送
    credentials: "include",
  });
  return handleResponse<T>(response);
}

/** 上传请求选项（multipart/form-data；body 为 FormData）。 */
export interface UploadRequestOptions {
  method?: "POST" | "PATCH" | "DELETE";
  /** multipart 表单体；undefined 表示无正文。 */
  body?: FormData;
}

/** 响应统一处理（request / requestUpload 共用；信封解析、401、204、不重试）。 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 401) {
      unauthorizedHandler?.();
    }
    const envelope = await parseErrorEnvelope(response);
    throw new ApiError(
      envelope ? envelope.message : `HTTP ${response.status}`,
      response.status,
      envelope?.code ?? null,
      envelope ? toDetails(envelope.details) : null,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * 发起 multipart 上传请求（同源 /api/v1 + Cookie；F014 导入端点）。
 * - 不设置 Content-Type：由 fetch / 浏览器自动生成
 *   `multipart/form-data; boundary=…`（手动设置会破坏 boundary）。
 * - 非 2xx / 401 / 204 / 不重试语义与 request 完全一致（共用 handleResponse）。
 */
export async function requestUpload<T>(
  path: string,
  options: UploadRequestOptions = {},
): Promise<T> {
  const response = await fetch(`${API_BASE_PATH}${path}`, {
    method: options.method ?? "POST",
    headers: {
      Accept: "application/json",
    },
    body: options.body,
    // csm_session 为 HttpOnly Cookie（Contract §2），必须随同源请求发送
    credentials: "include",
  });
  return handleResponse<T>(response);
}

/** GET /api/v1/health 响应体（架构 §1.4：200 {"status":"ok","service":"csm-backend"}）。 */
export interface Health {
  status: string;
  service: string;
}

/** 查询后端 liveness（不触库）。失败（网络错误 / 非 2xx / 非法 JSON）时 reject。 */
export function getHealth(): Promise<Health> {
  return request<Health>("/health");
}

/**
 * 将任意错误转为面向用户的展示文案。
 * ApiError 使用信封 message（后端保证不含凭据 / 账号存在性 / 堆栈，Contract §1.1），
 * 并附错误码便于识别；其他错误（网络层等）用固定文案，不伪装成业务错误。
 */
export function displayError(error: unknown): string {
  if (isApiError(error)) {
    return error.code ? `${error.message}（${error.code}）` : error.message;
  }
  return "无法连接服务器，请稍后重试";
}

/**
 * 从 422 VALIDATION_ERROR 信封的 details.fields 提取字段级错误
 * （F002/F003 Contract §1.2：{"fields":[{"field":str,"message":str}]}）。
 * 形状不符 / 缺失时返回空对象，不伪造内容。
 */
export function envelopeFieldErrors(details: ApiErrorDetails | null): Record<string, string> {
  if (details === null) {
    return {};
  }
  const fields = details["fields"];
  if (!Array.isArray(fields)) {
    return {};
  }
  const result: Record<string, string> = {};
  for (const item of fields) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const { field, message } = item as { field?: unknown; message?: unknown };
    if (typeof field === "string" && typeof message === "string") {
      result[field] = message;
    }
  }
  return result;
}
