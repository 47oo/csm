/**
 * BareMetal hardware 表单值 ↔ API 载荷映射（F005，Contract：docs/api/F004.md v2 §2.4）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts；ResourceForm.tsx
 * 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按点路径
 * hardware.<field> 呈现）：
 * - 创建：hardware 仅携带已登记子字段（省略 → null，无默认 0）；
 *   全部留空 → 整体省略 hardware 键（等效全 null）。
 * - PATCH：子字段级 exclude_unset——省略 = 保持原值；显式 null = 清空该
 *   nullable 子字段；hardware 整体不可显式 null（422）；无变化 → 省略键。
 * - 未知值 = null，绝不以 0 代替（gpu_count=0 = 明确无 GPU）。
 * - 数值严格整数语义与范围（cpu_sockets/cpu_cores/memory_mb 为正整数
 *   1..2147483647；gpu_count 为非负整数 0..2147483647）。
 * - 字符串 trim 后非空、≤255 code point（空串 / 纯 whitespace 不发送，
 *   由本地校验拦截；服务端对空串 / 纯空白返回 422，不转 null）。
 * - VM 不携带 hardware 键（出现即 422，DR-51）——由页面按 resource_type
 *   保证，本模块不重复判断。
 *
 * hardware.metadata 的 JSON 文本解析复用 parseMetadataText（ClusterForm），
 * 由表单与页面各自调用后传入本模块（避免本模块依赖 .tsx 文件）。
 */
import type { Hardware, HardwareInput, HardwarePatch } from "../api/resources.ts";

/** hardware 字符串字段键（Contract §2.4；trim 后非空或 null）。 */
export type HardwareStringFieldKey =
  | "manufacturer"
  | "model"
  | "serial_number"
  | "cpu_model"
  | "gpu_model";

/** hardware 数值字段键（Contract §2.4；严格整数 + 范围校验）。 */
export type HardwareIntFieldKey =
  | "cpu_sockets"
  | "cpu_cores"
  | "memory_mb"
  | "gpu_count";

/** hardware 表单字段键（9 字段 + metadata；metadata 为 JSON 文本，单独解析）。 */
export type HardwareFieldKey = HardwareStringFieldKey | HardwareIntFieldKey | "metadata";

/** hardware 表单原始值（均为字符串；空串 = 未登记 null）。 */
export interface HardwareFormValues {
  manufacturer: string;
  model: string;
  serial_number: string;
  cpu_model: string;
  cpu_sockets: string;
  cpu_cores: string;
  memory_mb: string;
  gpu_model: string;
  gpu_count: string;
  /** hardware.metadata 的 JSON 文本（空 = {}；由 parseMetadataText 解析）。 */
  metadata: string;
}

/** 解析后的 hardware 9 字段值（空输入 = null；metadata 由调用方另行解析）。 */
export interface HardwareParsedFields {
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  cpu_model: string | null;
  cpu_sockets: number | null;
  cpu_cores: number | null;
  memory_mb: number | null;
  gpu_model: string | null;
  gpu_count: number | null;
}

/** 解析后的完整 hardware 值（9 字段 + metadata 对象）。 */
export interface HardwareParsedValues extends HardwareParsedFields {
  metadata: Record<string, unknown>;
}

/** hardware 字段级本地校验错误（键为字段名，服务端 422 用点路径由表单映射）。 */
export type HardwareFormErrors = Partial<Record<HardwareFieldKey, string>>;

/** 数值上限（Contract §2.4：通用整型 2147483647）。 */
const HARDWARE_INT_MAX = 2147483647;

/** 字符串长度上限（code point；Contract §2.4 / d01 §5.4）。 */
const HARDWARE_STRING_MAX = 255;

/** 严格整数字符串（允许前导 “-”，以便给出明确的范围错误而非格式错误）。 */
const INTEGER_PATTERN = /^-?\d+$/;

/** 空白 hardware 表单值（全部未登记）。 */
export function emptyHardwareFormValues(): HardwareFormValues {
  return {
    manufacturer: "",
    model: "",
    serial_number: "",
    cpu_model: "",
    cpu_sockets: "",
    cpu_cores: "",
    memory_mb: "",
    gpu_model: "",
    gpu_count: "",
    metadata: "",
  };
}

/** 从 Resource.hardware 初始化表单值（edit 模式）；hardware 为 null（VM）时全空。 */
export function hardwareFormValuesFromResource(hardware: Hardware | null): HardwareFormValues {
  if (hardware === null) {
    return emptyHardwareFormValues();
  }
  return {
    manufacturer: hardware.manufacturer ?? "",
    model: hardware.model ?? "",
    serial_number: hardware.serial_number ?? "",
    cpu_model: hardware.cpu_model ?? "",
    cpu_sockets: hardware.cpu_sockets === null ? "" : String(hardware.cpu_sockets),
    cpu_cores: hardware.cpu_cores === null ? "" : String(hardware.cpu_cores),
    memory_mb: hardware.memory_mb === null ? "" : String(hardware.memory_mb),
    gpu_model: hardware.gpu_model ?? "",
    gpu_count: hardware.gpu_count === null ? "" : String(hardware.gpu_count),
    metadata:
      Object.keys(hardware.metadata).length > 0
        ? JSON.stringify(hardware.metadata, null, 2)
        : "",
  };
}

/** 字符串字段：空 = null；非空 trim 后必须非空且 ≤255 code point。 */
function parseHardwareString(
  key: HardwareStringFieldKey,
  raw: string,
  errors: HardwareFormErrors,
): string | null {
  if (raw === "") {
    return null;
  }
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors[key] = "仅包含空白：请清空该字段表示未登记（null），或输入有效内容（服务端对纯空白返回 422）";
    return null;
  }
  if (Array.from(trimmed).length > HARDWARE_STRING_MAX) {
    errors[key] = `长度超过 ${HARDWARE_STRING_MAX} 字符（Unicode code point，服务端同样限制）`;
  }
  return trimmed;
}

/** 数值字段：空 = null；严格整数且 min..HARDWARE_INT_MAX。 */
function parseHardwareInt(
  key: HardwareIntFieldKey,
  raw: string,
  min: 0 | 1,
  errors: HardwareFormErrors,
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
  if (value < min || value > HARDWARE_INT_MAX) {
    errors[key] =
      min === 0
        ? `必须为非负整数（0..${HARDWARE_INT_MAX}；0 = 明确无 GPU，留空 = 未知）`
        : `必须为正整数（1..${HARDWARE_INT_MAX}；留空 = 未知，不以 0 代替）`;
    return null;
  }
  return value;
}

/**
 * 解析 hardware 表单值（9 字段；metadata 文本由调用方经 parseMetadataText
 * 解析后合并）。本地校验为快速反馈；服务端 422 仍按点路径呈现。
 */
export function parseHardwareFormValues(
  values: HardwareFormValues,
): { ok: true; fields: HardwareParsedFields } | { ok: false; errors: HardwareFormErrors } {
  const errors: HardwareFormErrors = {};
  const fields: HardwareParsedFields = {
    manufacturer: parseHardwareString("manufacturer", values.manufacturer, errors),
    model: parseHardwareString("model", values.model, errors),
    serial_number: parseHardwareString("serial_number", values.serial_number, errors),
    cpu_model: parseHardwareString("cpu_model", values.cpu_model, errors),
    cpu_sockets: parseHardwareInt("cpu_sockets", values.cpu_sockets, 1, errors),
    cpu_cores: parseHardwareInt("cpu_cores", values.cpu_cores, 1, errors),
    memory_mb: parseHardwareInt("memory_mb", values.memory_mb, 1, errors),
    gpu_model: parseHardwareString("gpu_model", values.gpu_model, errors),
    gpu_count: parseHardwareInt("gpu_count", values.gpu_count, 0, errors),
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §2.4 / §6.2）：仅携带已登记子字段（省略 → null）；
 * 全部为 null / 空 metadata → 返回 undefined（整体省略 hardware 键，
 * 等效全 null）。gpu_count=0 为有效登记值，照常携带。
 */
export function buildHardwareCreateInput(parsed: HardwareParsedValues): HardwareInput | undefined {
  const input: HardwareInput = {};
  let any = false;
  for (const key of ["manufacturer", "model", "serial_number", "cpu_model", "gpu_model"] as const) {
    const value = parsed[key];
    if (value !== null) {
      input[key] = value;
      any = true;
    }
  }
  for (const key of ["cpu_sockets", "cpu_cores", "memory_mb", "gpu_count"] as const) {
    const value = parsed[key];
    if (value !== null) {
      input[key] = value;
      any = true;
    }
  }
  if (Object.keys(parsed.metadata).length > 0) {
    input.metadata = parsed.metadata;
    any = true;
  }
  return any ? input : undefined;
}

/**
 * PATCH 载荷（Contract §2.4 / §6.4，子字段级 exclude_unset 的本地镜像）：
 * 与当前值相同 → 省略（保持原值）；变化 → 携带新值或显式 null（清空该
 * nullable 子字段）；metadata 整值比较（变化才携带，非 null）。
 * 无任何子字段变化 → 返回 null（省略 hardware 键）。
 * current 为 null 仅在旧版后端（contract v1）响应下出现，按“全部未登记”处理。
 */
export function buildHardwarePatch(
  current: Hardware | null,
  parsed: HardwareParsedValues,
): HardwarePatch | null {
  const patch: HardwarePatch = {};
  let changed = false;
  for (const key of ["manufacturer", "model", "serial_number", "cpu_model", "gpu_model"] as const) {
    const next = parsed[key];
    const prev = current === null ? null : current[key];
    if (next !== prev) {
      patch[key] = next;
      changed = true;
    }
  }
  for (const key of ["cpu_sockets", "cpu_cores", "memory_mb", "gpu_count"] as const) {
    const next = parsed[key];
    const prev = current === null ? null : current[key];
    if (next !== prev) {
      patch[key] = next;
      changed = true;
    }
  }
  const prevMetadata = current === null ? {} : current.metadata;
  if (JSON.stringify(parsed.metadata) !== JSON.stringify(prevMetadata)) {
    patch.metadata = parsed.metadata;
    changed = true;
  }
  return changed ? patch : null;
}
