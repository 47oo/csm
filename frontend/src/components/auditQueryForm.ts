/**
 * Audit 查询表单值 ↔ API 查询参数映射（F015，Contract：docs/api/F015.md v1 §2.1）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts；
 * AuditQueryPanel.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按查询参数名呈现）：
 * - operator：trim → 空 = 未提供（不发参数）；trim 后 >64 code point → 本地
 *   拦截（服务端 422）。发送 trim 后原样值；精确匹配的 trim+小写归一由
 *   服务端执行（前端不折叠展示大小写）。
 * - object_type / action：下拉恒合法；"" = 未提供。
 * - object_id：trim → 空 = 未提供；非空时须为 UUID 且与 object_type 同现
 *   （单独提供 → 服务端 422，本地镜像拦截；非 UUID → 422，本地镜像拦截）。
 * - created_from / created_to：datetime-local 输入（YYYY-MM-DDTHH:MM[:SS]）
 *   按 UTC 解释并归一为 ISO-8601 UTC（"YYYY-MM-DDTHH:MM:SSZ"）；闭区间
 *   （含边界）；from>to → 服务端 422，本地镜像拦截；不合法日期（如 2 月
 *   30 日）本地拦截。
 * - 分页 / 排序由 buildAuditQuery 附加：page≥1、page_size 1–100、sort 恒
 *   created_at（Contract 仅此一个排序字段）、order asc|desc。
 * - 字段点路径映射：服务端 422 fields[].field 为查询参数名（snake_case），
 *   经 auditQueryFieldFromPath 归一到表单键；未知路径不映射（由页面在通用
 *   错误区呈现，不静默丢弃 422）。
 */
import type { AuditAction, AuditObjectType, ListAuditQuery } from "../api/audit.ts";
import type { SortOrder } from "../api/clusters.ts";

/** Audit 查询表单可校验字段键。 */
export type AuditQueryFieldKey =
  | "operator"
  | "objectType"
  | "objectId"
  | "action"
  | "createdFrom"
  | "createdTo";

/** 服务端 422 查询参数名全集（Contract §2.1；分页 / 排序参数由页面控件约束）。 */
export type AuditQueryServerFieldKey =
  | "operator"
  | "object_type"
  | "object_id"
  | "action"
  | "created_from"
  | "created_to"
  | "page"
  | "page_size"
  | "sort"
  | "order";

/**
 * 服务端 422 参数名（snake_case）→ 表单键（camelCase）。
 * page/page_size/sort/order 无对应过滤表单控件（由分页 / 排序控件约束），
 * auditQueryFieldFromPath 对它们返回 null（页面在通用错误区呈现）。
 */
const SERVER_FIELD_TO_FORM_KEY: Partial<Record<AuditQueryServerFieldKey, AuditQueryFieldKey>> = {
  operator: "operator",
  object_type: "objectType",
  object_id: "objectId",
  action: "action",
  created_from: "createdFrom",
  created_to: "createdTo",
};

/** Audit 查询表单原始值（objectType/action 为下拉值；时间为 datetime-local 原始值）。 */
export interface AuditQueryFormValues {
  operator: string;
  objectType: "" | AuditObjectType;
  objectId: string;
  action: "" | AuditAction;
  createdFrom: string;
  createdTo: string;
}

/** 解析后的过滤条件（null = 未提供，不发参数）。 */
export interface AuditQueryParsed {
  operator: string | null;
  objectType: AuditObjectType | null;
  objectId: string | null;
  action: AuditAction | null;
  /** ISO-8601 UTC（"YYYY-MM-DDTHH:MM:SSZ"）。 */
  createdFrom: string | null;
  createdTo: string | null;
}

/** 字段级本地校验错误（键为表单字段键）。 */
export type AuditQueryFormErrors = Partial<Record<AuditQueryFieldKey, string>>;

/** operator 长度上限（code point；Contract §2.1：trim 后 >64 → 422）。 */
const OPERATOR_MAX = 64;

/** UUID 格式（Contract §2.1：非 UUID → 422；大小写均接受，原样上送）。 */
const UUID_PATTERN =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/** datetime-local 输入格式（秒可选；浏览器控件产出，含秒与否因精度设置而异）。 */
const DATETIME_LOCAL_PATTERN = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/;

/** 空白 Audit 查询表单值（无过滤，服务端默认 page=1/page_size=20/order=desc）。 */
export function emptyAuditQueryFormValues(): AuditQueryFormValues {
  return {
    operator: "",
    objectType: "",
    objectId: "",
    action: "",
    createdFrom: "",
    createdTo: "",
  };
}

/** 服务端 422 参数路径 → 表单键（顶层路径直通；分页 / 排序与未知路径返回 null）。 */
export function auditQueryFieldFromPath(path: string): AuditQueryFieldKey | null {
  const top = path.split(".")[0] as AuditQueryServerFieldKey;
  // 分页 / 排序参数（page/page_size/sort/order）无对应过滤表单控件，不强行映射
  if (top === "page" || top === "page_size" || top === "sort" || top === "order") {
    return null;
  }
  return SERVER_FIELD_TO_FORM_KEY[top] ?? null;
}

/** 单个时间输入的解析结果：ok=true 时 value=null 表示空输入（未提供）。 */
export type Iso8601UtcInput =
  | { ok: true; value: string | null }
  | { ok: false; message: string };

/**
 * datetime-local 原始值 → ISO-8601 UTC（"YYYY-MM-DDTHH:MM:SSZ"）。
 * - 空输入 → {ok:true, value:null}（未提供，不发参数）；
 * - 格式非法 / 分量越界 / 日期不存在（如 2026-02-30）→ {ok:false, message}；
 * - 秒省略时补 "00"（闭区间边界按整分对齐）。
 * 输入按 UTC 解释（契约时间为 ISO-8601 UTC，不做本地时区换算）。
 */
export function parseIso8601UtcInput(raw: string): Iso8601UtcInput {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: true, value: null };
  }
  const match = DATETIME_LOCAL_PATTERN.exec(trimmed);
  if (match === null) {
    return { ok: false, message: "时间格式非法（应为 YYYY-MM-DD HH:MM[:SS]，按 UTC 解释）" };
  }
  const [, year, month, day, hour, minute, second] = match;
  const y = Number(year);
  const mo = Number(month);
  const d = Number(day);
  const h = Number(hour);
  const mi = Number(minute);
  const s = second === undefined ? 0 : Number(second);
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) {
    return { ok: false, message: "时间分量越界（月 1–12、日 1–31、时 0–23、分/秒 0–59）" };
  }
  // 日历校验：Date.UTC 对越界日期会进位（如 2 月 30 日 → 3 月 2 日），回读比对
  const check = new Date(Date.UTC(y, mo - 1, d, h, mi, s));
  if (
    check.getUTCFullYear() !== y ||
    check.getUTCMonth() !== mo - 1 ||
    check.getUTCDate() !== d
  ) {
    return { ok: false, message: "日期不存在（如 2 月 30 日），请修正后重试" };
  }
  return { ok: true, value: `${year}-${month}-${day}T${hour}:${minute}:${second ?? "00"}Z` };
}

/**
 * 解析 Audit 查询表单值（本地快速反馈；服务端 422 仍按参数名呈现）：
 * - operator：trim；空 = 未提供；>64 code point → 错误；
 * - object_id：非空时须为 UUID 且 object_type 已选（同现规则）；
 * - created_from/created_to：归一为 ISO-8601 UTC；from>to → 错误（闭区间）。
 */
export function parseAuditQueryFormValues(
  values: AuditQueryFormValues,
): { ok: true; fields: AuditQueryParsed } | { ok: false; errors: AuditQueryFormErrors } {
  const errors: AuditQueryFormErrors = {};

  // operator：trim → 空不发；>64 拦截（服务端 422 的本地镜像）
  const operator = values.operator.trim();
  if (operator !== "" && Array.from(operator).length > OPERATOR_MAX) {
    errors.operator = `operator 长度超过 ${OPERATOR_MAX} 字符（Unicode code point，服务端同样限制）`;
  }

  // object_id：须与 object_type 同现；非 UUID 拦截（均为服务端 422 的本地镜像）
  const objectId = values.objectId.trim();
  if (objectId !== "") {
    if (values.objectType === "") {
      errors.objectId = "object_id 须与 object_type 同现（单独提供会被服务端 422 拒绝）";
    }
    if (!UUID_PATTERN.test(objectId)) {
      errors.objectId = "object_id 必须是 UUID（服务端同样 422 拒绝非 UUID）";
    }
  }

  // 时间：datetime-local → ISO-8601 UTC；闭区间 from≤to
  const fromResult = parseIso8601UtcInput(values.createdFrom);
  if (!fromResult.ok) {
    errors.createdFrom = fromResult.message;
  }
  const toResult = parseIso8601UtcInput(values.createdTo);
  if (!toResult.ok) {
    errors.createdTo = toResult.message;
  }
  if (
    fromResult.ok &&
    toResult.ok &&
    fromResult.value !== null &&
    toResult.value !== null &&
    fromResult.value > toResult.value
  ) {
    errors.createdTo = "created_from 不能晚于 created_to（闭区间，服务端同样 422 拒绝）";
  }

  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    fields: {
      operator: operator === "" ? null : operator,
      objectType: values.objectType === "" ? null : values.objectType,
      objectId: objectId === "" ? null : objectId,
      action: values.action === "" ? null : values.action,
      createdFrom: fromResult.ok ? fromResult.value : null,
      createdTo: toResult.ok ? toResult.value : null,
    },
  };
}

/**
 * 组装完整查询（过滤 + 分页 + 排序，Contract §2.1）：
 * 未提供的过滤条件不发（服务端默认值生效）；sort 恒 created_at（唯一排序
 * 字段）；order / page / page_size 恒携带（由页面控件约束在合法区间）。
 */
export function buildAuditQuery(
  fields: AuditQueryParsed,
  page: number,
  pageSize: number,
  order: SortOrder,
): ListAuditQuery {
  const query: ListAuditQuery = {
    page,
    page_size: pageSize,
    sort: "created_at",
    order,
  };
  if (fields.operator !== null) {
    query.operator = fields.operator;
  }
  if (fields.objectType !== null) {
    query.object_type = fields.objectType;
  }
  if (fields.objectId !== null) {
    query.object_id = fields.objectId;
  }
  if (fields.action !== null) {
    query.action = fields.action;
  }
  if (fields.createdFrom !== null) {
    query.created_from = fields.createdFrom;
  }
  if (fields.createdTo !== null) {
    query.created_to = fields.createdTo;
  }
  return query;
}
