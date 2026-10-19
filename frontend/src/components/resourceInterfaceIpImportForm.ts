/**
 * 「资源+网卡+IP」批量导入表单纯逻辑（F023，Contract：docs/api/F023.md v1
 * §2/§6/§10/§14；上限复用 F014 §10 签核值）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 importForm.ts 约定；
 * ResourceInterfaceIpImportPanel.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 语义的本地镜像（服务端为最终权威）：
 * - format（§2）：csv | xlsx（服务端大小写不敏感；本客户端恒发规范小写值，
 *   下拉恒合法；防御自由输入的非法值本地报错——服务端对缺失 / 非法 format
 *   返回 422 VALIDATION_ERROR field="format"，经
 *   resourceInterfaceIpImportFormFieldFromPath 映射到表单键）。
 * - file（§2）：必选；未选择文件 → 本地报错、不发起请求（空输入不发请求）。
 * - format=xlsx 仅接受 .xlsx 文件名（大小写不敏感）——服务端对 .xls / 非
 *   xlsx 返回 422 IMPORT_INVALID_FILE{unsupported_format}（§7），本地快速
 *   反馈；format=csv 不做扩展名限制（服务端按 UTF-8 解码，二进制内容报
 *   unreadable，仍以服务端错误为准）。
 * - 文件大小 > IMPORT_MAX_FILE_BYTES → 本地报错（服务端解析前 413
 *   IMPORT_FILE_TOO_LARGE 拦截；§14 复用 F014 签核值 5 MiB，服务端权威）。
 * - resourceInterfaceIpImportTargetKey：file + format 的指纹（文件名 / 大小 /
 *   修改时间 + 格式）。输入变化 → 既有预校验结果对当前输入失效（写入端点
 *   重新上传同一文件并在事务内完整重校验，§4/§12.2）。
 * - canConfirmResourceInterfaceIpImport：确认导入门控——仅当预校验成功且
 *   error_count==0（存在错误行时整批不可能成功，不进入写入）、指纹一致
 *   （防止「换了文件但沿用旧校验结果」）且本次导入未成功（同一文件再导入
 *   会因现存 (cluster,hostname)/(cluster,ip) 冲突被服务端整批拒绝，§11）
 *   时可用。
 * - 模板表头文本（§6 冻结 26 列，D03 签核）：本地镜像常量与表头行 CSV
 *   生成，供页面即时展示与 smoke 断言；逐列必填 / 适用行 / 类型 / 单位 /
 *   枚举 / 说明以 templates 端点响应为权威（§5），不在此复制。
 */
import type { ImportFormat, ResourceInterfaceIpColumnSpec } from "../api/imports.ts";
import { IMPORT_MAX_FILE_BYTES } from "../api/imports.ts";

/** F023 导入表单可校验字段键（file 为本地必选校验；format 与服务端 422 field 同名）。 */
export type ResourceInterfaceIpImportFormFieldKey = "file" | "format";

/** 服务端 422 VALIDATION_ERROR 点路径全集（Contract §1.2/§2：format 缺失 / 非法）。 */
export type ResourceInterfaceIpImportServerFieldKey = "format";

/** F023 导入表单原始值（format 下拉恒合法；file 未选择为 null）。 */
export interface ResourceInterfaceIpImportFormValues {
  format: ImportFormat;
  file: File | null;
}

/** 本地校验错误（键为字段名，format 与服务端 422 fields 同名）。 */
export type ResourceInterfaceIpImportFormErrors = Partial<
  Record<ResourceInterfaceIpImportFormFieldKey, string>
>;

/** 空白导入表单值（默认 CSV 格式、未选择文件）。 */
export function emptyResourceInterfaceIpImportFormValues(): ResourceInterfaceIpImportFormValues {
  return { format: "csv", file: null };
}

/** 服务端 422 点路径 → 表单字段键（仅 format；未知路径返回 null 不强行映射）。 */
export function resourceInterfaceIpImportFormFieldFromPath(
  path: string,
): ResourceInterfaceIpImportFormFieldKey | null {
  return path === "format" ? "format" : null;
}

/** 文件名扩展（小写）；无扩展返回空串。 */
function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  return index < 0 ? "" : name.slice(index + 1).toLowerCase();
}

/**
 * 输入指纹：format + 文件名 + 大小 + 修改时间。用于判断既有预校验结果是否
 * 仍对当前输入有效（文件 / 格式任一变化即失效，需重新预校验）。
 * 未选择文件 → null。
 */
export function resourceInterfaceIpImportTargetKey(
  values: Pick<ResourceInterfaceIpImportFormValues, "format" | "file">,
): string | null {
  if (values.file === null) {
    return null;
  }
  return `${values.format}:${values.file.name}:${values.file.size}:${values.file.lastModified}`;
}

/**
 * 解析 F023 导入表单值（本地快速反馈；服务端校验仍权威）：
 * - file 未选择 → 本地错误（空输入不发请求）；
 * - format 非 csv/xlsx → 本地错误（下拉恒合法，防御自由输入）；
 * - 文件大小超上限 → 本地错误（服务端 413 IMPORT_FILE_TOO_LARGE 同口径）；
 * - format=xlsx 且扩展名非 .xlsx（大小写不敏感）→ 本地错误
 *   （服务端 422 IMPORT_INVALID_FILE{unsupported_format} 同口径）。
 */
export function parseResourceInterfaceIpImportFormValues(
  values: ResourceInterfaceIpImportFormValues,
): { ok: true } | { ok: false; errors: ResourceInterfaceIpImportFormErrors } {
  const errors: ResourceInterfaceIpImportFormErrors = {};

  if (values.format !== "csv" && values.format !== "xlsx") {
    errors.format = "format 必须为 csv 或 xlsx（不接受其它自由输入值）";
  }

  const file = values.file;
  if (file === null) {
    errors.file = "必须先选择要导入的文件（空输入不会发起请求）";
  } else if (file.size > IMPORT_MAX_FILE_BYTES) {
    errors.file =
      `文件超过同步导入大小上限（${IMPORT_MAX_FILE_BYTES} 字节 ≈ 5 MiB）；` +
      "请拆分文件后重试（服务端同样在解析前拒绝 413 IMPORT_FILE_TOO_LARGE）";
  } else if (values.format === "xlsx" && fileExtension(file.name) !== "xlsx") {
    errors.file =
      "format=xlsx 时仅接受 .xlsx 文件（.xls 等旧格式不支持；" +
      "服务端同样拒绝 IMPORT_INVALID_FILE/unsupported_format）";
  }

  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true };
}

/**
 * 确认导入门控（纯逻辑，面板据此禁用「确认导入」按钮）：
 * - validated 为 null（未完成预校验）或 errorCount > 0（存在错误行时整批
 *   不可能成功，不进入写入）→ 不可用；
 * - validatedKey 与 currentKey 不一致（文件 / 格式已变化，旧预校验结果对
 *   当前输入失效）或任一为 null → 不可用；
 * - importSucceeded（本次导入已成功；同一文件再导入会因现存冲突被服务端
 *   整批拒绝，Contract §11）→ 不可用。
 */
export function canConfirmResourceInterfaceIpImport(input: {
  validated: { errorCount: number } | null;
  validatedKey: string | null;
  currentKey: string | null;
  importSucceeded: boolean;
}): boolean {
  return (
    input.validated !== null &&
    input.validated.errorCount === 0 &&
    input.validatedKey !== null &&
    input.validatedKey === input.currentKey &&
    !input.importSucceeded
  );
}

/**
 * 统一宽模板冻结列名（Contract §6，D03 签核；单一 26 列模板，
 * resource_type 逐行区分 BARE_METAL / VIRTUAL_MACHINE、允许混排）。
 * 本地镜像：页面即时展示表头文本与 smoke 断言用；逐列权威描述以
 * templates 端点响应为准（§5），不在此复制。
 */
export const RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS: readonly string[] = [
  "cluster",
  "hostname",
  "resource_type",
  "role",
  "status",
  "host",
  "vcpu",
  "memory_mb",
  "disk_gb",
  "hypervisor",
  "manufacturer",
  "model",
  "serial_number",
  "cpu_model",
  "cpu_sockets",
  "cpu_cores",
  "gpu_model",
  "gpu_count",
  "name",
  "interface_type",
  "mac_address",
  "speed_mbps",
  "mtu",
  "enabled",
  "network",
  "ip",
];

/** 由列名清单生成表头行 CSV 文本（服务端响应权威；.xlsx 模板使用相同表头与列序，§6）。 */
export function resourceInterfaceIpTemplateHeaderCsvFrom(names: readonly string[]): string {
  return `${names.join(",")}\n`;
}

/** 冻结 26 列的表头行 CSV 文本（本地镜像；列名 / 顺序与契约 §6 一致）。 */
export function buildResourceInterfaceIpTemplateHeaderCsv(): string {
  return resourceInterfaceIpTemplateHeaderCsvFrom(RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS);
}

/** F023 模板列「类型 · 单位 / 枚举」展示文本（type 含 boolean，§5/§6）。 */
export function resourceInterfaceIpColumnTypeLabel(
  column: Pick<ResourceInterfaceIpColumnSpec, "type" | "unit" | "enum">,
): string {
  let label = column.type;
  if (column.unit !== null) {
    label += ` · ${column.unit}`;
  }
  if (column.enum !== null && column.enum.length > 0) {
    label += `（${column.enum.join(" | ")}）`;
  }
  return label;
}

/** F023 模板列必填性展示文本（可选列空 = 省略，默认值生效，§6.2）。 */
export function resourceInterfaceIpColumnRequiredLabel(
  column: Pick<ResourceInterfaceIpColumnSpec, "required">,
): string {
  return column.required ? "必填" : "可选（空 = 省略）";
}

/** F023 模板列适用行展示文本（两类均适用 → 「BM / VM」；单类 → 仅该类，§6.1）。 */
export function resourceInterfaceIpColumnAppliesToLabel(
  column: Pick<ResourceInterfaceIpColumnSpec, "applies_to">,
): string {
  const bareMetal = column.applies_to.includes("BARE_METAL");
  const virtualMachine = column.applies_to.includes("VIRTUAL_MACHINE");
  if (bareMetal && virtualMachine) {
    return "BM / VM";
  }
  if (bareMetal) {
    return "仅 BM";
  }
  if (virtualMachine) {
    return "仅 VM";
  }
  return "—";
}
