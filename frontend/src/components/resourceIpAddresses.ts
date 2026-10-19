/**
 * Resource 详情 IP Addresses 区域的纯逻辑（F022；复用 Contract：docs/api/
 * F007.md v1 §4/§6.1 与 docs/api/F010.md v1 §3/§4/§5/§6.1，不新增端点 /
 * 参数；docs/features/F022/architecture.md DR-382–DR-400，Contract
 * NOT_REQUIRED）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、
 * ./interfaceIpSelection.ts；ResourceIpAddressesPanel.tsx 含 JSX 无法被
 * Node 加载，故本模块独立成文件）。
 *
 * - 接口列表查询（DR-382）：GET /api/v1/interfaces 固定 resource_id=资源 id、
 *   deleted=exclude（未删接口；绑定到已软删 Interface 的 IP 因只查未删接口
 *   自然不出现，DR-391）、sort=name&order=asc、page 递增逐页取全、
 *   page_size=100（分页上限，F007 §4）；安全上限 RESOURCE_INTERFACES_MAX_PAGES
 *   页，超限显式提示截断、不静默遗漏（DR-383）。
 * - 逐接口已绑定 IP 查询（DR-382）：复用 F019 buildInterfaceBoundIpsQuery
 *   （interface_id + deleted=exclude + sort=address + order=asc + page=1 +
 *   page_size=100，F010 §4/§6.1），不另造口径、不修改 F019 模块（DR-400）。
 * - 合并与排序（DR-384/DR-385）：行 = 未删接口 × 该接口未删 IP；总排序
 *   interface.name ASC（字符串码序、区分大小写，同 F007 sort=name）→
 *   IP 地址数值 ASC（本地实现，不改 F019）→ id ASC 兜底（确定性全序）；
 *   已软删接口不产生行（防御，服务端 exclude 已保证）。
 * - 边界判定（DR-388）：单接口 total>items 复用 F019 interfaceIpTotalBoundary
 *   判 truncated，聚合任一 truncated 即产生显式提示条目、不静默截断；
 *   接口列表 total>已加载数（达安全上限仍未覆盖）即 truncated。
 * - 部分失败汇总（DR-389）：全成功 / 部分失败 / 全失败三态计数，不折叠为
 *   整体成功；呈现层据此区分警告（保留已加载行）与整体 Error（可重试）。
 * - 展示标签（DR-386）：ip_pool=null → 「池外（手动）」、description=null →
 *   「—」，不以空串代替。
 */
import type { ListInterfacesQuery } from "../api/interfaces.ts";
import type { IpAddress, ListIpAddressesQuery } from "../api/ipAddresses.ts";
import {
  buildInterfaceBoundIpsQuery,
  interfaceIpTotalBoundary,
} from "./interfaceIpSelection.ts";

/** 接口列表单页大小（F007 §4 分页上限 100，DR-382）。 */
export const RESOURCE_INTERFACES_PAGE_SIZE = 100;

/** 接口列表逐页取全的安全上限（DR-383）：超限显式提示截断，不静默遗漏。 */
export const RESOURCE_INTERFACES_MAX_PAGES = 50;

/** 逐接口 IP 请求的有界并发上限（DR-398）。 */
export const RESOURCE_IP_LOAD_CONCURRENCY = 6;

/** ip_pool=null（池外手动分配）的展示标签（DR-386；不以空串代替）。 */
export const RESOURCE_IP_POOL_NULL_LABEL = "池外（手动）";

/** description=null（未设置）的展示标签（DR-386；不以空串代替）。 */
export const RESOURCE_IP_DESCRIPTION_NULL_LABEL = "—";

/**
 * 接口列表查询（DR-382）：恰含 resource_id / deleted=exclude / sort=name /
 * order=asc / page / page_size=100，不夹带其它过滤项（F007 §4/§6.1）。
 */
export function buildResourceInterfacesQuery(resourceId: string, page = 1): ListInterfacesQuery {
  return {
    resource_id: resourceId,
    deleted: "exclude",
    sort: "name",
    order: "asc",
    page,
    page_size: RESOURCE_INTERFACES_PAGE_SIZE,
  };
}

/** 逐接口已绑定 IP 查询（DR-382）：复用 F019 buildInterfaceBoundIpsQuery，不另造口径。 */
export function buildResourceInterfaceIpsQuery(interfaceId: string): ListIpAddressesQuery {
  return buildInterfaceBoundIpsQuery(interfaceId);
}

/** 合并所需的最小接口形状（结构性子集；完整 Interface 响应对象直接兼容）。 */
export interface ResourceIpInterfaceRef {
  id: string;
  name: string;
  deleted_at: string | null;
}

/** 合并后的展示行：接口归属 + 原始 IP 行（字段按 DR-386 呈现）。 */
export interface ResourceIpRow {
  interfaceId: string;
  interfaceName: string;
  ip: IpAddress;
}

/** 点分四段 IPv4 → 32 位无符号整数（不匹配返回 null；本地实现，不改 F019，DR-400）。 */
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

/** IP 地址数值升序比较（镜像服务端 sort=address 数值语义；无法解析时回退字符串码序）。 */
export function compareResourceIpAddressesAscending(left: string, right: string): number {
  const leftValue = ipv4ToNumber(left);
  const rightValue = ipv4ToNumber(right);
  if (leftValue !== null && rightValue !== null) {
    return leftValue - rightValue;
  }
  return left < right ? -1 : left > right ? 1 : 0;
}

/**
 * 总排序比较器（DR-385，确定性全序）：interface.name 码序（区分大小写，
 * 同 F007 sort=name）→ IP 地址数值 ASC → id ASC 兜底。
 */
export function compareResourceIpRows(left: ResourceIpRow, right: ResourceIpRow): number {
  if (left.interfaceName !== right.interfaceName) {
    return left.interfaceName < right.interfaceName ? -1 : 1;
  }
  const byAddress = compareResourceIpAddressesAscending(left.ip.address, right.ip.address);
  if (byAddress !== 0) {
    return byAddress;
  }
  if (left.ip.id !== right.ip.id) {
    return left.ip.id < right.ip.id ? -1 : 1;
  }
  return 0;
}

/**
 * 合并各接口已绑定 IP 为展示行并按总排序（DR-384/DR-385，M3）：
 * - 行数 = Σ 各未删接口的 IP 数；归属取接口列表（逐接口查询展开）；
 * - 已软删接口不产生行（防御，服务端 deleted=exclude 已保证，DR-391）；
 * - 加载失败的接口（无加载结果）不产生行，由部分失败警告显式提示（DR-389）。
 */
export function mergeResourceIpRows(
  interfaces: readonly ResourceIpInterfaceRef[],
  ipsByInterfaceId: ReadonlyMap<string, readonly IpAddress[]>,
): ResourceIpRow[] {
  const rows: ResourceIpRow[] = [];
  for (const iface of interfaces) {
    if (iface.deleted_at !== null) {
      continue;
    }
    const ips = ipsByInterfaceId.get(iface.id);
    if (ips === undefined) {
      continue;
    }
    for (const ip of ips) {
      rows.push({ interfaceId: iface.id, interfaceName: iface.name, ip });
    }
  }
  rows.sort(compareResourceIpRows);
  return rows;
}

/** 单接口 IP 截断提示条目（DR-388：total>items 显式提示总数，不静默截断）。 */
export interface ResourceIpTruncation {
  interfaceName: string;
  total: number;
  shown: number;
}

/**
 * 逐接口 total 边界汇总（DR-388/M5）：任一接口 truncated（total>items，复用
 * F019 interfaceIpTotalBoundary 判定）即产生一条提示条目；全 complete /
 * empty 不产生。聚合口径：任一 truncated 即整体 truncated。
 */
export function collectResourceIpTruncations(
  loads: readonly { interfaceName: string; total: number; itemCount: number }[],
): ResourceIpTruncation[] {
  const truncations: ResourceIpTruncation[] = [];
  for (const load of loads) {
    if (interfaceIpTotalBoundary(load.total, load.itemCount) === "truncated") {
      truncations.push({
        interfaceName: load.interfaceName,
        total: load.total,
        shown: load.itemCount,
      });
    }
  }
  return truncations;
}

/**
 * 接口列表逐页取全边界（DR-383）：total > 已加载数（达安全上限仍未覆盖）
 * → truncated（呈现层显式提示总数，不静默截断）；否则 complete。
 */
export function resourceInterfacesListBoundary(
  total: number,
  loadedCount: number,
): "complete" | "truncated" {
  return total > loadedCount ? "truncated" : "complete";
}

/** 逐接口加载失败的呈现条目（message 为已归一的错误文案，DR-389）。 */
export interface ResourceIpInterfaceFailure {
  interfaceId: string;
  interfaceName: string;
  message: string;
}

/** 部分失败汇总（DR-389/M6）：全成功 / 部分失败 / 全失败三态计数，不折叠。 */
export interface ResourceIpInterfaceLoadSummary {
  interfaceCount: number;
  succeeded: number;
  failed: number;
  /** 全失败（呈现层整体 Error，可重试重取全部）；无接口时不误报。 */
  allFailed: boolean;
  anyFailed: boolean;
}

export function summarizeResourceIpInterfaceLoads(
  interfaceCount: number,
  failures: readonly ResourceIpInterfaceFailure[],
): ResourceIpInterfaceLoadSummary {
  const failed = failures.length;
  return {
    interfaceCount,
    succeeded: interfaceCount - failed,
    failed,
    allFailed: interfaceCount > 0 && failed === interfaceCount,
    anyFailed: failed > 0,
  };
}
