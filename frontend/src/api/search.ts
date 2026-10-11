/**
 * Global Search API（F013，Contract：docs/api/F013.md v1，READY）。
 *
 * 端点（Contract §2）：
 * - GET /search  跨对象全局搜索（READ；VIEWER / EDITOR / ADMIN 全角色）
 *
 * 注意：
 * - 本端点与各域列表的 `q` 是不同接口（Contract §1.4/DR-185）：本端点为
 *   跨对象全局入口（pg_trgm + 归一化键），各域列表 `q` 保持 ILIKE 子串
 *   语义不变，前端不混用。
 * - `q` 必填：trim 后非空、长度 1–255（Unicode code point）；空 / 纯空白 /
 *   超长 → 422 field="q"（服务端权威，Contract §2.5/DR-177）。前端对空输入
 *   不发请求（I-13），非空输入的本地预检见 components/globalSearchForm.ts。
 * - `type ∈ {resource, cluster, ip_address, service}`（缺省全部）；
 *   `deleted ∈ {exclude, include, only}` 默认 exclude，include/only 需
 *   VIEW_DELETED（ADMIN）否则 403 FORBIDDEN{reason:"permission"}（§4）。
 * - 响应为 typed 行（I-11/DR-174 定稿）：resource 行仅由 hostname 命中产生；
 *   ip_address / service 行各自嵌入其 resource（未绑定 IP 的 resource=null，
 *   不伪造归属 A5/I-6）；同键 (object_type,id) 去重；排序固定
 *   similarity DESC → object_type → id ASC（§2.3，非参数化，无 sort/order）。
 * - 只读：无写入口、无 Audit、幂等（§5/A21）；任何失败不自动重试。
 * - 401 / 403（含未知 reason 的兜底呈现）/ 422 / 500 / 网络层错误的页面
 *   呈现语义见 describeSearchError。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, envelopeFieldErrors, isApiError, request } from "./client.ts";
import type { DeletedMode } from "./clusters.ts";

/** 软删可见性与 F003 同一语义，复用同一类型定义（Contract §4）。 */
export type { DeletedMode } from "./clusters.ts";

/** 搜索对象类型（Contract §2.2：判别字段 object_type）。 */
export type SearchObjectType = "resource" | "cluster" | "ip_address" | "service";

/** 命中字段（Contract §2.2：hostname | address | code | name）。 */
export type SearchMatchedField = "hostname" | "address" | "code" | "name";

/** SearchItem 嵌套的 Resource（Contract §2.2：承载/命中 Resource；未命中为 null）。 */
export interface SearchResourceRef {
  id: string;
  hostname: string;
  resource_type: "BARE_METAL" | "VIRTUAL_MACHINE";
  role: string;
  status: string;
  cluster: { id: string; code: string; name: string };
}

/** SearchItem 嵌套的 Cluster（Contract §2.2）。 */
export interface SearchClusterRef {
  id: string;
  code: string;
  name: string;
  status: "ACTIVE" | "INACTIVE";
}

/** SearchItem 嵌套的 IPAddress（Contract §2.2：interface 未绑定为 null）。 */
export interface SearchIpAddressRef {
  id: string;
  /** 点分十进制 IPv4（裸地址，精确匹配命中，Contract §2.4）。 */
  address: string;
  network: { id: string; name: string };
  interface: { id: string; name: string } | null;
}

/** SearchItem 嵌套的 Service（Contract §2.2）。 */
export interface SearchServiceRef {
  id: string;
  name: string;
  status: "RUNNING" | "STOPPED" | "UNKNOWN";
}

/**
 * 搜索结果行（Contract §2.2，typed 行）：字段集不因查询变化（便于前端判别），
 * 除 object_type 对应的嵌套对象外其余为 null；id 为稳定 UUID（跳转依据，I-9）。
 */
export interface SearchItem {
  object_type: SearchObjectType;
  id: string;
  matched_field: SearchMatchedField;
  /** 命中展示值（原值，不改写，Contract §2.2）。 */
  matched_value: string;
  resource: SearchResourceRef | null;
  cluster: SearchClusterRef | null;
  ip_address: SearchIpAddressRef | null;
  service: SearchServiceRef | null;
}

/** 搜索响应（Contract §2.2：{items, page, page_size, total}）。 */
export interface SearchResponse {
  items: SearchItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /search 查询参数（Contract §2.1；q 必填，其余省略由服务端默认生效）。 */
export interface SearchQuery {
  /** 搜索串（整体一个查询串，不做 OR 拆词；归一化按目标列分别进行，§2.6）。 */
  q: string;
  /** 收窄到单一 object_type；省略 = 全部。 */
  type?: SearchObjectType;
  /** 软删可见性；include/only 需 VIEW_DELETED。 */
  deleted?: DeletedMode;
  page?: number;
  page_size?: number;
}

/**
 * 全局搜索：GET /api/v1/search（READ）。
 * 空 q 不应传入（服务端 422 field="q"；前端空输入不发请求，见
 * components/globalSearchForm.ts 的 buildSearchQuery）。空结果返回 200 空列表。
 */
export function search(query: SearchQuery): Promise<SearchResponse> {
  const searchParams = new URLSearchParams();
  // q 必填：始终携带（调用方保证非空；URLSearchParams 负责编码）
  searchParams.set("q", query.q);
  if (query.type !== undefined) {
    searchParams.set("type", query.type);
  }
  if (query.deleted !== undefined) {
    searchParams.set("deleted", query.deleted);
  }
  if (query.page !== undefined) {
    searchParams.set("page", String(query.page));
  }
  if (query.page_size !== undefined) {
    searchParams.set("page_size", String(query.page_size));
  }
  return request<SearchResponse>(`/search?${searchParams.toString()}`);
}

/** 面向页面的搜索加载错误（Contract §1.2：401/403/422/500 + 网络层兜底）。 */
export interface SearchLoadError {
  message: string;
  code: string | null;
  /** 422 VALIDATION_ERROR 的字段级错误（q/type/deleted/page/page_size，§1.2）。 */
  fields: Record<string, string>;
}

/**
 * 把搜索加载错误归类为页面可直接呈现的结构（不抛出、不重试）：
 * - 网络层错误（fetch reject）：固定文案，不伪装成业务结果；
 * - 401：会话缺失（client 全局处理器已同时清登录态回登录页）；
 * - 403：reason="permission"（如无 VIEW_DELETED 却请求 include/only）给明确
 *   文案；未知 reason 原样透出 reason 值，不伪装成已知原因；
 * - 422 VALIDATION_ERROR：details.fields → 字段级错误（供逐字段呈现）；
 * - 其余（含 500 / 非 JSON 信封）：回退信封 message + code，不伪造内容。
 */
export function describeSearchError(error: unknown): SearchLoadError {
  if (!isApiError(error)) {
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      fields: {},
    };
  }

  const result: SearchLoadError = {
    message: displayError(error),
    code: error.code,
    fields: {},
  };
  const details = error.details ?? {};

  if (error.status === 401) {
    result.message = "尚未登录或会话已过期（AUTH_REQUIRED），请重新登录。";
  } else if (error.status === 403) {
    const reason = details["reason"];
    if (reason === "permission") {
      result.message =
        "没有权限执行该搜索（查看已删除对象需 VIEW_DELETED 权限，FORBIDDEN）。";
    } else {
      // 未知 reason：原样透出，不伪装成已知原因（Contract §1.2 未定义其它 reason）
      result.message = `搜索被拒绝（FORBIDDEN${
        typeof reason === "string" && reason !== "" ? `，reason=${reason}` : ""
      }）。`;
    }
  } else if (error.status === 422) {
    result.fields = envelopeFieldErrors(error.details);
    result.message = "搜索参数校验失败（VALIDATION_ERROR）。";
  }
  return result;
}
