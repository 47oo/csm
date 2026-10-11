/**
 * Service 表单值 ↔ API 载荷映射（F011，Contract：docs/api/F011.md v1 §2；
 * d01-conventions.md v10 §5.10）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、./interfaceForm.ts、
 * ./ipPoolForm.ts；ServiceForm.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按顶层字段路径呈现，
 * Contract §2.3）：
 * - 创建：resource/name 必填（resource 由选择器提供，本模块不重复校验其
 *   存在性——服务端校验存在 / 未软删，422 field="resource"）；status 省略
 *   默认 UNKNOWN（表单恒显式携带）；description 省略 → null；metadata 省略
 *   → {}（非空才携带）。
 * - PATCH：字段省略 = 保持原值不重置（exclude_unset）；显式 null = 清空该
 *   nullable 字段（description）；name 改后重检同 Resource 唯一；metadata
 *   整值替换（变化才携带，不可显式 null）；resource 创建后不可改（表单只读
 *   展示，PATCH 载荷恒不含 resource/resource_id，DR-144）；无变化 → 返回
 *   null（不发起空更新）。
 * - name（§2.1）：trim 首尾空白 → trim 后非空 → 禁控制字符（Unicode Cc/Cf）
 *   → 长度（code point）1–255；允许中文及其它 Unicode、内部普通空格且不自动
 *   合并（与 Interface 禁内部空白不同）；保留展示大小写，唯一性大小写不敏感
 *   （仅 ASCII 折叠）由服务端 409 承载。
 * - status ∈ {RUNNING, STOPPED, UNKNOWN}，默认 UNKNOWN（人工维护的登记状态、
 *   非探测、不由名称或外部监控推导/自动转换，§15/T21）。
 * - description：可选 nullable 文本，无长度上限；空串 = null（未设置）。
 * - metadata：JSON object、默认 {}、整值替换、Service 自有（DR-143）；
 *   JSON 文本解析复用 parseMetadataText（ClusterForm），由表单调用后传入
 *   本模块（避免本模块依赖 .tsx 文件，同 ./interfaceForm.ts 约定）。
 * - 字段点路径映射：服务端 422 fields[].field 为顶层字段路径
 *   （resource/name/status/description/metadata，Contract §2.3），经
 *   serviceFormFieldFromPath 归一到表单键；未知路径不映射（由页面在通用
 *   错误区呈现，不静默丢弃 422）。
 */
import type {
  CreateServicePayload,
  Service,
  ServiceStatus,
  UpdateServicePayload,
} from "../api/services.ts";

/** Service 表单可校验字段键（status 由下拉恒合法、resource 由选择器约束，不参与本地校验）。 */
export type ServiceFieldKey = "name";

/** 服务端 422 顶层字段全集（Contract §2.3）。 */
export type ServiceServerFieldKey = "resource" | "name" | "status" | "description" | "metadata";

const SERVICE_FIELD_KEYS: readonly ServiceServerFieldKey[] = [
  "resource",
  "name",
  "status",
  "description",
  "metadata",
];

/** Service 表单原始值（resource 为 UUID 字符串；metadata 为 JSON 文本）。 */
export interface ServiceFormValues {
  /** 所属 Resource UUID（创建必填；编辑只读，不上送）。 */
  resource: string;
  name: string;
  status: ServiceStatus;
  description: string;
  /** metadata 的 JSON 文本（空 = {}；由 parseMetadataText 解析后传入构建函数）。 */
  metadata: string;
}

/** 解析后的 Service 值（description 空输入 = null；status 透传）。 */
export interface ServiceParsedValues {
  /** trim 后的 name（服务端同样 trim 后校验 / 存储；保留展示大小写不折叠）。 */
  name: string;
  status: ServiceStatus;
  description: string | null;
}

/** Service 字段级本地校验错误（键为字段名，与服务端 422 fields 同名）。 */
export type ServiceFormErrors = Partial<Record<ServiceFieldKey, string>>;

/** name 长度上限（code point；Contract §2.1 / D01 §5.10）。 */
const SERVICE_NAME_MAX = 255;

/** 控制字符（Unicode Cc/Cf；Contract §2.1，应用层口径）。 */
const CONTROL_CHAR_PATTERN = /\p{Cc}|\p{Cf}/u;

/** 服务端 422 点路径 → 表单字段键（顶层路径直通；未知路径返回 null 不强行映射）。 */
export function serviceFormFieldFromPath(path: string): ServiceServerFieldKey | null {
  const top = path.split(".")[0];
  return (SERVICE_FIELD_KEYS as readonly string[]).includes(top)
    ? (top as ServiceServerFieldKey)
    : null;
}

/** 空白 Service 表单值（status 默认 UNKNOWN，Contract §2.2）。 */
export function emptyServiceFormValues(): ServiceFormValues {
  return {
    resource: "",
    name: "",
    status: "UNKNOWN",
    description: "",
    metadata: "",
  };
}

/**
 * 从 Service 初始化表单值（edit 模式）；service 为 null（防御旧版后端）时全空。
 * description 为 null → 空串（未设置）；resource 取展开引用 id；空 metadata →
 * 空文本（不显示 "{}" 噪音）。
 */
export function serviceFormValuesFromService(service: Service | null): ServiceFormValues {
  if (service === null) {
    return emptyServiceFormValues();
  }
  return {
    resource: service.resource.id,
    name: service.name,
    status: service.status,
    description: service.description ?? "",
    metadata:
      Object.keys(service.metadata).length > 0
        ? JSON.stringify(service.metadata, null, 2)
        : "",
  };
}

/**
 * name 校验（§2.1 本地镜像）：trim → 非空 → 禁控制字符（Unicode Cc/Cf）→
 * ≤255 code point。允许中文及其它 Unicode、内部普通空格（不自动合并）；
 * 保留展示大小写（唯一性大小写不敏感由服务端 409 承载）。返回 trim 后值。
 */
function parseServiceName(raw: string, errors: ServiceFormErrors): string {
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.name = "name 不能为空（服务端会去除首尾空白后再校验）";
    return "";
  }
  if (CONTROL_CHAR_PATTERN.test(trimmed)) {
    errors.name = "name 禁止包含控制字符（Unicode Cc/Cf）";
  }
  if (Array.from(trimmed).length > SERVICE_NAME_MAX) {
    errors.name = `长度超过 ${SERVICE_NAME_MAX} 字符（Unicode code point，服务端同样限制）`;
  }
  return trimmed;
}

/**
 * 解析 Service 表单值（不含 resource 选择：创建必选由表单组件本地拦截，
 * 服务端校验存在 / 未软删，422 field="resource"；不含 metadata：JSON 文本由
 * 调用方经 parseMetadataText 解析后合并，见模块注释）。本地校验为快速反馈；
 * 服务端 422 仍按顶层字段路径（resource/name/status/description/metadata）呈现。
 */
export function parseServiceFormValues(
  values: ServiceFormValues,
): { ok: true; fields: ServiceParsedValues } | { ok: false; errors: ServiceFormErrors } {
  const errors: ServiceFormErrors = {};
  const fields: ServiceParsedValues = {
    name: parseServiceName(values.name, errors),
    status: values.status,
    description: values.description === "" ? null : values.description,
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §6.2）：resource/name/status 恒携带（status 默认 UNKNOWN
 * 由显式值承载）；description 仅已设置时携带（省略 → null）；metadata 非空才
 * 携带（省略 → 服务端默认 {}）。id/name_key 等只读字段永不携带。
 */
export function buildServiceCreateInput(
  resourceId: string,
  parsed: ServiceParsedValues,
  metadata: Record<string, unknown>,
): CreateServicePayload {
  const input: CreateServicePayload = {
    resource: resourceId,
    name: parsed.name,
    status: parsed.status,
  };
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
 * （保持原值）；变化 → 携带新值或显式 null（清空 description）；
 * metadata 整值比较（变化才携带，非 null）。version 必带（乐观锁）。
 * resource 创建后不可改（DR-144）：本函数恒不携带 resource/resource_id。
 * 无任何字段变化 → 返回 null（由页面提示，不发起空更新）。
 * id / 只读字段（name_key 等）永不携带。
 */
export function buildServicePatch(
  current: Service,
  parsed: ServiceParsedValues,
  metadata: Record<string, unknown>,
): UpdateServicePayload | null {
  const patch: UpdateServicePayload = { version: current.version };
  let changed = false;

  if (parsed.name !== current.name) {
    patch.name = parsed.name;
    changed = true;
  }
  if (parsed.status !== current.status) {
    patch.status = parsed.status;
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
