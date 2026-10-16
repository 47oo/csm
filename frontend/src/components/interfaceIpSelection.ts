/**
 * 接口侧选择并绑定 IP 的纯逻辑（F019；复用 Contract：docs/api/F010.md v1
 * §4/§6.1/§6.5，不新增端点 / 参数；docs/features/F019/architecture.md
 * DR-332–DR-345）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、./ipAddressForm.ts；
 * InterfaceIpBindingPanel.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * - 候选口径（DR-332/T54）：GET /api/v1/ip-addresses 固定 cluster_id=接口所属
 *   Resource 的 Cluster、bound=false（未绑定任何接口）、deleted=exclude（未
 *   删除）；可选 q（address 大小写不敏感子串）/ page / page_size≤100；
 *   sort=address&order=asc。跨 Cluster / 已绑定 / 已删 IP 不进入候选
 *   （服务端过滤，前端不复制过滤规则）。
 * - 跨页多选（DR-333）：选择身份 = IPAddress id，会话内跨页 / 翻页 / 改搜索
 *   保留快照 {id,address,version}；同 id 重复加入刷新快照。
 * - 逐条绑定（DR-334/T55）：每项单独 PATCH {interface,version}（F010 §6.5
 *   exclude_unset；不含 description 等其它键），按 address 数值升序串行提交，
 *   单项失败不中止其余；每项恰一次调用、不静默重试；部分成功不折叠为整体
 *   成功（F010 §7 无静默重试）。
 * - 已绑定展示（DR-335/T54）：GET /api/v1/ip-addresses?interface_id=<id>&
 *   deleted=exclude&sort=address&order=asc&page_size=100（单次有界加载，
 *   按需触发、按接口缓存）。
 * - total 边界（T56）：total>items 显式提示截断（不静默截断）；total==items
 *   完整；total==0 空态。
 * - 权限 / 软删门控（DR-337/DR-338/T57）：绑定入口仅 WRITE 且接口未软删时
 *   渲染；前端隐藏不替代服务端鉴权（VIEWER 直接调用仍被 403 拒绝，
 *   F010 §1.3；软删接口 PATCH 引用关系被 422 field="interface" 拒绝）。
 * - 失败原因不在本模块归一：逐项结果携带原始错误，呈现层复用
 *   describeIpAddressActionError（F010 §1.2 语义），避免复制 409/422 映射。
 */
import type { IpAddress, ListIpAddressesQuery } from "../api/ipAddresses.ts";

/** 候选 / 已选 IP 的最小快照（绑定提交仅需 id / address / version）。 */
export interface InterfaceIpCandidate {
  id: string;
  address: string;
  /** 选择时点的乐观锁版本（并发后到者 409 VERSION_CONFLICT，F010 §7）。 */
  version: number;
}

/** 跨页多选集合：以 IPAddress id 为键（DR-333；切页 / 改搜索不清空）。 */
export type InterfaceIpSelection = ReadonlyMap<string, InterfaceIpCandidate>;

/** 空选择集合。 */
export function emptyInterfaceIpSelection(): InterfaceIpSelection {
  return new Map();
}

/** 从列表响应行提取候选快照（仅 id/address/version，其余字段不参与绑定）。 */
export function interfaceIpCandidateFromIpAddress(ipAddress: IpAddress): InterfaceIpCandidate {
  return {
    id: ipAddress.id,
    address: ipAddress.address,
    version: ipAddress.version,
  };
}

/** 加入候选（同 id 重复加入时刷新快照，如 version 变化后重选），返回新集合。 */
export function addInterfaceIpCandidate(
  selection: InterfaceIpSelection,
  candidate: InterfaceIpCandidate,
): InterfaceIpSelection {
  const next = new Map(selection);
  next.set(candidate.id, candidate);
  return next;
}

/** 移除候选（不存在时原样返回同一引用），返回新集合。 */
export function removeInterfaceIpCandidate(
  selection: InterfaceIpSelection,
  id: string,
): InterfaceIpSelection {
  if (!selection.has(id)) {
    return selection;
  }
  const next = new Map(selection);
  next.delete(id);
  return next;
}

/** 点分四段 IPv4 → 32 位无符号整数（不匹配返回 null；不做归一化 / 改写）。 */
function ipv4ToNumber(address: string): number | null {
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(address.trim());
  if (match === null) {
    return null;
  }
  let value = 0;
  for (const part of match.slice(1)) {
    const octet = Number(part);
    if (octet > 255) {
      return null;
    }
    value = value * 256 + octet;
  }
  return value;
}

/** address 数值升序比较（镜像服务端 sort=address 语义；无法解析时回退字符串序）。 */
function compareByAddressAscending(left: string, right: string): number {
  const leftValue = ipv4ToNumber(left);
  const rightValue = ipv4ToNumber(right);
  if (leftValue !== null && rightValue !== null) {
    return leftValue - rightValue;
  }
  return left < right ? -1 : left > right ? 1 : 0;
}

/** 已选候选列表（address 数值升序 = 提交顺序，架构 §7.1-9）。 */
export function interfaceIpSelectionCandidates(
  selection: InterfaceIpSelection,
): InterfaceIpCandidate[] {
  return [...selection.values()].sort((left, right) =>
    compareByAddressAscending(left.address, right.address),
  );
}

/**
 * 候选列表查询参数（DR-332）：恰含 cluster_id / bound=false / deleted=exclude /
 * q（trim；空串由 listIpAddresses 视为未提供不发）/ page / page_size /
 * sort=address / order=asc，不夹带其它过滤项。
 */
export function buildInterfaceIpCandidateQuery(
  clusterId: string,
  query: { q?: string; page?: number; pageSize?: number } = {},
): ListIpAddressesQuery {
  return {
    cluster_id: clusterId,
    bound: false,
    deleted: "exclude",
    q: (query.q ?? "").trim(),
    page: query.page ?? 1,
    page_size: query.pageSize ?? 20,
    sort: "address",
    order: "asc",
  };
}

/**
 * 接口已绑定 IP 查询参数（DR-335）：interface_id 精确过滤 + 未删口径 +
 * address 升序，单次有界加载（page=1、page_size=100，分页上限，Contract §4）。
 */
export function buildInterfaceBoundIpsQuery(interfaceId: string): ListIpAddressesQuery {
  return {
    interface_id: interfaceId,
    deleted: "exclude",
    sort: "address",
    order: "asc",
    page: 1,
    page_size: 100,
  };
}

/** 列表 total 边界（T56）：truncated=total>items（显式提示截断）；complete=恰完整；empty=空。 */
export type InterfaceIpTotalBoundary = "empty" | "complete" | "truncated";

export function interfaceIpTotalBoundary(total: number, itemCount: number): InterfaceIpTotalBoundary {
  if (total <= 0 || itemCount <= 0) {
    return "empty";
  }
  return total > itemCount ? "truncated" : "complete";
}

/** 单项绑定请求（F010 §6.5 PATCH 载荷本地镜像：恰含 version + interface）。 */
export interface InterfaceIpBindingRequest extends InterfaceIpCandidate {
  /** 目标接口 UUID（载荷 interface 字段；服务端重检存在 / 未软删 / 同 Cluster）。 */
  interface: string;
}

/** 逐项提交结果：单项 ok 与原始错误（成功为 null）；呈现层经 describeIpAddressActionError 归一。 */
export interface InterfaceIpBindingOutcome {
  id: string;
  address: string;
  ok: boolean;
  error: unknown;
}

/** 构造逐条绑定请求（已选快照 + 目标接口 → PATCH 载荷，address 数值升序串行）。 */
export function buildInterfaceIpBindingRequests(
  selection: InterfaceIpSelection,
  interfaceId: string,
): InterfaceIpBindingRequest[] {
  return interfaceIpSelectionCandidates(selection).map((candidate) => ({
    ...candidate,
    interface: interfaceId,
  }));
}

/**
 * 串行逐条提交（DR-334/T55）：按传入顺序逐项 await；单项失败不中止其余；
 * 每项恰一次调用、不重试；全部完成后返回逐项结果（部分成功由汇总区分，
 * 不折叠为整体成功）。submit 由调用方提供（页面 = updateIpAddress）。
 */
export async function submitInterfaceIpBindingRequests(
  requests: InterfaceIpBindingRequest[],
  submit: (request: InterfaceIpBindingRequest) => Promise<unknown>,
): Promise<InterfaceIpBindingOutcome[]> {
  const outcomes: InterfaceIpBindingOutcome[] = [];
  for (const request of requests) {
    try {
      await submit(request);
      outcomes.push({ id: request.id, address: request.address, ok: true, error: null });
    } catch (error) {
      outcomes.push({ id: request.id, address: request.address, ok: false, error });
    }
  }
  return outcomes;
}

/** 部分成功汇总（T55/AC3）：全成功才 allSucceeded=true；空提交不误报整体成功。 */
export interface InterfaceIpBindingSummary {
  total: number;
  succeeded: number;
  failed: number;
  allSucceeded: boolean;
}

export function summarizeInterfaceIpBindingOutcomes(
  outcomes: InterfaceIpBindingOutcome[],
): InterfaceIpBindingSummary {
  const succeeded = outcomes.filter((outcome) => outcome.ok).length;
  const failed = outcomes.length - succeeded;
  return {
    total: outcomes.length,
    succeeded,
    failed,
    allSucceeded: outcomes.length > 0 && failed === 0,
  };
}

/**
 * 绑定入口门控（DR-337/DR-338/T57/AC5）：仅具备 WRITE 且接口未软删时渲染
 * 「绑定 IP」入口；VIEWER 不显示（直接调用仍被服务端 403 拒绝，服务端权威）。
 */
export function canOpenInterfaceIpBinding(
  canWrite: boolean,
  interfaceDeletedAt: string | null,
): boolean {
  return canWrite && interfaceDeletedAt === null;
}
