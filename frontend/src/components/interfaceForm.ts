/**
 * Interface 表单值 ↔ API 载荷映射（F007，Contract：docs/api/F007.md v1 §2；
 * d01-conventions.md v6 §5.6）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts 与 ./hardware.ts、
 * ./virtualMachine.ts；InterfaceForm.tsx 含 JSX 无法被 Node 加载，故本模块
 * 独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按顶层字段路径呈现，
 * Contract §2.3）：
 * - 创建：resource/name 必填（resource 由所属 Resource 详情上下文提供，
 *   本模块不重复校验其存在性——服务端校验存在 / 未软删，422 field="resource"）；
 *   interface_type 省略默认 OTHER、enabled 省略默认 true（表单恒显式携带）；
 *   可空字段仅携带已登记值（省略 → null，无默认 0）。
 * - PATCH：字段省略 = 保持原值不重置（exclude_unset）；显式 null = 清空该
 *   nullable 字段（mac_address/speed_mbps/mtu/parent_interface/description）；
 *   必填 / 非 nullable（name/interface_type/enabled）不产生显式 null；
 *   resource 创建后不可改（表单只读展示，不上送，DR-79）；
 *   无变化 → 返回 null（省略全部键，仅由页面提示，不发起空更新）。
 * - name（§2.1）：trim 首尾空白 → trim 后非空 → 禁内部空白（Unicode
 *   White_Space）与控制字符（Cc/Cf）→ 长度（code point）1–64；区分大小写、
 *   保留输入、不折叠（eth0 与 ETH0 为不同名称）；唯一由服务端 409 承载。
 * - mac_address：trim 后非空或 null；≤64 code point；无格式正则、保留大小写、
 *   一期无全局唯一（DR-75）；空串 = null；纯空白 → 本地拦截（服务端 422 不转 null）。
 * - speed_mbps/mtu：正整数 1..2147483647 或 null；0/负/超限/非整数 → 422；
 *   未知留空 = null，绝不以 0 代替（DR-76 / DB-D69）。
 * - parent_interface：空 = 根接口（null）；值来自同 Resource 未删 Interface
 *   选择器（服务端 UUID）；自引用 / 跨 Resource / 成环由服务端 422
 *   field="parent_interface" 承载（DR-78/DR-85），前端不预判环。
 * - metadata：JSON object、默认 {}、整值替换、Interface 自有（DR-83）；
 *   JSON 文本解析复用 parseMetadataText（ClusterForm），由表单调用后传入
 *   本模块（避免本模块依赖 .tsx 文件，同 ./hardware.ts 约定）。
 */
import type {
  CreateInterfacePayload,
  Interface,
  InterfaceTypeValue,
  UpdateInterfacePayload,
} from "../api/interfaces.ts";

/** Interface 数值字段键（Contract §2.2；严格整数 + 正整数范围校验）。 */
export type InterfaceIntFieldKey = "speed_mbps" | "mtu";

/** Interface 表单可校验字段键（interface_type/enabled 恒合法，不参与校验）。 */
export type InterfaceFieldKey =
  | "name"
  | "mac_address"
  | InterfaceIntFieldKey
  | "parent_interface"
  | "description";

/** Interface 表单原始值（数值 / UUID 为字符串；metadata 为 JSON 文本）。 */
export interface InterfaceFormValues {
  name: string;
  interface_type: InterfaceTypeValue;
  mac_address: string;
  speed_mbps: string;
  mtu: string;
  /** 父接口 UUID（来自同 Resource 未删 Interface 选择器）；空串 = 根接口（null）。 */
  parent_interface: string;
  enabled: boolean;
  description: string;
  /** metadata 的 JSON 文本（空 = {}；由 parseMetadataText 解析）。 */
  metadata: string;
}

/** 解析后的 Interface 值（可空字段空输入 = null；interface_type/enabled 透传）。 */
export interface InterfaceParsedValues {
  /** trim 后的 name（服务端同样 trim 后校验 / 存储）。 */
  name: string;
  mac_address: string | null;
  speed_mbps: number | null;
  mtu: number | null;
  parent_interface: string | null;
  description: string | null;
  interface_type: InterfaceTypeValue;
  enabled: boolean;
}

/** Interface 字段级本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type InterfaceFormErrors = Partial<Record<InterfaceFieldKey, string>>;

/** 数值上限（Contract §2.3 / D01 §5.6：通用整型 2147483647）。 */
const INTERFACE_INT_MAX = 2147483647;

/** name 长度上限（code point；Contract §2.1 / D01 §5.2）。 */
const INTERFACE_NAME_MAX = 64;

/** mac_address 长度上限（code point；Contract §2.2 / D01 §5.2）。 */
const INTERFACE_MAC_MAX = 64;

/** 严格整数字符串（允许前导 “-”，以便给出明确的范围错误而非格式错误）。 */
const INTEGER_PATTERN = /^-?\d+$/;

/**
 * 内部空白（Unicode White_Space）：JS 正则 \s 即 White_Space 属性（含
 * \u00a0/\u3000 等；\ufeff 不属 White_Space，由下方控制字符检查拦截）。
 */
const INTERNAL_WHITESPACE_PATTERN = /\s/;

/** 控制字符（Unicode Cc/Cf；Contract §2.1，应用层口径）。 */
const CONTROL_CHAR_PATTERN = /\p{Cc}|\p{Cf}/u;

/** 空白 Interface 表单值（全字段未登记；interface_type 默认 OTHER，enabled 默认 true）。 */
export function emptyInterfaceFormValues(): InterfaceFormValues {
  return {
    name: "",
    interface_type: "OTHER",
    mac_address: "",
    speed_mbps: "",
    mtu: "",
    parent_interface: "",
    enabled: true,
    description: "",
    metadata: "",
  };
}

/**
 * 从 Interface 初始化表单值（edit 模式）；interface 为 null（防御旧版后端）时
 * 全空。数值 null → 空串（未知不以 0 代替，反向亦不把 0 丢成空串——
 * speed_mbps/mtu 为正整数，0 非法，服务端不会返回）。
 */
export function interfaceFormValuesFromInterface(
  iface: Interface | null,
): InterfaceFormValues {
  if (iface === null) {
    return emptyInterfaceFormValues();
  }
  return {
    name: iface.name,
    interface_type: iface.interface_type,
    mac_address: iface.mac_address ?? "",
    speed_mbps: iface.speed_mbps === null ? "" : String(iface.speed_mbps),
    mtu: iface.mtu === null ? "" : String(iface.mtu),
    parent_interface: iface.parent_interface === null ? "" : iface.parent_interface.id,
    enabled: iface.enabled,
    description: iface.description ?? "",
    metadata:
      Object.keys(iface.metadata).length > 0
        ? JSON.stringify(iface.metadata, null, 2)
        : "",
  };
}

/**
 * name 校验（§2.1 本地镜像）：trim → 非空 → 禁内部空白 / 控制字符 → ≤64
 * code point。返回 trim 后值（比较唯一 / 构造载荷均用 trim 后原值，不折叠）。
 */
function parseInterfaceName(raw: string, errors: InterfaceFormErrors): string {
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.name = "name 不能为空（服务端会去除首尾空白后再校验）";
    return "";
  }
  if (INTERNAL_WHITESPACE_PATTERN.test(trimmed)) {
    errors.name = "name 禁止包含内部空白（首尾空白会被去除；区分大小写，同资源内唯一）";
  }
  if (CONTROL_CHAR_PATTERN.test(trimmed)) {
    errors.name = "name 禁止包含控制字符（Unicode Cc/Cf）";
  }
  if (Array.from(trimmed).length > INTERFACE_NAME_MAX) {
    errors.name = `长度超过 ${INTERFACE_NAME_MAX} 字符（Unicode code point，服务端同样限制）`;
  }
  return trimmed;
}

/** mac_address：空 = null；非空 trim 后必须非空且 ≤64 code point（无格式正则，DR-75）。 */
function parseInterfaceMac(raw: string, errors: InterfaceFormErrors): string | null {
  if (raw === "") {
    return null;
  }
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.mac_address =
      "仅包含空白：请清空该字段表示未登记（null），或输入有效内容（服务端对纯空白返回 422）";
    return null;
  }
  if (CONTROL_CHAR_PATTERN.test(trimmed)) {
    errors.mac_address = "禁止包含控制字符（Unicode Cc/Cf）";
  }
  if (Array.from(trimmed).length > INTERFACE_MAC_MAX) {
    errors.mac_address = `长度超过 ${INTERFACE_MAC_MAX} 字符（Unicode code point；无格式校验，保留输入大小写）`;
  }
  return trimmed;
}

/** 数值字段：空 = null；严格整数且 1..INTERFACE_INT_MAX（正整数，0/负非法）。 */
function parseInterfaceInt(
  key: InterfaceIntFieldKey,
  raw: string,
  errors: InterfaceFormErrors,
): number | null {
  if (raw === "") {
    return null;
  }
  const trimmed = raw.trim();
  if (!INTEGER_PATTERN.test(trimmed)) {
    errors[key] = "必须为整数（不接受小数、文本；服务端同样按严格整数校验）";
    return null;
  }
  const value = Number(trimmed);
  if (value < 1 || value > INTERFACE_INT_MAX) {
    errors[key] = `必须为正整数（1..${INTERFACE_INT_MAX}；留空 = 未知（null），不以 0 代替）`;
    return null;
  }
  return value;
}

/**
 * 解析 Interface 表单值（不含 metadata：JSON 文本由调用方经 parseMetadataText
 * 解析后合并，见模块注释）。本地校验为快速反馈；服务端 422 仍按顶层字段
 * 路径（name / mac_address / speed_mbps / mtu / parent_interface）呈现。
 */
export function parseInterfaceFormValues(
  values: InterfaceFormValues,
): { ok: true; fields: InterfaceParsedValues } | { ok: false; errors: InterfaceFormErrors } {
  const errors: InterfaceFormErrors = {};
  const fields: InterfaceParsedValues = {
    name: parseInterfaceName(values.name, errors),
    mac_address: parseInterfaceMac(values.mac_address, errors),
    speed_mbps: parseInterfaceInt("speed_mbps", values.speed_mbps, errors),
    mtu: parseInterfaceInt("mtu", values.mtu, errors),
    // 空串 = 根接口（null）；值来自服务端 UUID 选择器，不重复校验
    // 自引用 / 跨 Resource / 成环（服务端 422 field="parent_interface"）
    parent_interface: values.parent_interface === "" ? null : values.parent_interface,
    description: values.description === "" ? null : values.description,
    interface_type: values.interface_type,
    enabled: values.enabled,
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §6.2）：resource/name/interface_type/enabled 恒携带
 * （表单恒有值；interface_type 默认 OTHER、enabled 默认 true 由显式值承载）；
 * 可空字段仅携带已登记值（省略 → null）；metadata 非空才携带（默认 {}）。
 */
export function buildInterfaceCreateInput(
  resourceId: string,
  parsed: InterfaceParsedValues,
  metadata: Record<string, unknown>,
): CreateInterfacePayload {
  const input: CreateInterfacePayload = {
    resource: resourceId,
    name: parsed.name,
    interface_type: parsed.interface_type,
    enabled: parsed.enabled,
  };
  if (parsed.mac_address !== null) {
    input.mac_address = parsed.mac_address;
  }
  if (parsed.speed_mbps !== null) {
    input.speed_mbps = parsed.speed_mbps;
  }
  if (parsed.mtu !== null) {
    input.mtu = parsed.mtu;
  }
  if (parsed.parent_interface !== null) {
    input.parent_interface = parsed.parent_interface;
  }
  if (parsed.description !== null) {
    input.description = parsed.description;
  }
  if (Object.keys(metadata).length > 0) {
    input.metadata = metadata;
  }
  return input;
}

/**
 * PATCH 载荷（Contract §6.4，exclude_unset 的本地镜像）：与当前值相同 → 省略
 * （保持原值）；变化 → 携带新值或显式 null（清空该 nullable 字段）；
 * name 按 trim 后原值比较（§2.1 唯一比较用 trim 后原值）；metadata 整值比较
 * （变化才携带，非 null）。version 必带（乐观锁）。无任何字段变化 → 返回
 * null（由页面提示，不发起空更新）。resource 不可改，永不携带。
 */
export function buildInterfacePatch(
  current: Interface,
  parsed: InterfaceParsedValues,
  metadata: Record<string, unknown>,
): UpdateInterfacePayload | null {
  const patch: UpdateInterfacePayload = { version: current.version };
  let changed = false;

  if (parsed.name !== current.name) {
    patch.name = parsed.name;
    changed = true;
  }
  if (parsed.interface_type !== current.interface_type) {
    patch.interface_type = parsed.interface_type;
    changed = true;
  }
  if (parsed.enabled !== current.enabled) {
    patch.enabled = parsed.enabled;
    changed = true;
  }
  if (parsed.mac_address !== current.mac_address) {
    patch.mac_address = parsed.mac_address;
    changed = true;
  }
  if (parsed.speed_mbps !== current.speed_mbps) {
    patch.speed_mbps = parsed.speed_mbps;
    changed = true;
  }
  if (parsed.mtu !== current.mtu) {
    patch.mtu = parsed.mtu;
    changed = true;
  }
  const prevParent = current.parent_interface === null ? null : current.parent_interface.id;
  if (parsed.parent_interface !== prevParent) {
    patch.parent_interface = parsed.parent_interface;
    changed = true;
  }
  if (parsed.description !== current.description) {
    patch.description = parsed.description;
    changed = true;
  }
  if (JSON.stringify(metadata) !== JSON.stringify(current.metadata)) {
    patch.metadata = metadata;
    changed = true;
  }
  return changed ? patch : null;
}
