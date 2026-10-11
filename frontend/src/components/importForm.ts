/**
 * 批量导入表单纯逻辑（F014，Contract：docs/api/F014.md v1 §2/§6/§10）。
 *
 * 纯逻辑模块（无 JSX / React 依赖）：scripts/smoke-client.mjs 以 Node type
 * stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts 与 ./interfaceForm.ts
 * 等约定；ResourceImportPanel.tsx 含 JSX 无法被 Node 加载，故本模块独立成文件）。
 *
 * 语义的本地镜像（服务端为最终权威）：
 * - format（§2）：csv | xlsx（下拉恒合法；防御自由输入的非法值本地报错，
 *   不做大小写归一化——服务端对缺失 / 非法 format 返回 422 VALIDATION_ERROR
 *   field="format"，经 importFormFieldFromPath 映射到表单键）。
 * - file（§2）：必选；未选择文件 → 本地报错、不发起请求（空输入不发请求）。
 * - format=xlsx 仅接受 .xlsx 文件名（大小写不敏感）——服务端对 .xls / 非
 *   xlsx 返回 422 IMPORT_INVALID_FILE{unsupported_format}（§7），本地快速
 *   反馈；format=csv 不做扩展名限制（服务端按 UTF-8 解码，二进制内容报
 *   unreadable，仍以服务端错误为准）。
 * - 文件大小 > IMPORT_MAX_FILE_BYTES → 本地报错（服务端解析前 413
 *   IMPORT_FILE_TOO_LARGE 拦截；§10 签核值 5 MiB，服务端权威）。
 * - importTargetKey：file + format 的指纹（文件名 / 大小 / 修改时间 + 格式）。
 *   输入变化 → 既有预校验结果对当前输入失效（写入端点重新上传同一文件并
 *   完整重校验，§4/§8）；面板据 key 判断「预校验通过是否仍对当前输入有效」，
 *   产品规则：预校验存在错误行时整批不可能成功，不进入写入（§24-1）。
 * - 模板渲染辅助（§5/§6）：templateColumnTypeLabel 拼「类型 · 单位 / 枚举」
 *   展示文本（单位 MiB/GiB、枚举大写规范值原样呈现）；buildTemplateCsv 由
 *   templates 响应生成表头行 CSV 文本（DR-208：模板端点供前端查看与生成
 *   下载；.xlsx 模板使用相同表头，列名与顺序须与冻结模板完全一致）。
 */
import type { ImportColumnSpec, ImportFormat, ImportTemplate } from "../api/imports.ts";
import { IMPORT_MAX_FILE_BYTES } from "../api/imports.ts";

/** 导入表单可校验字段键（file 为本地必选校验；format 与服务端 422 field 同名）。 */
export type ImportFormFieldKey = "file" | "format";

/** 服务端 422 VALIDATION_ERROR 点路径全集（Contract §1.2/§2：format 缺失 / 非法）。 */
export type ImportServerFieldKey = "format";

/** 导入表单原始值（format 下拉恒合法；file 未选择为 null）。 */
export interface ImportFormValues {
  format: ImportFormat;
  file: File | null;
}

/** 本地校验错误（键为字段名，format 与服务端 422 fields 同名）。 */
export type ImportFormErrors = Partial<Record<ImportFormFieldKey, string>>;

/** 空白导入表单值（默认 CSV 格式、未选择文件）。 */
export function emptyImportFormValues(): ImportFormValues {
  return { format: "csv", file: null };
}

/** 服务端 422 点路径 → 表单字段键（仅 format；未知路径返回 null 不强行映射）。 */
export function importFormFieldFromPath(path: string): ImportFormFieldKey | null {
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
export function importTargetKey(values: Pick<ImportFormValues, "format" | "file">): string | null {
  if (values.file === null) {
    return null;
  }
  return `${values.format}:${values.file.name}:${values.file.size}:${values.file.lastModified}`;
}

/**
 * 解析导入表单值（本地快速反馈；服务端校验仍权威）：
 * - file 未选择 → 本地错误（空输入不发请求）；
 * - format 非 csv/xlsx → 本地错误（下拉恒合法，防御自由输入）；
 * - 文件大小超上限 → 本地错误（服务端 413 IMPORT_FILE_TOO_LARGE 同口径）；
 * - format=xlsx 且扩展名非 .xlsx（大小写不敏感）→ 本地错误
 *   （服务端 422 IMPORT_INVALID_FILE{unsupported_format} 同口径）。
 */
export function parseImportFormValues(
  values: ImportFormValues,
): { ok: true } | { ok: false; errors: ImportFormErrors } {
  const errors: ImportFormErrors = {};

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

/** 模板列「类型 · 单位 / 枚举」展示文本（单位 / 枚举原样呈现，§5/§6）。 */
export function templateColumnTypeLabel(column: ImportColumnSpec): string {
  let label = column.type;
  if (column.unit !== null) {
    label += ` · ${column.unit}`;
  }
  if (column.enum !== null && column.enum.length > 0) {
    label += `（${column.enum.join(" | ")}）`;
  }
  return label;
}

/** 模板列必填性展示文本（可选列空 = 省略，默认值生效，§6.3/DR-199）。 */
export function templateColumnRequiredLabel(column: ImportColumnSpec): string {
  return column.required ? "必填" : "可选（空 = 省略）";
}

/** 由模板生成表头行 CSV 文本（DR-208；.xlsx 模板使用相同表头与列序，§6.3）。 */
export function buildTemplateCsv(template: ImportTemplate): string {
  return `${template.columns.map((column) => column.name).join(",")}\n`;
}
