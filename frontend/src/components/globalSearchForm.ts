/**
 * 全局搜索表单值 ↔ API 查询映射（F013，Contract：docs/api/F013.md v1 §2）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、
 * ./serviceEndpointForm.ts；GlobalSearch.tsx 含 JSX 无法被 Node 加载，
 * 故本模块独立成文件）。
 *
 * 语义的本地镜像（服务端为最终权威，422 字段错误按查询参数名呈现，
 * Contract §1.2）：
 * - q（§2.1/§2.5/DR-177）：trim 后非空、长度 1–255（Unicode code point）；
 *   空 / 纯空白 → 不发请求（I-13 定稿：服务端 422 field="q"，前端空输入
 *   直接本地提示，不发起调用）；>255 → 本地错误（服务端同样 422 field="q"）。
 * - type（§2.1）：∈ {resource, cluster, ip_address, service}，空串 = 全部
 *   （省略参数）。类型下拉为 input + datalist（允许输入与模糊筛选，§17），
 *   自由输入的非法值本地报错（不静默归一化 / 不改写用户输入；服务端同样
 *   422 field="type"）。
 * - deleted（§4）：exclude 默认 | include | only；include/only 需
 *   VIEW_DELETED，否则 403（由服务端承载，页面按权限显示开关）。
 * - page ≥ 1、page_size 1–100：由分页控件提供（下拉恒合法），
 *   buildSearchQuery 原样序列化；服务端对越界 / 非整数 422。
 * - 422 点路径映射（Contract §1.2）：field 为查询参数名
 *   （q/type/deleted/page/page_size），经 searchFormFieldFromPath 归一；
 *   未知路径返回 null（由页面在通用错误区呈现，不静默丢弃 422）。
 * - highlightSegments：对命中展示值做 ASCII 大小写不敏感的子串定位
 *   （与 hostname/service name 归一化口径一致，§2.6；中文与内部空格原样），
 *   供结果列表高亮；模糊（trigram）命中但非子串时返回整段未命中（不伪造
 *   高亮位置）。
 */
import type { DeletedMode, SearchObjectType, SearchQuery } from "../api/search.ts";

/** 类型过滤的表单值：空串 = 全部（Contract §2.1 缺省语义）。 */
export type GlobalSearchTypeFilter = "" | SearchObjectType;

/** 类型下拉的全部合法值（datalist 选项与本地校验共用）。 */
export const GLOBAL_SEARCH_TYPE_OPTIONS: { value: GlobalSearchTypeFilter; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "resource", label: "resource（资源）" },
  { value: "cluster", label: "cluster（集群）" },
  { value: "ip_address", label: "ip_address（IP 地址）" },
  { value: "service", label: "service（服务）" },
];

/** q 的长度上限（trim 后，Unicode code point；Contract §2.5/V9）。 */
export const SEARCH_Q_MAX_LENGTH = 255;

/** 服务端 422 查询参数名全集（Contract §1.2：field 使用查询参数名）。 */
export type SearchServerFieldKey = "q" | "type" | "deleted" | "page" | "page_size";

const SEARCH_FIELD_KEYS: readonly SearchServerFieldKey[] = [
  "q",
  "type",
  "deleted",
  "page",
  "page_size",
];

/** 全局搜索表单原始值（q / type 为文本输入；page 由分页控件管理）。 */
export interface GlobalSearchFormValues {
  q: string;
  type: GlobalSearchTypeFilter;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
}

/** 本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type GlobalSearchFormErrors = Partial<Record<"q" | "type", string>>;

/** 解析后的全局搜索值（q 已 trim；type 空串 = 全部）。 */
export interface GlobalSearchParsedValues {
  q: string;
  type: GlobalSearchTypeFilter;
}

/** Unicode code point 计数（Contract §2.5 按 code point 计长）。 */
function codePointLength(text: string): number {
  return Array.from(text).length;
}

/** ASCII 大写 → 小写折叠（仅 A–Z，与 D01 §5.3 归一化同口径；中文等原样）。 */
function asciiLower(text: string): string {
  let result = "";
  for (const ch of text) {
    const code = ch.codePointAt(0) ?? 0;
    result += code >= 0x41 && code <= 0x5a ? String.fromCodePoint(code + 0x20) : ch;
  }
  return result;
}

/** 服务端 422 点路径 → 表单字段键（顶层路径直通；未知路径返回 null 不强行映射）。 */
export function searchFormFieldFromPath(path: string): SearchServerFieldKey | null {
  const top = path.split(".")[0];
  return (SEARCH_FIELD_KEYS as readonly string[]).includes(top)
    ? (top as SearchServerFieldKey)
    : null;
}

/** 空白搜索表单值。 */
export function emptyGlobalSearchFormValues(): GlobalSearchFormValues {
  return {
    q: "",
    type: "",
    deleted: "exclude",
    page: 1,
    pageSize: 20,
  };
}

/**
 * 解析搜索表单值（本地快速反馈；服务端 422 仍按查询参数名呈现）：
 * - q：trim → 非空 → ≤255 code point（含 255；超长报错）；
 * - type：仅接受空串或四个规范枚举值（datalist 恒合法；防御自由输入，
 *   不做大小写归一化，不静默改写）。
 * 注意：本函数对空 q 返回 ok:false（errors.q），供提交入口提示「不发请求」；
 * 是否发起请求由 buildSearchQuery 决定。
 */
export function parseGlobalSearchFormValues(
  values: Pick<GlobalSearchFormValues, "q" | "type">,
): { ok: true; fields: GlobalSearchParsedValues } | { ok: false; errors: GlobalSearchFormErrors } {
  const errors: GlobalSearchFormErrors = {};

  const q = values.q.trim();
  if (q === "") {
    errors.q = "请输入搜索关键字（空 / 纯空白查询不会执行，服务端同样拒绝空 q）";
  } else if (codePointLength(q) > SEARCH_Q_MAX_LENGTH) {
    errors.q = `关键字过长：trim 后不得超过 ${SEARCH_Q_MAX_LENGTH}（Unicode code point）`;
  }

  const validTypes = GLOBAL_SEARCH_TYPE_OPTIONS.map((option) => option.value);
  if (!validTypes.includes(values.type)) {
    errors.type =
      "type 必须为 resource / cluster / ip_address / service 之一，或留空表示全部（不接受其它自由输入值）";
  }

  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields: { q, type: values.type } };
}

/**
 * 构造 API 查询（Contract §2.1）：q trim 后为空 → 返回 null（不发请求，
 * I-13/DR-177——空查询不返回全量，前端直接本地提示）；否则携带 trim 后的 q，
 * type 非空才携带（空 = 全部，省略参数），deleted / page / page_size 原样
 * 序列化（服务端默认 exclude / 1 / 20）。
 */
export function buildSearchQuery(values: GlobalSearchFormValues): SearchQuery | null {
  const q = values.q.trim();
  if (q === "") {
    return null;
  }
  const query: SearchQuery = {
    q,
    deleted: values.deleted,
    page: values.page,
    page_size: values.pageSize,
  };
  if (values.type !== "") {
    query.type = values.type;
  }
  return query;
}

/** 高亮分段：hit 段为与查询串 ASCII 大小写不敏感匹配的子串。 */
export interface HighlightSegment {
  text: string;
  hit: boolean;
}

/**
 * 对展示文本按查询串定位高亮分段：q 经 ASCII 小写折叠后在文本（同样折叠）
 * 中查找首个子串出现；命中 → 前缀 / 命中 / 后缀 三段；未命中（模糊
 * trigram 命中但非连续子串）或 q 为空 → 整段未命中（不伪造高亮位置）。
 */
export function highlightSegments(text: string, rawQuery: string): HighlightSegment[] {
  const query = asciiLower(rawQuery.trim());
  if (query === "") {
    return [{ text, hit: false }];
  }
  const lowered = asciiLower(text);
  const index = lowered.indexOf(query);
  if (index < 0) {
    return [{ text, hit: false }];
  }
  return [
    { text: text.slice(0, index), hit: false },
    { text: text.slice(index, index + query.length), hit: true },
    { text: text.slice(index + query.length), hit: false },
  ].filter((segment) => segment.text !== "");
}
