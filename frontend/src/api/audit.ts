/**
 * Audit 完整查询 API（F015，Contract：docs/api/F015.md v1，READY）。
 *
 * 端点（Contract §2）：
 * - GET /audit    完整审计查询（AUDIT_READ，仅 ADMIN；只读、无请求体、幂等，
 *                 不写新 Audit，§22/A5/A8）
 *
 * 注意：
 * - 无任何修改 / 删除 / 清空 Audit 的端点（A8/A30/T36）；本 client 也不提供
 *   对应方法，前端仅只读查询。
 * - 查询条件 AND 组合（§2.1）：operator（operator_username 精确匹配，服务端
 *   trim+小写归一；本 client 发送 trim 后原样值，归一由服务端执行）、
 *   object_type（9 值，8 类资源对象 + user）、object_id（UUID，须与
 *   object_type 同现，否则服务端 422——本地镜像见
 *   components/auditQueryForm.ts）、action（4 值）、created_from/created_to
 *   （ISO-8601 UTC 闭区间，from>to 422）。
 * - 排序仅 created_at（order asc|desc，默认 desc），同刻 id 恒升序（§2.1）；
 *   空结果 200 {items:[],page,page_size,total:0}。
 * - 校验顺序 401→403→422→200；错误信封复用 F002 §1.1/§1.2，不新增错误码。
 * - AuditRow 不含密码 / 令牌（I-2）；operator_user_id 可 null、operator_username
 *   为快照，账号停用后仍可解析（I-4/A11）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { SortOrder } from "./clusters.ts";

/** 审计动作（Contract §2.1：CREATE|UPDATE|DELETE|RESTORE，§22）。 */
export type AuditAction = "CREATE" | "UPDATE" | "DELETE" | "RESTORE";

/**
 * object_type 取值集合（Contract §2.1：8 类资源对象 + user）。
 * §6：值集合属 API 契约枚举（audit_logs.object_type 为 varchar(64) 无枚举
 * CHECK，DB-D167），登记 "user" 无需 Schema 变更。
 */
export type AuditObjectType =
  | "cluster"
  | "resource"
  | "interface"
  | "network"
  | "ip_pool"
  | "ip_address"
  | "service"
  | "service_endpoint"
  | "user";

/**
 * AuditRow（Contract §2.2）。
 * operator_user_id 可 null（如引导 / 系统写入）；before_data/after_data 为
 * 变更前后快照（JSON object，可 null）；不含密码 / 令牌（I-2）。
 */
export interface AuditRow {
  id: string;
  action: AuditAction;
  object_type: AuditObjectType;
  object_id: string;
  operator_user_id: string | null;
  operator_username: string;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  created_at: string;
}

/** 列表响应（Contract §2.2：{items,page,page_size,total}；空结果 200 total=0）。 */
export interface AuditListResponse {
  items: AuditRow[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /audit 查询参数（省略项不发，由服务端默认值生效，Contract §2.1）。 */
export interface ListAuditQuery {
  /** operator_username 精确匹配（服务端 trim+小写归一；trim 空或 >64 → 422）。 */
  operator?: string;
  object_type?: AuditObjectType;
  /** UUID；须与 object_type 同现（单独提供 → 422；非 UUID → 422）。 */
  object_id?: string;
  action?: AuditAction;
  /** 闭区间下界（ISO-8601 UTC）。 */
  created_from?: string;
  /** 闭区间上界（ISO-8601 UTC）；from>to → 422。 */
  created_to?: string;
  page?: number;
  page_size?: number;
  /** 仅 created_at（Contract §2.1；其它值服务端 422）。 */
  sort?: "created_at";
  order?: SortOrder;
}

/** 完整审计查询：GET /api/v1/audit（AUDIT_READ，仅 ADMIN）。只读、无副作用。 */
export function listAudit(query: ListAuditQuery = {}): Promise<AuditListResponse> {
  const search = new URLSearchParams();
  if (query.operator !== undefined && query.operator !== "") {
    search.set("operator", query.operator);
  }
  if (query.object_type !== undefined) {
    search.set("object_type", query.object_type);
  }
  if (query.object_id !== undefined && query.object_id !== "") {
    search.set("object_id", query.object_id);
  }
  if (query.action !== undefined) {
    search.set("action", query.action);
  }
  if (query.created_from !== undefined && query.created_from !== "") {
    search.set("created_from", query.created_from);
  }
  if (query.created_to !== undefined && query.created_to !== "") {
    search.set("created_to", query.created_to);
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
  return request<AuditListResponse>(`/audit${queryString ? `?${queryString}` : ""}`);
}

/**
 * 面向页面的查询错误描述（Contract §2.3；401→403→422→200）：
 * - 401 AUTH_REQUIRED：会话无效（client 已同时触发全局 401 处理器回登录页）；
 * - 403 FORBIDDEN：无 AUDIT_READ（前端隐藏导航不替代服务端鉴权）；
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（键为查询参数名，可经
 *   components/auditQueryForm.ts 的 auditQueryFieldFromPath 映射回表单键）；
 * - 500 / 网络层错误：兑底文案，不伪装成空列表。
 */
export interface AuditQueryError {
  message: string;
  code: string | null;
  /** 字段级错误（422 VALIDATION_ERROR details.fields）。 */
  fields: Record<string, string>;
}

/** 把查询错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeAuditQueryError(error: unknown): AuditQueryError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return { message: "无法连接服务器，请稍后重试", code: null, fields: {} };
  }

  const result: AuditQueryError = {
    message: displayError(error),
    code: error.code,
    fields: {},
  };

  if (error.status === 401) {
    result.message = "未认证或会话已过期（AUTH_REQUIRED）；请重新登录后再查询。";
  } else if (error.status === 403) {
    result.message =
      "没有权限查询完整审计（需 AUDIT_READ 权限，服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
    result.message = "查询参数校验失败（VALIDATION_ERROR）；请修正过滤条件后重试。";
  }
  return result;
}
