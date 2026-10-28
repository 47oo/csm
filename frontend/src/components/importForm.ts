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
 *
 * F034 增补（Contract：docs/api/F014.md §「CSV 文本载体（加法引用）」增补节
 * v1，READY 2026-10-26；architecture §3.1/§3.3/§3.4）：表单值增加载体维度
 * （`carrier` = file | text）与粘贴文本（`text`）。文本载体只改变 multipart
 * `file` 部分的产生方式，请求形状、端点、错误码、上限与权限不变；本地只
 * 拦截「空 / 纯空白」「UTF-8 字节超上限」「文本载体下 format 非 csv（防御）」
 * 三类，其余（表头 / 分隔符 / 行数 / CSV 语法 / 取值合法性）一律交服务端。
 * `carrier` 恒由 UI 下拉产生，`errors.carrier` 仅用于防御非法载体值。
 */
import type { ImportColumnSpec, ImportFormat, ImportTemplate } from "../api/imports.ts";
import { IMPORT_MAX_FILE_BYTES } from "../api/imports.ts";
import {
  fileImportTargetKey,
  isBlankImportText,
  pastedCsvFile,
  textImportTargetKey,
  utf8ByteLength,
  type ImportCarrier,
} from "./importCarrier.ts";

/** 导入表单可校验字段键（file / text 为本地输入校验；format 与服务端 422 field 同名）。 */
export type ImportFormFieldKey = "carrier" | "format" | "file" | "text";

/** 服务端 422 VALIDATION_ERROR 点路径全集（Contract §1.2/§2：format 缺失 / 非法）。 */
export type ImportServerFieldKey = "format";

/**
 * 导入表单原始值：
 * - carrier：输入载体（默认 "file"；文本载体与文件载体并列，不替换）；
 * - format：下拉恒合法；carrier="text" 时恒为 "csv"（UI 只读）；
 * - file：carrier="file" 时有效，未选择为 null；
 * - text：carrier="text" 时有效，原始粘贴内容（不 trim、不改写）。
 */
export interface ImportFormValues {
  carrier: ImportCarrier;
  format: ImportFormat;
  file: File | null;
  text: string;
}

/** 本地校验错误（键为字段名，format 与服务端 422 fields 同名）。 */
export type ImportFormErrors = Partial<Record<ImportFormFieldKey, string>>;

/** 空白导入表单值（默认文件载体、CSV 格式、未选择文件、文本为空）。 */
export function emptyImportFormValues(): ImportFormValues {
  return { carrier: "file", format: "csv", file: null, text: "" };
}

/**
 * 载体切换的表单补丁（DR-F034-07/10，F036 DR-F036-02）：
 * - 切到 "text" 强制 format="csv"（不提供 .xlsx 文本载体）；
 * - 切回 "file" 保留当前 format，**不回填**历史 xlsx（避免「以为在上传 xlsx
 *   实际是文本」类误判，切换后的旧结果由 changeInput 统一重置）。
 * - 切到 "file" 时置 `file: null`：文本载体下原生 file input 已卸载，切回后
 *   重挂载为空 ⇒ 界面显示「未选择文件」而 values.file 仍指旧文件，会让预校验
 *   结果与将要提交的内容不一致（F034-RV-01，§24.5 T116 忠实度）。清值后
 *   importTargetKey 返回 null，既有门控（validatedKey === currentKey）自动使
 *   「确认导入」不可用。
 */
export function importCarrierPatch(
  values: ImportFormValues,
  carrier: ImportCarrier,
): Partial<ImportFormValues> {
  if (carrier === "text") {
    return { carrier, format: "csv" };
  }
  return { carrier, format: values.format, file: null };
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
 * 输入指纹（载体感知，DR-F034-08）：用于判断既有预校验结果是否仍对当前
 * 输入有效（载体 / 格式 / 文件 / 文本任一变化即失效，需重新预校验）：
 * - 文件载体 → `file:<format>:<name>:<size>:<lastModified>`（语义与 F034 前
 *   等价，只加 carrier 前缀）；未选择文件 → null。
 * - 文本载体 → `text:csv:<digest>:<byteLength>`（任一字符变化即换指纹，含
 *   非 ASCII；T116）。空文本同样给出确定性指纹，但空内容由 parse* 本地
 *   拦截、永不进入预校验，因此不会产生可确认的陈旧结果。
 */
export function importTargetKey(
  values: Pick<ImportFormValues, "carrier" | "format" | "file" | "text">,
): string | null {
  if (values.carrier === "text") {
    return textImportTargetKey(values.text);
  }
  if (values.file === null) {
    return null;
  }
  return fileImportTargetKey(values.format, values.file);
}

/**
 * 解析导入表单值（本地快速反馈；服务端校验仍权威），并按当前载体给出
 * 实际要提交的 `File`（DR-F034-11：文本载体每次重新构造，不缓存字节）：
 *
 * 文件载体（既有三条本地校验不变）：
 * - file 未选择 → 本地错误（空输入不发请求）；
 * - 文件大小超上限 → 本地错误（服务端 413 IMPORT_FILE_TOO_LARGE 同口径）；
 * - format=xlsx 且扩展名非 .xlsx（大小写不敏感）→ 本地错误
 *   （服务端 422 IMPORT_INVALID_FILE{unsupported_format} 同口径）。
 *
 * 文本载体（DR-F034-05：仅这四项，其余交服务端）：
 * - 载体非法值（防御；UI 下拉恒合法）；
 * - 空 / 纯空白内容（trim 判定；payload 不 trim）→ 不发请求；
 * - UTF-8 字节数严格大于上限 → 不发请求（等于上限放行）；
 * - format 非 csv（防御；文本载体恒为 csv）。
 * **不**做 CSV 解析 / 表头校验 / 分隔符嗅探 / 补表头 / 行数镜像（DR-F034-06）。
 */
export function parseImportFormValues(
  values: ImportFormValues,
): { ok: true; file: File } | { ok: false; errors: ImportFormErrors } {
  const errors: ImportFormErrors = {};

  if (values.format !== "csv" && values.format !== "xlsx") {
    errors.format = "format 必须为 csv 或 xlsx（不接受其它自由输入值）";
  }

  if (values.carrier !== "file" && values.carrier !== "text") {
    // 防御非法载体值（UI 下拉恒合法，不新增业务规则）
    errors.carrier = "输入载体必须为「上传文件」或「粘贴 CSV 文本」（不接受其它值）";
  } else if (values.carrier === "text") {
    if (values.format !== "csv") {
      errors.format = "粘贴 CSV 文本仅支持 csv 格式（format 固定为 csv，不提供 .xlsx 文本载体）";
    }
    const byteLength = utf8ByteLength(values.text);
    if (isBlankImportText(values.text)) {
      errors.text = "粘贴内容为空或只有空白字符（空输入不会发起请求）";
    } else if (byteLength > IMPORT_MAX_FILE_BYTES) {
      errors.text =
        `粘贴内容超过同步导入大小上限（UTF-8 编码后 ${byteLength} 字节 > ${IMPORT_MAX_FILE_BYTES} 字节 ≈ 5 MiB）；` +
        "请拆分后重试（服务端同样在解析前拒绝 413 IMPORT_FILE_TOO_LARGE）";
    }
  } else {
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
  }

  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }

  if (values.carrier === "text") {
    return { ok: true, file: pastedCsvFile(values.text) };
  }
  if (values.file === null) {
    // 不可达（上方已拦截）；保留防御，避免返回空文件
    return { ok: false, errors: { file: "必须先选择要导入的文件（空输入不会发起请求）" } };
  }
  return { ok: true, file: values.file };
}

/**
 * 粘贴文本输入框的占位示例（DR-F036-04 / F034-RV-03）：
 * - 首行明确「片段」，避免被误当作完整表头照抄；
 * - 示例数据行只取冻结模板前 3 列（列数 ≤ 4，TD-I-7），**不**列全部 26 列，
 *   **不**用 `...` 模拟截断（那会被当成可照抄的省略写法）；
 * - 完整表头以「查看模板」的 templates 响应为准（§5/§6，DR-208）。
 */
export const IMPORT_TEXT_PLACEHOLDER =
  "示例片段（非完整表头，勿整段照抄；请先复制「查看模板」中的表头行）\n" +
  "cluster,hostname,resource_type\n" +
  "N96P,cn001,BARE_METAL";

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
