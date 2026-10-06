/**
 * API 客户端（F001 工程底座）。
 *
 * base path 固定为同源相对路径 /api/v1（需求 §25；架构 §1.2）：
 * 浏览器请求发往同源入口 Nginx，由其代理到 backend 服务，
 * 因此无需 CORS 配置，也不存在硬编码主机地址。
 * 本文件不含任何密钥或敏感信息。
 */

const API_BASE_PATH = "/api/v1";

/** 非 2xx 响应时抛出的错误。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_PATH}${path}`, {
    headers: { Accept: "application/json" },
  });

  if (!response.ok) {
    throw new ApiError(`HTTP ${response.status}`, response.status);
  }

  return (await response.json()) as T;
}

/** GET /api/v1/health 响应体（架构 §1.4：200 {"status":"ok","service":"csm-backend"}）。 */
export interface Health {
  status: string;
  service: string;
}

/** 查询后端 liveness（不触库）。失败（网络错误 / 非 2xx / 非法 JSON）时 reject。 */
export function getHealth(): Promise<Health> {
  return requestJson<Health>("/health");
}
