/**
 * IP Pool 表单值 ↔ API 载荷映射（F009，Contract：docs/api/F009.md v1 §2；
 * d01-conventions.md v8 §5.8）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、./interfaceForm.ts、
 * ./networkForm.ts；IpPoolForm.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按顶层字段路径呈现，
 * Contract §2.3）：
 * - 创建：network/name/start_address/end_address 必填；allocation_mode 省略
 *   默认 MANUAL（表单恒显式携带）；description 省略 → null；IPPool 无
 *   metadata（请求含 metadata → 422，I-6，表单不提供该输入）。
 * - PATCH：字段省略 = 保持原值不重置（exclude_unset）；显式 null = 清空该
 *   nullable 字段（description）；name 改后重检同 Network 唯一；
 *   start/end/allocation_mode 变更由服务端重检 CIDR / 重叠 / RESERVED 占用；
 *   network 创建后不可改（表单只读展示，PATCH 载荷恒不含 network/network_id，
 *   DR-107）；无变化 → 返回 null（不发起空更新）。
 * - name（§2.1）：trim 首尾空白 → trim 后非空 → 禁控制字符（Unicode Cc/Cf）
 *   → 长度（code point）1–255；允许中文与内部普通空格且不自动合并；保留
 *   展示大小写，唯一性大小写不敏感由服务端 409 承载。
 * - start_address/end_address（§2.2）：必填单个 IPv4 主机地址（点分四段，
 *   非 CIDR/掩码，不支持 IPv6）；start ≤ end（start=end 允许，为单地址池）；
 *   均须属所属 Network 的 CIDR —— 前端在选择到网络时做本地提示（服务端
 *   同样校验并返回 422，本地不通过不代表绕过服务端）。
 * - allocation_mode ∈ {MANUAL, AUTO, RESERVED}，默认 MANUAL（语义：AUTO 允许
 *   自动与手动、MANUAL 仅手动、RESERVED 禁止分配；分配执行在 F010）。
 * - description：可选 nullable 文本，无长度上限；空串 = null（未设置）。
 * - 字段点路径映射：服务端 422 fields[].field 为顶层字段路径
 *   （network/name/start_address/end_address/allocation_mode/description，
 *   Contract §2.3），经 ipPoolFormFieldFromPath 归一到表单键；未知路径不
 *   映射（由页面在通用错误区呈现，不静默丢弃 422）。
 */
import type {
  CreateIpPoolPayload,
  IpPool,
  IpPoolAllocationMode,
  UpdateIpPoolPayload,
} from "../api/ipPools.ts";

/** IPPool 表单可校验字段键（allocation_mode 恒合法，不参与本地校验）。 */
export type IpPoolFieldKey =
  | "network"
  | "name"
  | "start_address"
  | "end_address"
  | "description";

/** 服务端 422 顶层字段全集（Contract §2.3；含恒合法的 allocation_mode）。 */
export type IpPoolServerFieldKey = IpPoolFieldKey | "allocation_mode";

const IP_POOL_FIELD_KEYS: readonly IpPoolServerFieldKey[] = [
  "network",
  "name",
  "start_address",
  "end_address",
  "allocation_mode",
  "description",
];

/** IPPool 表单原始值（network 为 UUID 字符串）。 */
export interface IpPoolFormValues {
  /** 所属 Network UUID（创建必填；编辑只读，不上送）。 */
  network: string;
  name: string;
  start_address: string;
  end_address: string;
  allocation_mode: IpPoolAllocationMode;
  description: string;
}

/** 解析后的 IPPool 值（description 空输入 = null；allocation_mode 透传）。 */
export interface IpPoolParsedValues {
  /** trim 后的 name（服务端同样 trim 后校验 / 存储）。 */
  name: string;
  /** trim 后的 IPv4 主机地址（本地不做任何归一化 / 改写）。 */
  start_address: string;
  end_address: string;
  allocation_mode: IpPoolAllocationMode;
  description: string | null;
}

/** IPPool 字段级本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type IpPoolFormErrors = Partial<Record<IpPoolFieldKey, string>>;

/** name 长度上限（code point；Contract §2.1 / D01 §5.8）。 */
const IP_POOL_NAME_MAX = 255;

/** 控制字符（Unicode Cc/Cf；Contract §2.1，应用层口径）。 */
const CONTROL_CHAR_PATTERN = /\p{Cc}|\p{Cf}/u;

/** IPv4 点分四段（0–255）；start/end 必须是不带掩码的单个主机地址。 */
const IPV4_OCTET = "(25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)";
const IPV4_PATTERN = new RegExp(`^${IPV4_OCTET}(\\.${IPV4_OCTET}){3}$`);

/** 服务端 422 点路径 → 表单字段键（顶层路径直通；未知路径返回 null 不强行映射）。 */
export function ipPoolFormFieldFromPath(path: string): IpPoolServerFieldKey | null {
  const top = path.split(".")[0];
  return (IP_POOL_FIELD_KEYS as readonly string[]).includes(top)
    ? (top as IpPoolServerFieldKey)
    : null;
}

/** 点分四段 IPv4 → 32 位无符号整数（不匹配返回 null；不做归一化）。 */
function ipv4ToInt(ip: string): number | null {
  if (!IPV4_PATTERN.test(ip)) {
    return null;
  }
  const parts = ip.split(".");
  let value = 0;
  for (const part of parts) {
    value = (value * 256 + Number(part)) >>> 0;
  }
  return value;
}

/** 网络地址（含掩码的 CIDR）→ 整数区间 [network, broadcast]；不合法返回 null。 */
function parseCidrRange(
  cidr: string,
): { network: number; broadcast: number } | null {
  const slash = cidr.indexOf("/");
  if (slash <= 0) {
    return null;
  }
  const network = ipv4ToInt(cidr.slice(0, slash));
  const prefix = Number(cidr.slice(slash + 1));
  if (network === null || !Number.isInteger(prefix) || prefix < 0 || prefix > 32) {
    return null;
  }
  // 掩码按前缀长度计算（/0 → 0，/32 → 0xFFFFFFFF）；broadcast = network | ~mask
  const mask = prefix === 0 ? 0 : (0xFFFFFFFF << (32 - prefix)) >>> 0;
  return {
    network: network & mask,
    broadcast: (network | (~mask >>> 0)) >>> 0,
  };
}

/** 空白 IPPool 表单值（allocation_mode 默认 MANUAL，Contract §2.2）。 */
export function emptyIpPoolFormValues(): IpPoolFormValues {
  return {
    network: "",
    name: "",
    start_address: "",
    end_address: "",
    allocation_mode: "MANUAL",
    description: "",
  };
}

/**
 * 从 IPPool 初始化表单值（edit 模式）；ipPool 为 null（防御旧版后端）时全空。
 * description 为 null → 空串（未设置）；network 取展开引用 id。
 */
export function ipPoolFormValuesFromIpPool(ipPool: IpPool | null): IpPoolFormValues {
  if (ipPool === null) {
    return emptyIpPoolFormValues();
  }
  return {
    network: ipPool.network.id,
    name: ipPool.name,
    start_address: ipPool.start_address,
    end_address: ipPool.end_address,
    allocation_mode: ipPool.allocation_mode,
    description: ipPool.description ?? "",
  };
}

/** name 校验（§2.1 本地镜像）：trim → 非空 → 禁控制字符 → ≤255 code point。 */
function parseIpPoolName(raw: string, errors: IpPoolFormErrors): string {
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.name = "name 不能为空（服务端会去除首尾空白后再校验）";
    return "";
  }
  if (CONTROL_CHAR_PATTERN.test(trimmed)) {
    errors.name = "name 禁止包含控制字符（Unicode Cc/Cf）";
  }
  if (Array.from(trimmed).length > IP_POOL_NAME_MAX) {
    errors.name = `长度超过 ${IP_POOL_NAME_MAX} 字符（Unicode code point，服务端同样限制）`;
  }
  return trimmed;
}

/**
 * start/end（§2.2）：必填单个 IPv4 主机地址（不带掩码）；起止顺序
 * start ≤ end（相等允许）；可选附加 CIDR 包含检查（networkCidr 非空时本地
 * 提示，服务端仍权威校验）。
 */
function parseIpPoolAddresses(
  rawStart: string,
  rawEnd: string,
  networkCidr: string | null,
  errors: IpPoolFormErrors,
): void {
  const start = rawStart.trim();
  const end = rawEnd.trim();
  let startInt: number | null = null;
  let endInt: number | null = null;

  if (start === "") {
    errors.start_address = "start_address 不能为空（服务端要求单个 IPv4 主机地址）";
  } else {
    startInt = ipv4ToInt(start);
    if (startInt === null) {
      errors.start_address =
        "必须为单个合法 IPv4 主机地址（点分四段、不带掩码，如 10.0.0.10）；不支持 IPv6 / CIDR";
    }
  }
  if (end === "") {
    errors.end_address = "end_address 不能为空（服务端要求单个 IPv4 主机地址）";
  } else {
    endInt = ipv4ToInt(end);
    if (endInt === null) {
      errors.end_address =
        "必须为单个合法 IPv4 主机地址（点分四段、不带掩码，如 10.0.0.100）；不支持 IPv6 / CIDR";
    }
  }

  // 起止顺序：start ≤ end（相等允许，为单地址池，Contract §2.2）
  if (startInt !== null && endInt !== null && startInt > endInt) {
    errors.end_address =
      "end_address 不能小于 start_address（起止允许相等，为单地址池；逆序服务端返回 422）";
  }

  // 属 CIDR 本地提示（选择到网络时；服务端同样校验并返回 422 field=start_address/end_address）
  if (networkCidr !== null) {
    const range = parseCidrRange(networkCidr.trim());
    if (range !== null) {
      if (startInt !== null && (startInt < range.network || startInt > range.broadcast)) {
        errors.start_address = `start_address 不属于所属网络 CIDR ${networkCidr}（服务端同样校验，越界返回 422）`;
      }
      if (endInt !== null && (endInt < range.network || endInt > range.broadcast)) {
        errors.end_address = `end_address 不属于所属网络 CIDR ${networkCidr}（服务端同样校验，越界返回 422）`;
      }
    }
    // CIDR 本身不合法时不做本地判定（由网络数据源 / 服务端承载，不伪造结论）
  }
}

/**
 * 解析 IPPool 表单值（不含 network 选择：创建必选由表单组件本地拦截，
 * 服务端校验存在 / 未软删，422 field="network"）。
 * networkCidr 为当前所选网络的 CIDR（null/undefined = 未知，跳过属 CIDR 本地
 * 提示，服务端仍权威校验）。本地校验为快速反馈；服务端 422 仍按顶层字段
 * 路径（network/name/start_address/end_address/allocation_mode/description）呈现。
 */
export function parseIpPoolFormValues(
  values: IpPoolFormValues,
  networkCidr?: string | null,
): { ok: true; fields: IpPoolParsedValues } | { ok: false; errors: IpPoolFormErrors } {
  const errors: IpPoolFormErrors = {};
  const name = parseIpPoolName(values.name, errors);
  parseIpPoolAddresses(values.start_address, values.end_address, networkCidr ?? null, errors);
  const fields: IpPoolParsedValues = {
    name,
    start_address: values.start_address.trim(),
    end_address: values.end_address.trim(),
    allocation_mode: values.allocation_mode,
    description: values.description === "" ? null : values.description,
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §6.2）：network/name/start_address/end_address/
 * allocation_mode 恒携带（allocation_mode 默认 MANUAL 由显式值承载）；
 * description 仅已设置时携带（省略 → null）。
 */
export function buildIpPoolCreateInput(
  networkId: string,
  parsed: IpPoolParsedValues,
): CreateIpPoolPayload {
  const input: CreateIpPoolPayload = {
    network: networkId,
    name: parsed.name,
    start_address: parsed.start_address,
    end_address: parsed.end_address,
    allocation_mode: parsed.allocation_mode,
  };
  if (parsed.description !== null) {
    input.description = parsed.description;
  }
  return input;
}

/**
 * PATCH 载荷（Contract §6.4，exclude_unset 的本地镜像）：与当前值相同 → 省略
 * （保持原值）；变化 → 携带新值或显式 null（清空 description）；
 * name/start/end 按 trim 后原值比较。version 必带（乐观锁）。
 * network 创建后不可改（DR-107）：本函数恒不携带 network/network_id。
 * 无任何字段变化 → 返回 null（由页面提示，不发起空更新）。
 * id / 只读字段（name_key/address_range/metadata 等）永不携带。
 */
export function buildIpPoolPatch(
  current: IpPool,
  parsed: IpPoolParsedValues,
): UpdateIpPoolPayload | null {
  const patch: UpdateIpPoolPayload = { version: current.version };
  let changed = false;

  if (parsed.name !== current.name) {
    patch.name = parsed.name;
    changed = true;
  }
  if (parsed.start_address !== current.start_address) {
    patch.start_address = parsed.start_address;
    changed = true;
  }
  if (parsed.end_address !== current.end_address) {
    patch.end_address = parsed.end_address;
    changed = true;
  }
  if (parsed.allocation_mode !== current.allocation_mode) {
    patch.allocation_mode = parsed.allocation_mode;
    changed = true;
  }
  if (parsed.description !== current.description) {
    patch.description = parsed.description;
    changed = true;
  }
  return changed ? patch : null;
}
