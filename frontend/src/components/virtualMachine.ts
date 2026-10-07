/**
 * VirtualMachine virtual_machine 表单值 ↔ API 载荷映射
 * （F006，Contract：docs/api/F004.md v3 §2.5；d01-conventions.md v5 §5.5）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts 与 ./hardware.ts；
 * ResourceForm.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 载荷语义的本地镜像（服务端为最终权威，422 字段错误按点路径
 * virtual_machine.<field> 呈现）：
 * - 创建：VIRTUAL_MACHINE 时 virtual_machine 必须出现且 host_resource_id
 *   必填非 null；vcpu/memory_mb/disk_gb/hypervisor 仅携带已登记值
 *   （省略 → null，无默认 0）；不携带 metadata 键（归 Resource，DR-69）。
 * - PATCH：子字段级 exclude_unset——省略 = 保持原值；容量 / hypervisor
 *   显式 null = 清空该 nullable 子字段；host_resource_id 变更 = 换 Host
 *   （仅限同 Cluster 未删除 BARE_METAL，服务端校验）；virtual_machine 整体
 *   不可显式 null（422）；无变化 → 省略键。
 * - 未知值 = null，绝不以 0 代替（vcpu/memory_mb 的 0 非法；disk_gb=0 =
 *   明确无磁盘，与 null=未知语义不同且可区分）。
 * - 数值严格整数语义与范围：vcpu/memory_mb 为正整数 1..2147483647；
 *   disk_gb 为非负整数 0..2147483647（D01 §5.5，镜像 DB-D55/DB-D56）。
 * - hypervisor 字符串：trim 首尾空白 → trim 后非空 → ≤255 code point；
 *   空串留空 = null；纯空白 → 本地拦截（服务端对纯空白返回 422，不转 null）；
 *   区分大小写、保留展示；一期无枚举，不据值推导行为（DR-64）。
 * - BARE_METAL 不携带 virtual_machine 键（出现即 422，互斥对称）——由页面
 *   按 resource_type 保证，本模块不重复判断。
 *
 * host_resource_id 来自宿主选择器（同 Cluster 未删除 BARE_METAL 列表，
 * 值为服务端返回的 UUID）；本模块只校验非空，宿主四条件（存在 / 未软删 /
 * BARE_METAL / 同 Cluster）由服务端统一 422（field="virtual_machine.host_resource_id"）。
 */
import type { VirtualMachine, VirtualMachineInput, VirtualMachinePatch } from "../api/resources.ts";

/** virtual_machine 数值字段键（Contract §2.5；严格整数 + 范围校验）。 */
export type VirtualMachineIntFieldKey = "vcpu" | "memory_mb" | "disk_gb";

/** virtual_machine 表单字段键（宿主选择 + 容量三字段 + hypervisor；无 metadata）。 */
export type VirtualMachineFieldKey = "host_resource_id" | VirtualMachineIntFieldKey | "hypervisor";

/** virtual_machine 表单原始值（容量为字符串；空串 = 未登记 null）。 */
export interface VirtualMachineFormValues {
  /** 宿主 Resource UUID（来自 Host 选择器；空串 = 未选择）。 */
  host_resource_id: string;
  vcpu: string;
  memory_mb: string;
  disk_gb: string;
  hypervisor: string;
}

/** 解析后的 virtual_machine 值（容量 / hypervisor 空输入 = null）。 */
export interface VirtualMachineParsedFields {
  host_resource_id: string;
  vcpu: number | null;
  memory_mb: number | null;
  disk_gb: number | null;
  hypervisor: string | null;
}

/** virtual_machine 字段级本地校验错误（键为字段名，服务端 422 用点路径由表单映射）。 */
export type VirtualMachineFormErrors = Partial<Record<VirtualMachineFieldKey, string>>;

/** 数值上限（Contract §2.5 / D01 §5.5：通用整型 2147483647）。 */
const VM_INT_MAX = 2147483647;

/** hypervisor 长度上限（code point；Contract §2.5 / D01 §5.2/§5.5）。 */
const VM_STRING_MAX = 255;

/** 严格整数字符串（允许前导 “-”，以便给出明确的范围错误而非格式错误）。 */
const INTEGER_PATTERN = /^-?\d+$/;

/** 空白 virtual_machine 表单值（容量 / hypervisor 未登记，宿主未选择）。 */
export function emptyVirtualMachineFormValues(): VirtualMachineFormValues {
  return {
    host_resource_id: "",
    vcpu: "",
    memory_mb: "",
    disk_gb: "",
    hypervisor: "",
  };
}

/**
 * 从 Resource.virtual_machine 初始化表单值（edit 模式）；
 * virtual_machine 为 null（BARE_METAL / 旧版后端）时全空。
 * 数值 0 不得丢成空串（disk_gb=0 与 null=未知必须可区分）。
 */
export function virtualMachineFormValuesFromResource(
  vm: VirtualMachine | null,
): VirtualMachineFormValues {
  if (vm === null) {
    return emptyVirtualMachineFormValues();
  }
  return {
    host_resource_id: vm.host_resource_id,
    vcpu: vm.vcpu === null ? "" : String(vm.vcpu),
    memory_mb: vm.memory_mb === null ? "" : String(vm.memory_mb),
    disk_gb: vm.disk_gb === null ? "" : String(vm.disk_gb),
    hypervisor: vm.hypervisor ?? "",
  };
}

/** hypervisor：空 = null；非空 trim 后必须非空且 ≤255 code point。 */
function parseVirtualMachineHypervisor(
  raw: string,
  errors: VirtualMachineFormErrors,
): string | null {
  if (raw === "") {
    return null;
  }
  const trimmed = raw.trim();
  if (trimmed === "") {
    errors.hypervisor =
      "仅包含空白：请清空该字段表示未登记（null），或输入有效内容（服务端对纯空白返回 422）";
    return null;
  }
  if (Array.from(trimmed).length > VM_STRING_MAX) {
    errors.hypervisor = `长度超过 ${VM_STRING_MAX} 字符（Unicode code point，服务端同样限制）`;
  }
  return trimmed;
}

/** 容量数值字段：空 = null；严格整数且 min..VM_INT_MAX。 */
function parseVirtualMachineInt(
  key: VirtualMachineIntFieldKey,
  raw: string,
  min: 0 | 1,
  errors: VirtualMachineFormErrors,
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
  if (value < min || value > VM_INT_MAX) {
    errors[key] =
      key === "disk_gb"
        ? `必须为非负整数（0..${VM_INT_MAX}；0 = 明确无磁盘，留空 = 未知）`
        : `必须为正整数（1..${VM_INT_MAX}；留空 = 未知，不以 0 代替）`;
    return null;
  }
  return value;
}

/**
 * 解析 virtual_machine 表单值。本地校验为快速反馈；服务端 422 仍按
 * virtual_machine.<field> 点路径呈现。host_resource_id 仅校验非空
 * （值来自 Host 选择器的服务端 UUID；四条件由服务端校验）。
 */
export function parseVirtualMachineFormValues(
  values: VirtualMachineFormValues,
): { ok: true; fields: VirtualMachineParsedFields } | { ok: false; errors: VirtualMachineFormErrors } {
  const errors: VirtualMachineFormErrors = {};
  if (values.host_resource_id === "") {
    errors.host_resource_id =
      "必须选择宿主机（Host）：同集群内未删除的 BARE_METAL 资源（服务端校验宿主存在 / 未删 / 类型 / 同集群）";
  }
  const fields: VirtualMachineParsedFields = {
    host_resource_id: values.host_resource_id,
    vcpu: parseVirtualMachineInt("vcpu", values.vcpu, 1, errors),
    memory_mb: parseVirtualMachineInt("memory_mb", values.memory_mb, 1, errors),
    disk_gb: parseVirtualMachineInt("disk_gb", values.disk_gb, 0, errors),
    hypervisor: parseVirtualMachineHypervisor(values.hypervisor, errors),
  };
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields };
}

/**
 * 创建载荷（Contract §2.5 / §6.2）：virtual_machine 必须出现且
 * host_resource_id 必填，故恒返回对象（区别于 hardware 的可整体省略）；
 * 容量 / hypervisor 仅携带已登记值（省略 → null）；disk_gb=0 为有效登记值，
 * 照常携带；不携带 metadata 键（DR-69）。
 */
export function buildVirtualMachineCreateInput(
  parsed: VirtualMachineParsedFields,
): VirtualMachineInput {
  const input: VirtualMachineInput = { host_resource_id: parsed.host_resource_id };
  if (parsed.vcpu !== null) {
    input.vcpu = parsed.vcpu;
  }
  if (parsed.memory_mb !== null) {
    input.memory_mb = parsed.memory_mb;
  }
  if (parsed.disk_gb !== null) {
    input.disk_gb = parsed.disk_gb;
  }
  if (parsed.hypervisor !== null) {
    input.hypervisor = parsed.hypervisor;
  }
  return input;
}

/**
 * PATCH 载荷（Contract §2.5 / §6.4，子字段级 exclude_unset 的本地镜像）：
 * 与当前值相同 → 省略（保持原值）；变化 → 携带新值或显式 null（清空该
 * nullable 子字段）；host_resource_id 变化 = 换 Host（服务端校验同 Cluster
 * 未删除 BARE_METAL）。无任何子字段变化 → 返回 null（省略 virtual_machine 键）。
 * current 为 null 仅在旧版后端（contract v1/v2）响应下出现，按“全部未登记”处理。
 */
export function buildVirtualMachinePatch(
  current: VirtualMachine | null,
  parsed: VirtualMachineParsedFields,
): VirtualMachinePatch | null {
  const patch: VirtualMachinePatch = {};
  let changed = false;
  const prevHost = current === null ? "" : current.host_resource_id;
  if (parsed.host_resource_id !== prevHost) {
    patch.host_resource_id = parsed.host_resource_id;
    changed = true;
  }
  for (const key of ["vcpu", "memory_mb", "disk_gb"] as const) {
    const next = parsed[key];
    const prev = current === null ? null : current[key];
    if (next !== prev) {
      patch[key] = next;
      changed = true;
    }
  }
  {
    const next = parsed.hypervisor;
    const prev = current === null ? null : current.hypervisor;
    if (next !== prev) {
      patch.hypervisor = next;
      changed = true;
    }
  }
  return changed ? patch : null;
}
