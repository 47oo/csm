/**
 * Network 表单值 ↔ API 载荷映射（F008，Contract：docs/api/F008.md v1 §2；
 * d01-conventions.md v7 §5.7）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、./interfaceForm.ts）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按顶层字段路径呈现，
 * Contract §2.3）：
 * - 创建：cluster/name/cidr 必填；status 省略默认 ACTIVE、auto_allocate 省略
 *   默认 false（表单恒显式携带）；gateway/description 空 = null；metadata 默认
 *   {}、整值替换、Network 自有（DR-95）。
 * - PATCH：字段省略 = 保持原值不重置（exclude_unset）；显式 null = 清空该
 *   nullable 字段（gateway/description）；name 改后重检同 Cluster 唯一；
 *   cidr/cluster 改后由服务端重检引用与重叠；无变化 → 返回 null。
 * - name（§2.1）：trim 首尾空白 → trim 后非空 → 禁控制字符（Unicode Cc/Cf）
 *   → 长度（code point）1–255；允许中文与内部普通空格且不自动合并；保留
 *   展示大小写，唯一性大小写不敏感由服务端 409 承载。
 * - cidr（§2.2）：必填合法 IPv4 CIDR；host 位由服务端归一化为网络地址
 *   （'10.0.0.5/24'→'10.0.0.0/24'），前端只做格式校验、不改写输入。
 * - gateway（§2.2/§11.1）：可选 IPv4；是否属 CIDR 基础可用地址 / 是否落入
 *   禁用范围由服务端校验（422 field="gateway"），前端只做格式校验。
 * - status ∈ {ACTIVE, INACTIVE}；auto_allocate boolean（仅控自动分配）。
 * - metadata：JSON object、默认 {}、整值替换；JSON 文本解析复用
 *   parseMetadataText（ClusterForm），由表单调用后传入本模块。
 */
import type {
  CreateNetworkPayload,
  Network,
  NetworkStatus,
  UpdateNetworkPayload,
} from "../api/networks.ts";

/** Network 表单可校验字段键（status/auto_allocate 恒合法，不参与本地校验）。 */
export type NetworkFieldKey = "name" | "cidr" | "gateway" | "description";

/** Network 表单原始值（cluster 为 UUID 字符串；metadata 为 JSON 文本）。 */
export interface NetworkFormValues {
  /** 所属 Cluster UUID（来自未删除集群选择器；创建必填）。 */
  cluster: string;
  name: string;
  cidr: string;
  gateway: string;
  status: NetworkStatus;
  auto_allocate: boolean;
  description: string;
  /** metadata 的 JSON 文本（空 = {}；由 parseMetadataText 解析）。 */
  metadata: string;
}

/** 解析后的 Network 值（可空字段空输入 = null；status/auto_allocate 透传）。 */
export interface NetworkParsedValues {
  /** trim 后的 name（服务端同样 trim 后校验 / 存储）。 */
  name: string;
  /** trim 后的 cidr（未归一化 host 位；服务端负责归一化）。 */
  cidr: string;
  gateway: string | null;
  status: NetworkStatus;
  auto_allocate: boolean;
  description: string | null;
}

/** Network 字段级本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type NetworkFormErrors = Partial<Record<NetworkFieldKey, string>>;

/** name 长度上限（code point；Contract §2.1 / D01 §5.7）。 */
const NETWORK_NAME_MAX = 255;

/** 控制字符（Unicode Cc/Cf；Contract §2.1，应用层口径）。 */
const CONTROL_CHAR_PATTERN = /\p{Cc}|\p{Cf}/u;

/** IPv4 点分四段（0–255）；网关与 CIDR 网络部分共用。 */
const IPV4_OCTET = "(25[0-5]|2[0-4]\\d|1\\d\\d|[1-9]?\\d)";
const IPV4_PATTERN = new RegExp(`^${IPV4_OCTET}(\\.${IPV4_OCTET}){3}$`);

/** 合法 IPv4 CIDR：点分四段 + /0–32（host 位由服务端归一化，前端不拒绝）。 */
const CIDR_PATTERN = new RegExp(`^${IPV4_OCTET}(\\.${IPV4_OCTET}){3}/(3[0-2]|[12]?\\d)$`);

/** 空白 Network 表单值（status 默认 ACTIVE，auto_allocate 默认 false）。 */
export function emptyNetworkFormValues(): NetworkFormValues {
  return {
    cluster: "",
    name: "",
    cidr: "",
    gateway: "",
    status: "ACTIVE",
    auto_allocate: false,
    description: "",
    metadata: "",
  };
}

/**
 * 从 Network 初始化表单值（edit 模式）；network 为 null（防御旧版后端）时全空。
 * gateway/description 为 null → 空串（未设置）；cluster 取展开引用 id。
 */
export function networkFormValuesFromNetwork(network: Network | null): NetworkFormValues {
  if (network === null) {
    return emptyNetworkFormValues();
  }
  return {
    cluster: network.cluster.id,
    name: network.name,
    cidr: network.cidr,
    gateway: network.gateway ?? "",
    status: network.status,
    auto_allocate: network.auto_allocate,
    description: network.description ?? "",
    metadata:
      Object.keys(network.metadata).length > 0
        ? JSON.stringify(network.metadata, null, 2)
        : "",
  };
}

/** name 校验（§2.1 本地镜像）：trim → 非空 → 禁控制字符 → ≤255 code point。 */
function parseNetworkName(raw: string, errors: NetworkFormErrors): string {
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.name = "name 不能为空（服务端会去除首尾空白后再校验）";
    return "";
  }
  if (CONTROL_CHAR_PATTERN.test(trimmed)) {
    errors.name = "name 禁止包含控制字符（Unicode Cc/Cf）";
  }
  if (Array.from(trimmed).length > NETWORK_NAME_MAX) {
    errors.name = `长度超过 ${NETWORK_NAME_MAX} 字符（Unicode code point，服务端同样限制）`;
  }
  return trimmed;
}

/** cidr（§2.2）：必填合法 IPv4 CIDR；host 位接受，归一化由服务端完成。 */
function parseNetworkCidr(raw: string, errors: NetworkFormErrors): string {
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.cidr = "cidr 不能为空（服务端要求合法 IPv4 CIDR，如 10.0.0.0/24）";
    return "";
  }
  if (!CIDR_PATTERN.test(trimmed)) {
    errors.cidr =
      "必须为合法 IPv4 CIDR（点分四段 + /0–32）；不支持 IPv6；host 位会被服务端归一化为网络地址";
  }
  return trimmed;
}

/** gateway（§2.2）：空 = null；非空必须为合法 IPv4（是否属 CIDR / 是否禁用由服务端校验）。 */
function parseNetworkGateway(raw: string, errors: NetworkFormErrors): string | null {
  if (raw === "") {
    return null;
  }
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.gateway =
      "仅包含空白：请清空该字段表示未设置（null），或输入有效 IPv4 地址（服务端对纯空白返回 422）";
    return null;
  }
  if (!IPV4_PATTERN.test(trimmed)) {
    errors.gateway =
      "必须为合法 IPv4 地址（如 10.0.0.1）；是否属该 CIDR 基础可用地址且非禁用范围由服务端校验";
  }
  return trimmed;
}

/**
 * 解析 Network 表单值（不含 metadata：JSON 文本由调用方经 parseMetadataText
 * 解析后合并，见模块注释）。本地校验为快速反馈；服务端 422 仍按顶层字段
 * 路径（name / cluster / cidr / gateway / status / auto_allocate / metadata）呈现。
 */
export function parseNetworkFormValues(
  values: NetworkFormValues,
): { ok: true; fields: NetworkParsedValues } | { ok: false; errors: NetworkFormErrors } {
  const errors: NetworkFormErrors = {};
  const fields: NetworkParsedValues = {
    name: parseNetworkName(values.name, errors),
    cidr: parseNetworkCidr(values.cidr, errors),
    gateway: parseNetworkGateway(values.gateway, errors),
    status: values.status,
    auto_allocate: values.auto_allocate,
    description: values.description === "" ? null : values.description,
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §6.2）：cluster/name/cidr/status/auto_allocate 恒携带
 * （status 默认 ACTIVE、auto_allocate 默认 false 由显式值承载）；gateway 仅
 * 已设置时携带（省略 → null）；metadata 非空才携带（默认 {}）。
 */
export function buildNetworkCreateInput(
  clusterId: string,
  parsed: NetworkParsedValues,
  metadata: Record<string, unknown>,
): CreateNetworkPayload {
  const input: CreateNetworkPayload = {
    cluster: clusterId,
    name: parsed.name,
    cidr: parsed.cidr,
    status: parsed.status,
    auto_allocate: parsed.auto_allocate,
  };
  if (parsed.gateway !== null) {
    input.gateway = parsed.gateway;
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
 * （保持原值）；变化 → 携带新值或显式 null（清空 gateway/description）；
 * name/cidr 按 trim 后原值比较；cluster 按展开引用 id 比较；metadata 整值比较
 * （变化才携带，非 null）。version 必带（乐观锁）。无任何字段变化 → 返回 null
 * （由页面提示，不发起空更新）。id / 只读字段永不携带。
 */
export function buildNetworkPatch(
  current: Network,
  clusterId: string,
  parsed: NetworkParsedValues,
  metadata: Record<string, unknown>,
): UpdateNetworkPayload | null {
  const patch: UpdateNetworkPayload = { version: current.version };
  let changed = false;

  if (clusterId !== current.cluster.id) {
    patch.cluster = clusterId;
    changed = true;
  }
  if (parsed.name !== current.name) {
    patch.name = parsed.name;
    changed = true;
  }
  if (parsed.cidr !== current.cidr) {
    patch.cidr = parsed.cidr;
    changed = true;
  }
  if (parsed.gateway !== current.gateway) {
    patch.gateway = parsed.gateway;
    changed = true;
  }
  if (parsed.status !== current.status) {
    patch.status = parsed.status;
    changed = true;
  }
  if (parsed.auto_allocate !== current.auto_allocate) {
    patch.auto_allocate = parsed.auto_allocate;
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