/**
 * 已删除对象统一查询与恢复路由 API（F015，Contract：docs/api/F015.md v1，READY）。
 *
 * 端点与路由（Contract §3/§5）：
 * - GET /api/v1/deleted    跨 8 类已软删对象只读聚合（VIEW_DELETED，仅 ADMIN；
 *                          仅 deleted_at IS NOT NULL；无 404、无写副作用）
 * - 恢复不新增统一写端点（O-3/DR-216）：前端按 item.object_type 调用各域既有
 *   `POST /api/v1/{object}/{id}/restore?version=N`（RESTORE；§5 路由表），
 *   语义以各域契约为准（I-15：F015 不复制 / 不改变各域恢复规则）。
 *
 * 注意：
 * - DeletedItem（Contract §3.2）：object_type / object_id（稳定 UUID，I-14）/
 *   version（int≥1，供既有 restore ?version= 乐观锁）/ label（cluster=code；
 *   resource=hostname；interface/network/ip_pool/service=name；ip_address=
 *   address；service_endpoint="{protocol}:{port}"，由服务端生成）/ cluster
 *   （object|null，适用时）/ deleted_at。不返回删除操作者（O-7）。
 * - 排序仅 deleted_at（order asc|desc，默认 desc），同刻 object_type 升序、
 *   object_id 升序（§3.1）；object_type 过滤为 8 类（不含 user，§3.1）。
 * - 各域恢复失败 reason 沿用各域契约（unique_conflict / dependency_deleted /
 *   not_deleted / VERSION_CONFLICT，§5）；呈现语义见 describeDeletedActionError。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts）。
 */
import { displayError, isApiError, request } from "./client.ts";
import type { SortOrder } from "./clusters.ts";
import { restoreCluster } from "./clusters.ts";
import { restoreResource } from "./resources.ts";
import { restoreInterface } from "./interfaces.ts";
import { restoreNetwork } from "./networks.ts";
import { restoreIpPool } from "./ipPools.ts";
import { restoreIpAddress } from "./ipAddresses.ts";
import { restoreService } from "./services.ts";
import { restoreServiceEndpoint } from "./serviceEndpoints.ts";

/** 已删聚合的 object_type（Contract §3.1：8 类，不含 user）。 */
export type DeletedObjectType =
  | "cluster"
  | "resource"
  | "interface"
  | "network"
  | "ip_pool"
  | "ip_address"
  | "service"
  | "service_endpoint";

/** DeletedItem 内嵌的 Cluster 引用（Contract §3.2：{id,code,name}；不适用时为 null）。 */
export interface DeletedClusterRef {
  id: string;
  code: string;
  name: string;
}

/** 已删对象条目（Contract §3.2）。 */
export interface DeletedItem {
  object_type: DeletedObjectType;
  object_id: string;
  /** ≥1；供既有各域 restore ?version= 乐观锁使用。 */
  version: number;
  /** 按域口径的展示标识（服务端生成，见模块注释）。 */
  label: string;
  cluster: DeletedClusterRef | null;
  deleted_at: string;
}

/** 列表响应（Contract §3.2：{items,page,page_size,total}）。 */
export interface DeletedListResponse {
  items: DeletedItem[];
  page: number;
  page_size: number;
  total: number;
}

/** GET /deleted 查询参数（省略项不发，由服务端默认值生效，Contract §3.1）。 */
export interface ListDeletedQuery {
  object_type?: DeletedObjectType;
  page?: number;
  page_size?: number;
  /** 仅 deleted_at（Contract §3.1；其它值服务端 422）。 */
  sort?: "deleted_at";
  order?: SortOrder;
}

/** 已删对象统一查询：GET /api/v1/deleted（VIEW_DELETED，仅 ADMIN；只读）。 */
export function listDeleted(query: ListDeletedQuery = {}): Promise<DeletedListResponse> {
  const search = new URLSearchParams();
  if (query.object_type !== undefined) {
    search.set("object_type", query.object_type);
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
  return request<DeletedListResponse>(`/deleted${queryString ? `?${queryString}` : ""}`);
}

/**
 * 面向页面的查询错误描述（Contract §3.4：401/403/422/500，无 404）：
 * - 401：会话无效；403：无 VIEW_DELETED；422：参数校验失败；
 * - 500 / 网络层错误：兑底文案，不伪装成空列表。
 */
export interface DeletedQueryError {
  message: string;
  code: string | null;
}

/** 把已删列表查询错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeDeletedQueryError(error: unknown): DeletedQueryError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return { message: "无法连接服务器，请稍后重试", code: null };
  }

  const result: DeletedQueryError = {
    message: displayError(error),
    code: error.code,
  };

  if (error.status === 401) {
    result.message = "未认证或会话已过期（AUTH_REQUIRED）；请重新登录后再查询。";
  } else if (error.status === 403) {
    result.message =
      "没有权限查看已删除对象（需 VIEW_DELETED 权限，服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.message = "查询参数校验失败（VALIDATION_ERROR）；请修正过滤条件后重试。";
  }
  return result;
}

/**
 * 按 object_type 路由到各域既有恢复端点（Contract §5 路由表；O-3 不新增统一
 * 写端点）。全部为 `POST /api/v1/{object}/{id}/restore?version=N`（RESTORE），
 * 仅恢复当前对象、不级联、重检唯一 / 依赖、失败不覆盖、写 RESTORE Audit 同
 * 事务——语义权威为各域契约（I-15），本函数仅做路由分发。
 *
 * 返回值为各域响应信封（{cluster}/{resource}/… 形状各异），调用方只关心
 * 成功 / 失败与错误描述，故统一为 unknown。
 */
export function restoreDeletedItem(
  objectType: DeletedObjectType,
  objectId: string,
  version: number,
): Promise<unknown> {
  switch (objectType) {
    case "cluster":
      return restoreCluster(objectId, version);
    case "resource":
      return restoreResource(objectId, version);
    case "interface":
      return restoreInterface(objectId, version);
    case "network":
      return restoreNetwork(objectId, version);
    case "ip_pool":
      return restoreIpPool(objectId, version);
    case "ip_address":
      return restoreIpAddress(objectId, version);
    case "service":
      return restoreService(objectId, version);
    case "service_endpoint":
      return restoreServiceEndpoint(objectId, version);
  }
}

/**
 * 面向页面的恢复错误描述（Contract §5/§6；reason 复用各域，F015 不新增）：
 * - 409 VERSION_CONFLICT：versionConflict=true 并携带 current_version；
 *   页面提示刷新列表后重新操作，绝不静默重试 / 覆盖。
 * - 409 CONFLICT：按 details.reason 映射各域通用文案
 *   （unique_conflict = 标识被新对象复用；dependency_deleted = 依赖仍删除 /
 *   缺失；not_deleted = 对象未处于已删状态）；各域特有细节（如字段名、
 *   conflicts 明细）以各域契约为准，本描述呈现 reason 分类文案。
 * - 403：无 RESTORE 权限；404：对象不存在（可能已被处理，请刷新列表）。
 */
export interface DeletedActionError {
  message: string;
  code: string | null;
  /** 409 VERSION_CONFLICT（乐观锁过期，需刷新列表后重试）。 */
  versionConflict: boolean;
  /** 服务器当前版本（VERSION_CONFLICT details.current_version；未知为 null）。 */
  currentVersion: number | null;
}

const CONFLICT_REASON_MESSAGES: Record<string, string> = {
  unique_conflict:
    "恢复失败：该对象的标识（名称 / hostname / code / 地址等，按其类型规则）" +
    "已被新的未删除对象占用，无法恢复；新对象不会被覆盖，原对象保持已删除状态",
  dependency_deleted:
    "恢复失败：该对象依赖的对象（如所属 Resource / Network / Service 等）" +
    "仍处于已删除状态或已不存在，需先恢复依赖对象后再恢复本对象",
  not_deleted: "该对象未处于已删除状态，无需恢复（可能已被恢复，请刷新列表）",
};

/** 把恢复错误归类为页面可直接呈现的结构（不抛出、不重试）。 */
export function describeDeletedActionError(error: unknown): DeletedActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      versionConflict: false,
      currentVersion: null,
    };
  }

  const result: DeletedActionError = {
    message: displayError(error),
    code: error.code,
    versionConflict: false,
    currentVersion: null,
  };
  const details = error.details ?? {};

  if (error.status === 409 && error.code === "VERSION_CONFLICT") {
    result.versionConflict = true;
    const current = details["current_version"];
    if (typeof current === "number") {
      result.currentVersion = current;
    }
    result.message =
      `该对象已被其他人修改（服务器当前版本 ${result.currentVersion ?? "未知"}）。` +
      "请刷新列表获取最新数据后重新操作；系统不会自动重试或覆盖他人修改。";
  } else if (error.status === 409 && error.code === "CONFLICT") {
    const reason = details["reason"];
    if (typeof reason === "string" && reason in CONFLICT_REASON_MESSAGES) {
      result.message = `${CONFLICT_REASON_MESSAGES[reason]}（CONFLICT/${reason}）`;
    } else {
      result.message = `恢复冲突：${error.message}（CONFLICT）`;
    }
  } else if (error.status === 403) {
    result.message = "没有权限恢复对象（需 RESTORE 权限，服务端已拒绝，FORBIDDEN）。";
  } else if (error.status === 404) {
    result.message = "对象不存在（可能已被处理，请刷新列表；NOT_FOUND）。";
  }
  return result;
}
