/**
 * ServiceEndpoint 表单值 ↔ API 载荷映射（F012，Contract：docs/api/F012.md v1 §2；
 * d01-conventions.md v11 §5.11）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、./serviceForm.ts；
 * ServiceEndpointForm.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按顶层字段路径呈现，
 * Contract §2.4）：
 * - 创建：service/ip_address/protocol/port 必填（service/ip_address 由选择器
 *   提供且选项已按契约过滤——Service 未删、IP 已绑定同 Resource 未删
 *   Interface，本模块不重复校验其存在性——服务端校验存在 / 未软删 / 归属，
 *   422 field="service"/"ip_address"）；description 省略 → null；
 *   service_id/ip_address_id/id/metadata 等未列 / 只读 / 未知字段不可出现
 *   （→ 422，DR-156/DR-157；表单不提供这些输入）。
 * - PATCH：字段省略 = 保持原值不重置（exclude_unset）；显式 null = 清空该
 *   nullable 字段（description）；protocol/port 改后重检监听唯一（409 承载）；
 *   service/ip_address 创建后不可改（表单只读展示，PATCH 载荷恒不含
 *   service/service_id/ip_address/ip_address_id，DR-157）；无变化 → 返回
 *   null（不发起空更新）。
 * - protocol ∈ {TCP, UDP}（§2.2/DR-160）：仅接受大写规范值（下拉恒合法，
 *   本模块防御显式非法值——"tcp" 等其它值 / 显式 null 均为本地错误，服务端
 *   同样 422 field="protocol"；不做大小写归一化，不静默改写用户输入）。
 * - port（§2.2/DR-160）：trim → 非空 → 严格整数（不接受小数 / 文本）→
 *   1–65535（含端点；0、65536、负数 → 错误；边界 1、65535 合法）。
 * - description：可选 nullable 文本，无长度上限；空串 = null（未设置）。
 * - 字段点路径映射：服务端 422 fields[].field 为顶层字段路径
 *   （service/ip_address/protocol/port/description，Contract §2.4），经
 *   serviceEndpointFormFieldFromPath 归一到表单键；service_id/ip_address_id
 *   等不可变别名不映射（由页面在通用错误区呈现，不静默丢弃 422）。
 */
import type {
  CreateServiceEndpointPayload,
  EndpointProtocol,
  ServiceEndpoint,
  UpdateServiceEndpointPayload,
} from "../api/serviceEndpoints.ts";

/** ServiceEndpoint 表单可校验字段键（service/ip_address 由选择器约束，不做本地格式校验）。 */
export type ServiceEndpointFieldKey = "protocol" | "port";

/** 服务端 422 顶层字段全集（Contract §2.4）。 */
export type ServiceEndpointServerFieldKey =
  | "service"
  | "ip_address"
  | "protocol"
  | "port"
  | "description";

const SERVICE_ENDPOINT_FIELD_KEYS: readonly ServiceEndpointServerFieldKey[] = [
  "service",
  "ip_address",
  "protocol",
  "port",
  "description",
];

/** ServiceEndpoint 表单原始值（service/ip_address 为 UUID 字符串；port 为文本输入）。 */
export interface ServiceEndpointFormValues {
  /** 所属 Service UUID（创建必填；编辑只读，不上送）。 */
  service: string;
  /** 引用 IPAddress UUID（创建必填；编辑只读，不上送）。 */
  ipAddress: string;
  protocol: EndpointProtocol;
  /** 监听端口的文本输入（解析为严格整数 1–65535）。 */
  port: string;
  description: string;
}

/** 解析后的 ServiceEndpoint 值（description 空输入 = null）。 */
export interface ServiceEndpointParsedValues {
  protocol: EndpointProtocol;
  port: number;
  description: string | null;
}

/** ServiceEndpoint 字段级本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type ServiceEndpointFormErrors = Partial<Record<ServiceEndpointFieldKey, string>>;

/** 端口下限 / 上限（含端点，Contract §2.2 / D01 §5.11）。 */
const PORT_MIN = 1;
const PORT_MAX = 65535;

/** 严格整数字符串（允许前导 “-”，以便给出明确的范围错误而非格式错误）。 */
const INTEGER_PATTERN = /^-?\d+$/;

/** 服务端 422 点路径 → 表单字段键（顶层路径直通；不可变别名 / 未知路径返回 null 不强行映射）。 */
export function serviceEndpointFormFieldFromPath(
  path: string,
): ServiceEndpointServerFieldKey | null {
  const top = path.split(".")[0];
  return (SERVICE_ENDPOINT_FIELD_KEYS as readonly string[]).includes(top)
    ? (top as ServiceEndpointServerFieldKey)
    : null;
}

/** 空白 ServiceEndpoint 表单值（protocol 无默认值，须显式选择）。 */
export function emptyServiceEndpointFormValues(): ServiceEndpointFormValues {
  return {
    service: "",
    ipAddress: "",
    protocol: "TCP",
    port: "",
    description: "",
  };
}

/**
 * 从 ServiceEndpoint 初始化表单值（edit 模式）；endpoint 为 null（防御旧版
 * 后端）时全空。description 为 null → 空串（未设置）；service/ipAddress 取
 * 展开引用 id。
 */
export function serviceEndpointFormValuesFromEndpoint(
  endpoint: ServiceEndpoint | null,
): ServiceEndpointFormValues {
  if (endpoint === null) {
    return emptyServiceEndpointFormValues();
  }
  return {
    service: endpoint.service.id,
    ipAddress: endpoint.ip_address.id,
    protocol: endpoint.protocol,
    port: String(endpoint.port),
    description: endpoint.description ?? "",
  };
}

/**
 * 解析 ServiceEndpoint 表单值（不含 service/ip_address 选择：创建必选由表单
 * 组件本地拦截，服务端校验存在 / 未软删 / 归属，422 field="service"/
 * "ip_address"）。本地校验为快速反馈；服务端 422 仍按顶层字段路径
 * （service/ip_address/protocol/port/description）呈现。
 */
export function parseServiceEndpointFormValues(
  values: ServiceEndpointFormValues,
): { ok: true; fields: ServiceEndpointParsedValues } | { ok: false; errors: ServiceEndpointFormErrors } {
  const errors: ServiceEndpointFormErrors = {};

  // protocol：仅大写规范值（下拉恒合法；防御显式非法值——服务端同样 422，
  // 不做大小写归一化，Contract §2.2/DR-160）
  if (values.protocol !== "TCP" && values.protocol !== "UDP") {
    errors.protocol =
      "protocol 必须为 TCP 或 UDP（仅大写规范值；服务端不接受其它值或 null）";
  }

  // port：trim → 非空 → 严格整数 → 1–65535（含端点，Contract §2.2/DR-160）
  const portText = values.port.trim();
  let port = 0;
  if (portText === "") {
    errors.port = "port 不能为空（整数 1–65535，含端点）";
  } else if (!INTEGER_PATTERN.test(portText)) {
    errors.port = "port 必须为整数（不接受小数、文本；服务端同样按严格整数校验）";
  } else {
    port = Number(portText);
    if (port < PORT_MIN || port > PORT_MAX) {
      errors.port = `port 必须在 ${PORT_MIN}–${PORT_MAX} 范围内（含端点；0、65536、负数均非法）`;
    }
  }

  const fields: ServiceEndpointParsedValues = {
    protocol: values.protocol,
    port,
    description: values.description === "" ? null : values.description,
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §6.2）：service/ip_address/protocol/port 恒携带；
 * description 仅已设置时携带（省略 → null）。service_id/ip_address_id/id/
 * metadata 等只读 / 未知字段永不携带。
 */
export function buildServiceEndpointCreateInput(
  serviceId: string,
  ipAddressId: string,
  parsed: ServiceEndpointParsedValues,
): CreateServiceEndpointPayload {
  const input: CreateServiceEndpointPayload = {
    service: serviceId,
    ip_address: ipAddressId,
    protocol: parsed.protocol,
    port: parsed.port,
  };
  if (parsed.description !== null) {
    input.description = parsed.description;
  }
  return input;
}

/**
 * PATCH 载荷（Contract §6.4，exclude_unset 的本地镜像）：与当前值相同 →
 * 省略（保持原值）；变化 → 携带新值或显式 null（清空 description）；
 * protocol/port 变化后重检监听唯一（排除自身，409 承载）。version 必带
 * （乐观锁）。service/ip_address 创建后不可改（DR-157）：本函数恒不携带
 * service/service_id/ip_address/ip_address_id。无任何字段变化 → 返回
 * null（由页面提示，不发起空更新）。id / 只读字段永不携带。
 */
export function buildServiceEndpointPatch(
  current: ServiceEndpoint,
  parsed: ServiceEndpointParsedValues,
): UpdateServiceEndpointPayload | null {
  const patch: UpdateServiceEndpointPayload = { version: current.version };
  let changed = false;

  if (parsed.protocol !== current.protocol) {
    patch.protocol = parsed.protocol;
    changed = true;
  }
  if (parsed.port !== current.port) {
    patch.port = parsed.port;
    changed = true;
  }
  if (parsed.description !== current.description) {
    patch.description = parsed.description;
    changed = true;
  }
  return changed ? patch : null;
}
