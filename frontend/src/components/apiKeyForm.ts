/**
 * API Key 创建表单纯逻辑（F017，Contract：docs/api/F017.md v1 §4.3；无 JSX，
 * 供 ApiKeyManagementPanel 与 scripts/smoke-client.mjs 共用）。
 *
 * - user_id：必选（下拉选项为存在且 ACTIVE 的账号；未选 → 本地拦截，
 *   服务端同样 422 field="user_id"）。
 * - label：trim 首尾空白 → trim 后非空 → 禁控制字符（Unicode Cc/Cf）→
 *   长度（code point）1..255；允许中文与内部普通空格且不自动合并；保留
 *   输入不折叠；不要求唯一（F017-OPEN-3 默认，重复由服务端允许）。
 * - validity_days：整数 1..365（含端点），默认 90；无「永不过期」取值；
 *   空（null）/ 非整数 / 越界 → 本地拦截（服务端同样 422）。
 * - 服务端 422 字段名（user_id / label / validity_days）→ 表单键映射；
 *   分页 / 排序参数与未知路径不强行映射。
 */
import type { CreateApiKeyPayload } from "../api/apiKeys.ts";

/** label 长度上限（code point；Contract §4.3）。 */
export const API_KEY_LABEL_MAX = 255;

/** 有效期范围（Contract §4.3：整数 1..365 含端点；缺省 90；无永不过期）。 */
export const VALIDITY_DAYS_DEFAULT = 90;
export const VALIDITY_DAYS_MIN = 1;
export const VALIDITY_DAYS_MAX = 365;

/** 控制字符（Unicode Cc/Cf；Contract §4.3，应用层口径）。 */
const CONTROL_CHAR_PATTERN = /\p{Cc}|\p{Cf}/u;

/** 创建表单原始值（面板受控状态）。 */
export interface ApiKeyFormValues {
  /** 绑定账号 user_id（"" = 未选择）。 */
  userId: string;
  label: string;
  /** 有效期天数；null = 输入框被清空（本地拦截，不发起请求）。 */
  validityDays: number | null;
}

/** 本地校验错误键（与服务端 422 字段经 apiKeyFormFieldFromPath 映射后同名空间）。 */
export type ApiKeyFormErrors = Partial<Record<"userId" | "label" | "validityDays", string>>;

/** 本地校验通过后的创建字段（构造 POST body 用）。 */
export interface ParsedApiKeyFields {
  userId: string;
  label: string;
  validityDays: number;
}

/** 空白创建表单值（有效期默认 90 天，Contract §4.3 缺省）。 */
export function emptyApiKeyFormValues(): ApiKeyFormValues {
  return { userId: "", label: "", validityDays: VALIDITY_DAYS_DEFAULT };
}

/** 有效期解析结果（null / 非整数 / 越界 → 错误文案；无永不过期取值）。 */
function parseValidityDays(
  value: number | null,
): { ok: true; days: number } | { ok: false; message: string } {
  if (value === null) {
    return {
      ok: false,
      message: `有效期不能为空（${VALIDITY_DAYS_MIN}–${VALIDITY_DAYS_MAX} 整数天；无永不过期选项）`,
    };
  }
  if (!Number.isInteger(value)) {
    return {
      ok: false,
      message: `有效期须为整数天（${VALIDITY_DAYS_MIN}–${VALIDITY_DAYS_MAX}）`,
    };
  }
  if (value < VALIDITY_DAYS_MIN || value > VALIDITY_DAYS_MAX) {
    return {
      ok: false,
      message: `有效期须在 ${VALIDITY_DAYS_MIN}–${VALIDITY_DAYS_MAX} 天之间（含端点；无永不过期选项）`,
    };
  }
  return { ok: true, days: value };
}

/**
 * 创建表单本地校验（服务端 422 的本地镜像，快速反馈；服务端为最终权威）：
 * 未选账号 / label 空·纯空白·控制字符·超 255 code point / 有效期空·非整数·
 * 越界 → 不发起请求。
 */
export function parseApiKeyFormValues(
  values: ApiKeyFormValues,
): { ok: true; fields: ParsedApiKeyFields } | { ok: false; errors: ApiKeyFormErrors } {
  const errors: ApiKeyFormErrors = {};

  if (values.userId === "") {
    errors.userId = "请选择绑定账号（须为存在且启用（ACTIVE）的账号）";
  }

  const label = values.label.trim();
  if (label === "") {
    errors.label = "label 不能为空（服务端会去除首尾空白后再校验）";
  } else if (CONTROL_CHAR_PATTERN.test(label)) {
    errors.label = "label 禁止包含控制字符（Unicode Cc/Cf）";
  } else if (Array.from(label).length > API_KEY_LABEL_MAX) {
    errors.label = `长度超过 ${API_KEY_LABEL_MAX} 字符（Unicode code point，服务端同样限制）`;
  }

  const validity = parseValidityDays(values.validityDays);
  if (!validity.ok) {
    errors.validityDays = validity.message;
  }

  if (!validity.ok || Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return {
    ok: true,
    fields: { userId: values.userId, label, validityDays: validity.days },
  };
}

/** 服务端 422 字段名 → 表单键（未知 / 分页排序参数返回 null，页面在通用错误区呈现）。 */
export function apiKeyFormFieldFromPath(
  path: string,
): "userId" | "label" | "validityDays" | null {
  switch (path) {
    case "user_id":
      return "userId";
    case "label":
      return "label";
    case "validity_days":
      return "validityDays";
    default:
      return null;
  }
}

/** 构造 POST /api-keys 请求体（恰含 user_id/label/validity_days，Contract §4.3）。 */
export function buildCreateApiKeyInput(fields: ParsedApiKeyFields): CreateApiKeyPayload {
  return {
    user_id: fields.userId,
    label: fields.label,
    validity_days: fields.validityDays,
  };
}
