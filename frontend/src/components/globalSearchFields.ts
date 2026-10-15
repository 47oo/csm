/**
 * F018 全局搜索字段组合展示 — 纯逻辑模块（无 JSX / React 依赖）。
 *
 * 承载（Contract：docs/api/F013.md v2 §2.9；DR-326 / DR-327 / DR-321）：
 * - 九字段白名单（§17.1：hostname、resource_type、role、status、cluster、
 *   Interface name、Interface interface_type、IP address、Network name；
 *   「网络类型」按 Network 名称解释，需网卡类型时单独选 interface_type）；
 * - 字段偏好 localStorage 读写与失败回退：约定键 `csm.globalSearch.fields.v1`，
 *   JSON 字符串数组，白名单校验（过滤未知字段、去重、按白名单顺序规范化）；
 *   读取键缺失 / JSON 损坏 / 非数组 / 存储不可用或写入失败时**静默回退**
 *   （返回 null / false，不抛错、不阻断搜索、不回退服务端持久化，DR-326）；
 * - 默认组合：无偏好（含空选择）时 = F013 现有 resource 行展示
 *   （hostname + resource_type + role + status + cluster，A12 无回归）；
 * - 「还有 N 条」计算：N = related_total − 展示行数；N ≤ 0 不提示（每台
 *   Resource 关联上限 10 行由服务端截断并返回截断前总数，DR-321/A6）；
 * - related / related_total 安全访问：缺失 / null / 形状不符时回退空集合与
 *   无提示，容忍旧后端（F013 v1 响应无此两键），不伪造数据（F8/B15）；
 * - 选择器作用域：仅 object_type="resource" 的顶层结果行；cluster /
 *   ip_address / service 行展示不变（DR-327，F013 行为）。
 *
 * scripts/smoke-client.mjs 以 Node type stripping 直接加载本模块做机制级
 * 冒烟（同 globalSearchForm.ts；GlobalSearch.tsx 含 JSX 无法被 Node 加载，
 * 故本模块独立成文件）。
 */
import type {
  SearchObjectType,
  SearchResourceRef,
  SearchResourceRelated,
} from "../api/search.ts";

/** 九字段白名单键（§17.1/A11；localStorage 偏好与选择器共用，顺序即展示规范序）。 */
export type GlobalSearchFieldKey =
  | "hostname"
  | "resource_type"
  | "role"
  | "status"
  | "cluster"
  | "interface_name"
  | "interface_type"
  | "ip_address"
  | "network_name";

/** 九字段白名单（固定顺序：四个关联字段在后，决定 resource 行关联展开）。 */
export const GLOBAL_SEARCH_FIELD_KEYS: readonly GlobalSearchFieldKey[] = [
  "hostname",
  "resource_type",
  "role",
  "status",
  "cluster",
  "interface_name",
  "interface_type",
  "ip_address",
  "network_name",
];

/** 字段选择器展示项（label 供界面与可访问名称使用）。 */
export const GLOBAL_SEARCH_FIELD_OPTIONS: readonly {
  value: GlobalSearchFieldKey;
  label: string;
}[] = [
  { value: "hostname", label: "hostname" },
  { value: "resource_type", label: "resource_type（类型）" },
  { value: "role", label: "role（角色）" },
  { value: "status", label: "status（状态）" },
  { value: "cluster", label: "cluster（集群）" },
  { value: "interface_name", label: "Interface name（网卡名）" },
  { value: "interface_type", label: "Interface type（网卡类型）" },
  { value: "ip_address", label: "IP address（IP 地址）" },
  { value: "network_name", label: "Network name（网络名称）" },
];

/** 关联字段子集（决定 resource 行是否展开 related 行，DR-327/DR-320）。 */
const RELATED_FIELD_KEYS: readonly GlobalSearchFieldKey[] = [
  "interface_name",
  "interface_type",
  "ip_address",
  "network_name",
];

/** localStorage 约定键（DR-326：偏好仅浏览器本地；JSON 字符串数组）。 */
export const GLOBAL_SEARCH_FIELDS_STORAGE_KEY = "csm.globalSearch.fields.v1";

/**
 * 默认组合 = F013 现有 resource 行展示（A12）：hostname 主值 +
 * resource_type / role / status / cluster 上下文；不含关联字段（不展开 related）。
 */
export const DEFAULT_GLOBAL_SEARCH_FIELDS: readonly GlobalSearchFieldKey[] = [
  "hostname",
  "resource_type",
  "role",
  "status",
  "cluster",
];

/** localStorage 最小接口（可注入受控实现，供机制级冒烟与测试替身）。 */
export interface GlobalSearchFieldsStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/**
 * 默认存储：浏览器 localStorage；不可用（Node / SSR / 隐私模式）或访问抛错
 * （如禁用 Cookie 的 SecurityError）时返回 null，由调用方静默回退（DR-326）。
 */
function defaultStorage(): GlobalSearchFieldsStorage | null {
  try {
    const candidate: unknown = (globalThis as { localStorage?: unknown }).localStorage;
    if (candidate === null || candidate === undefined) {
      return null;
    }
    const storage = candidate as Partial<GlobalSearchFieldsStorage>;
    if (typeof storage.getItem !== "function" || typeof storage.setItem !== "function") {
      return null;
    }
    return storage as GlobalSearchFieldsStorage;
  } catch {
    return null;
  }
}

/** 是否为白名单字段（九字段之外一律 false，含大小写变体：不归一化用户/存储值）。 */
export function isGlobalSearchFieldKey(value: unknown): value is GlobalSearchFieldKey {
  return (
    typeof value === "string" && (GLOBAL_SEARCH_FIELD_KEYS as readonly string[]).includes(value)
  );
}

/**
 * 解析存储值（JSON 字符串数组）→ 白名单字段：
 * - 键缺失 / 空串 / JSON 损坏 / 非数组 → null（视为无偏好，回退默认组合）；
 * - 合法数组 → 过滤未知字段、去重，并按白名单顺序规范化（偏好是集合，
 *   展示顺序确定）；全未知项时得到 []（空选择，effectiveGlobalSearchFields
 *   仍回退默认组合）。
 * 任何输入都不抛错（DR-326 静默回退）。
 */
export function parseGlobalSearchFieldPreference(
  stored: string | null,
): GlobalSearchFieldKey[] | null {
  if (typeof stored !== "string" || stored === "") {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(stored);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed)) {
    return null;
  }
  const known = parsed.filter(isGlobalSearchFieldKey);
  return GLOBAL_SEARCH_FIELD_KEYS.filter((key) => known.includes(key));
}

/**
 * 生效字段组合（F4/A12）：非空合法选择 → 该组合（白名单顺序规范化）；
 * null（无偏好）/ 空选择 / 全部被过滤 → 默认组合（= F013 现有展示）。
 * 返回新数组，调用方不得原地修改默认常量。
 */
export function effectiveGlobalSearchFields(
  preference: readonly GlobalSearchFieldKey[] | null,
): GlobalSearchFieldKey[] {
  if (preference === null || preference.length === 0) {
    return [...DEFAULT_GLOBAL_SEARCH_FIELDS];
  }
  const effective = GLOBAL_SEARCH_FIELD_KEYS.filter((key) =>
    (preference as readonly string[]).includes(key),
  );
  return effective.length > 0 ? effective : [...DEFAULT_GLOBAL_SEARCH_FIELDS];
}

/**
 * 读取字段偏好（F2）：约定键 → parseGlobalSearchFieldPreference；
 * 存储不可用或读取抛错 → null（静默，不抛错、不阻断搜索，DR-326）。
 */
export function readGlobalSearchFieldPreference(
  storage?: GlobalSearchFieldsStorage | null,
): GlobalSearchFieldKey[] | null {
  const target = storage === undefined ? defaultStorage() : storage;
  if (target === null) {
    return null;
  }
  try {
    return parseGlobalSearchFieldPreference(
      target.getItem(GLOBAL_SEARCH_FIELDS_STORAGE_KEY),
    );
  } catch {
    return null;
  }
}

/**
 * 写入字段偏好（F2/A11）：规范化（过滤未知、去重、白名单顺序）后以 JSON
 * 数组写入约定键；存储不可用或写入抛错（如配额 / 隐私模式）→ 返回 false
 * 静默失败（会话内状态由调用方保持，不回退服务端持久化，DR-326）。
 */
export function writeGlobalSearchFieldPreference(
  fields: readonly GlobalSearchFieldKey[],
  storage?: GlobalSearchFieldsStorage | null,
): boolean {
  const target = storage === undefined ? defaultStorage() : storage;
  if (target === null) {
    return false;
  }
  const normalized = GLOBAL_SEARCH_FIELD_KEYS.filter((key) =>
    (fields as readonly string[]).includes(key),
  );
  try {
    target.setItem(GLOBAL_SEARCH_FIELDS_STORAGE_KEY, JSON.stringify(normalized));
    return true;
  } catch {
    return false;
  }
}

/**
 * 字段选择是否作用于该结果行（DR-327/F6）：仅 object_type="resource" 的
 * 顶层结果行；cluster / ip_address / service 行展示不因字段选择改变。
 */
export function fieldSelectionAppliesTo(objectType: SearchObjectType): boolean {
  return objectType === "resource";
}

/** 是否选择了任一关联字段（决定 resource 行是否展开 related 行）。 */
export function hasRelatedFields(fields: readonly GlobalSearchFieldKey[]): boolean {
  return fields.some((key) => RELATED_FIELD_KEYS.includes(key));
}

/**
 * related 是否可用（F8 容忍）：契约 v2 下 resource 行恒为数组（无关联为 []）；
 * 缺失 / null / 非数组（旧后端 v1 响应或形状不符）→ false，展示层静默省略
 * 关联区块，不伪造「无关联」结论。
 */
export function relatedAvailable(resource: SearchResourceRef | null): boolean {
  return Array.isArray(resource?.related);
}

/** related 行集合（F8 容忍）：非数组 / 缺失 / null → []，不抛错。 */
export function relatedRows(resource: SearchResourceRef | null): SearchResourceRelated[] {
  const related: unknown = resource?.related;
  return Array.isArray(related) ? (related as SearchResourceRelated[]) : [];
}

/** 截断前关联总数（F8 容忍）：非非负整数（含缺失 / null / 非数值）→ null。 */
export function relatedTotal(resource: SearchResourceRef | null): number | null {
  const total: unknown = resource?.related_total;
  return typeof total === "number" && Number.isInteger(total) && total >= 0 ? total : null;
}

/**
 * 「还有 N 条」计算（F5/DR-321/A6）：N = related_total − 展示行数；
 * related 缺失 / 非数组（关联区块不渲染）或总数缺失 / null / 非数值，
 * 或 N ≤ 0（含 ≤10 上限内）→ 0（不提示）。
 * related_total 与顶层分页 total 语义不同，不相加、不混用（B18）。
 */
export function remainingRelatedCount(resource: SearchResourceRef | null): number {
  if (!relatedAvailable(resource)) {
    return 0;
  }
  const total = relatedTotal(resource);
  if (total === null) {
    return 0;
  }
  const displayed = relatedRows(resource).length;
  return Math.max(total - displayed, 0);
}

/**
 * related 行展示视图（F8）：单元格值原样回显（interface_type 不改写，B21）；
 * 行内对象缺失 / 形状不符 → null（组件以未知占位呈现，不伪造值）。
 * key 为行身份（IPAddress id，§4 稳定 ID）；缺失时退化为列表序号。
 */
export interface RelatedRowView {
  key: string;
  interfaceName: string | null;
  interfaceType: string | null;
  ipAddress: string | null;
  networkName: string | null;
}

function cellText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** related 行集合 → 展示视图（组件按生效字段选取单元格）。 */
export function relatedRowViews(resource: SearchResourceRef | null): RelatedRowView[] {
  return relatedRows(resource).map((row, index) => ({
    key: typeof row?.id === "string" ? row.id : String(index),
    interfaceName: cellText(row?.interface?.name),
    interfaceType: cellText(row?.interface?.interface_type),
    ipAddress: cellText(row?.ip_address?.address),
    networkName: cellText(row?.network?.name),
  }));
}
