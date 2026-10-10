/**
 * IP Address 表单值 ↔ API 载荷映射（F010，Contract：docs/api/F010.md v1 §2；
 * d01-conventions.md v9 §5.9）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、./ipPoolForm.ts；
 * IpAddressForm.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按顶层字段路径呈现，
 * Contract §2.3）：
 * - 手动分配（POST /ip-addresses）：network/address 必填；address 为单个裸
 *   IPv4 主机地址（点分四段、不带掩码/前缀，不支持 IPv6；含掩码 → 422
 *   field="address"，不静默归一化）；description 省略 → null；
 *   interface/ip_pool/cluster_id/metadata 等未列 / 只读字段不可出现
 *   （分配与绑定分离 DR-137；ip_pool 服务端推导 DR-122；表单不提供该输入）。
 * - 自动分配（POST /ip-addresses/auto-allocate）：network/ip_pool 必填
 *   （ip_pool 须为该 Network 的未删 AUTO 池，服务端 409 allocation_not_allowed
 *   承载）；不降级为手动；池耗尽 409 no_available_address 不切换（DR-125）。
 * - PATCH（绑定/解绑/转移/描述，exclude_unset 的本地镜像）：version 必带；
 *   interface 省略 = 保持绑定；显式 null（表单空选）= 解绑（IP 继续占用）；
 *   非空 UUID = 绑定/转移（服务端重检存在/未软删/同 Cluster，422
 *   field="interface"）；description 显式 null = 清空；
 *   network/address/ip_pool/id 等不可变 / 只读字段恒不上送（DR-120/DR-122，
 *   创建后不可改；改地址 = 释放后重新分配）；
 *   无变化 → 返回 null（不发起空更新）。
 * - address 属所属 Network CIDR：选择到网络时做本地提示（服务端同样校验并
 *   返回 422，本地不通过不代表绕过服务端）；网络/广播地址排除、禁用 5 段、
 *   gateway、RESERVED 池范围为跨表规则，由服务端权威校验（422 field="address"），
 *   本地不复制以免规则漂移。
 * - description：可选 nullable 文本，无长度上限；空串 = null（未设置）。
 * - 字段点路径映射：服务端 422 fields[].field 为顶层字段路径
 *   （network/address/interface/description，手动/自动创建体另含 ip_pool，
 *   Contract §2.3），经 ipAddressFormFieldFromPath 归一到表单键；未知路径不
 *   映射（由页面在通用错误区呈现，不静默丢弃 422）。
 */
import type {
  AutoAllocateIpAddressPayload,
  CreateIpAddressPayload,
  IpAddress,
  UpdateIpAddressPayload,
} from "../api/ipAddresses.ts";

/** 表单模式：manual=手动分配（创建）、auto=自动分配（创建）、edit=绑定/解绑/转移/描述。 */
export type IpAddressFormMode = "manual" | "auto" | "edit";

/** IPAddress 表单可校验字段键（interface 由选择器承载，不做本地格式校验）。 */
export type IpAddressFieldKey = "network" | "address" | "ip_pool" | "interface" | "description";

/** 服务端 422 顶层字段全集（Contract §2.3：创建体 network/address/ip_pool/description；PATCH interface/description）。 */
export type IpAddressServerFieldKey = IpAddressFieldKey;

const IP_ADDRESS_FIELD_KEYS: readonly IpAddressServerFieldKey[] = [
  "network",
  "address",
  "ip_pool",
  "interface",
  "description",
];

/** IPAddress 表单原始值（network/ip_pool/interface 为 UUID 字符串，空串 = 未选择/解绑）。 */
export interface IpAddressFormValues {
  /** 所属 Network UUID（创建必填；edit 模式只读展示，不上送）。 */
  network: string;
  /** 裸 IPv4 主机地址（manual 模式必填；auto/edit 模式不使用）。 */
  address: string;
  /** 指定 AUTO 池 UUID（auto 模式必填；manual/edit 模式不使用）。 */
  ip_pool: string;
  /** 绑定 Interface UUID（edit 模式；空串 = 解绑 / 保持未绑定）。 */
  interface: string;
  description: string;
}

/** 解析后的 IPAddress 值（description 空输入 = null；interface 空选 = null）。 */
export interface IpAddressParsedValues {
  /** trim 后的裸 IPv4 主机地址（manual 模式；本地不做任何归一化 / 改写）。 */
  address: string;
  /** 绑定 Interface UUID；空选 = null（解绑，PATCH 显式 null）。 */
  interface: string | null;
  description: string | null;
}

/** IPAddress 字段级本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type IpAddressFormErrors = Partial<Record<IpAddressFieldKey, string>>;

/** IPv4 点分四段（0–255）；必须是裸主机地址（不带掩码/前缀）。 */
const IPV4_OCTET = "(25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)";
const IPV4_PATTERN = new RegExp(`^${IPV4_OCTET}(\\.${IPV4_OCTET}){3}$`);

/** 服务端 422 点路径 → 表单字段键（顶层路径直通；未知路径返回 null 不强行映射）。 */
export function ipAddressFormFieldFromPath(path: string): IpAddressServerFieldKey | null {
  const top = path.split(".")[0];
  return (IP_ADDRESS_FIELD_KEYS as readonly string[]).includes(top)
    ? (top as IpAddressServerFieldKey)
    : null;
}

/** 裸 IPv4 主机地址校验（点分四段 0–255，不带掩码/前缀；列表过滤与表单共用）。 */
export function isValidBareIpv4(address: string): boolean {
  return IPV4_PATTERN.test(address);
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

/** 空白 IPAddress 表单值（各模式只使用自己的字段）。 */
export function emptyIpAddressFormValues(): IpAddressFormValues {
  return {
    network: "",
    address: "",
    ip_pool: "",
    interface: "",
    description: "",
  };
}

/**
 * 从 IPAddress 初始化表单值（edit 模式）；ipAddress 为 null（防御旧版后端）时全空。
 * description 为 null → 空串（未设置）；interface 取展开引用 id（未绑定 → 空串）。
 */
export function ipAddressFormValuesFromIpAddress(ipAddress: IpAddress | null): IpAddressFormValues {
  if (ipAddress === null) {
    return emptyIpAddressFormValues();
  }
  return {
    network: ipAddress.network.id,
    address: ipAddress.address,
    ip_pool: ipAddress.ip_pool?.id ?? "",
    interface: ipAddress.interface?.id ?? "",
    description: ipAddress.description ?? "",
  };
}

/**
 * 解析 IPAddress 表单值：
 * - manual：address 必填单个裸 IPv4 主机地址（不带掩码/前缀；IPv6 / CIDR 形式
 *   服务端 422）；可选附加 CIDR 包含检查（networkCidr 非空时本地提示）。
 * - auto：address 不参与（服务端在指定 AUTO 池内升序选址）。
 * - edit：address 为只读展示（创建后不可改，DR-120），不校验不上送。
 * network / ip_pool 选择是否为空由表单组件本地拦截（服务端校验存在 / 未软删 /
 * 属该 Network / AUTO 模式，422/409 承载），本函数不重复。
 */
export function parseIpAddressFormValues(
  values: IpAddressFormValues,
  mode: IpAddressFormMode,
  networkCidr?: string | null,
): { ok: true; fields: IpAddressParsedValues } | { ok: false; errors: IpAddressFormErrors } {
  const errors: IpAddressFormErrors = {};
  const address = values.address.trim();

  if (mode === "manual") {
    if (address === "") {
      errors.address = "address 不能为空（服务端要求单个裸 IPv4 主机地址）";
    } else if (ipv4ToInt(address) === null) {
      errors.address =
        "必须为单个合法 IPv4 主机地址（点分四段、不带掩码/前缀，如 10.0.0.5）；不支持 IPv6 / CIDR";
    } else if (networkCidr != null) {
      // 属 CIDR 本地提示（选择到网络时；服务端同样校验并返回 422 field="address"）
      const range = parseCidrRange(networkCidr.trim());
      const addressInt = ipv4ToInt(address);
      if (range !== null && addressInt !== null && (addressInt < range.network || addressInt > range.broadcast)) {
        errors.address = `address 不属于所属网络 CIDR ${networkCidr}（服务端同样校验，越界返回 422）`;
      }
      // CIDR 本身不合法时不做本地判定（由网络数据源 / 服务端承载，不伪造结论）
    }
  }

  const fields: IpAddressParsedValues = {
    address,
    interface: values.interface === "" ? null : values.interface,
    description: values.description === "" ? null : values.description,
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 手动分配载荷（Contract §6.2）：network/address 恒携带；description 仅已设置
 * 时携带（省略 → null）；interface/ip_pool/metadata/cluster_id 恒不出现。
 */
export function buildManualAllocateInput(
  networkId: string,
  parsed: IpAddressParsedValues,
): CreateIpAddressPayload {
  const input: CreateIpAddressPayload = {
    network: networkId,
    address: parsed.address,
  };
  if (parsed.description !== null) {
    input.description = parsed.description;
  }
  return input;
}

/**
 * 自动分配载荷（Contract §6.3）：network/ip_pool 恒携带（ip_pool 须为该 Network
 * 的未删 AUTO 池，服务端 409 allocation_not_allowed 承载）；description 仅已
 * 设置时携带；address/interface/metadata 恒不出现。
 */
export function buildAutoAllocateInput(
  networkId: string,
  ipPoolId: string,
  parsed: IpAddressParsedValues,
): AutoAllocateIpAddressPayload {
  const input: AutoAllocateIpAddressPayload = {
    network: networkId,
    ip_pool: ipPoolId,
  };
  if (parsed.description !== null) {
    input.description = parsed.description;
  }
  return input;
}

/**
 * PATCH 载荷（Contract §6.5，exclude_unset 的本地镜像）：
 * - interface：与当前绑定不同才携带（UUID = 绑定/转移；null = 解绑，IP 继续占用）；
 * - description：与当前值不同才携带（文本或显式 null 清空）；
 * - version 必带（乐观锁）；
 * - network/address/ip_pool/id 等不可变 / 只读字段恒不上送（DR-120/DR-122）；
 * - 无任何字段变化 → 返回 null（由页面提示，不发起空更新）。
 */
export function buildIpAddressPatch(
  current: IpAddress,
  parsed: IpAddressParsedValues,
): UpdateIpAddressPayload | null {
  const patch: UpdateIpAddressPayload = { version: current.version };
  let changed = false;

  const currentInterfaceId = current.interface?.id ?? null;
  if (parsed.interface !== currentInterfaceId) {
    patch.interface = parsed.interface;
    changed = true;
  }
  if (parsed.description !== current.description) {
    patch.description = parsed.description;
    changed = true;
  }
  return changed ? patch : null;
}
