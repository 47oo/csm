/**
 * Import API（F014，Contract：docs/api/F014.md v1，READY；F023，Contract：
 * docs/api/F023.md v2，READY）。
 *
 * F014 端点（Contract §3/§4/§5）：
 * - POST /imports/resources/validate   预校验（IMPORT；无副作用幂等，不写 Audit）
 * - POST /imports/resources            写入（IMPORT；整批成功 201 或整批回滚 422）
 * - GET  /imports/resources/templates  模板规范（READ 全角色；只读幂等）
 *
 * F023 端点（「资源+网卡+IP」三元组导入，Contract §1/§3/§4/§5）：
 * - POST /imports/resource-interfaces-ips/validate   预校验（IMPORT；无副作用幂等）
 * - POST /imports/resource-interfaces-ips            写入（IMPORT；整批成功 201 或整批回滚 422）
 * - GET  /imports/resource-interfaces-ips/templates  统一宽模板规范（READ 全角色；
 *   template.key 恒为 "resource_interfaces_ips"，26 列冻结）
 *
 * 注意：
 * - validate / 写入端点均为 multipart/form-data（file 二进制 + format 字符串），
 *   经 requestUpload 发送（不手动设置 Content-Type，boundary 由 fetch 生成）；
 *   服务端不落盘、不留临时文件，写入端点重新上传同一文件并完整重校验
 *   （F014 §4/§8；F023 §2/§12.2）。
 * - 写入「整批成功或整批回滚」：F014 成功 201 {"created","total_rows"}；F023
 *   成功 201 {"created","total_rows","interfaces_created","ip_addresses_created"}
 *   （created=按 (cluster,hostname) 合并后的 Resource 数，§4）；存在行错误
 *   → 422 IMPORT_VALIDATION_FAILED（details 携带与预校验同形状的聚合错误列表），
 *   无部分成功语义（F014 §4；F023 §4/§12.1）。
 * - 文件级致命错误（超限 413 / 不可解析或表头不符 422 IMPORT_INVALID_FILE）无
 *   errors 列表；行级错误聚合返回，1-based 文件行号、field 为模板列名、
 *   related_row 指向文件内重复 / 组内冲突的另一行（F014 §1.2；F023 §1.2）。
 * - 401 / 403（permission|csrf）/ 422 VALIDATION_ERROR（format 缺失或非法）/
 *   500 沿用 F002 口径；页面呈现统一走 describeImportError（F023 经 scope
 *   参数区分整批回滚文案中的对象清单）。
 * - 上限复用 F014 签核值（契约值，服务端权威；本地仅快速反馈镜像）。
 * - 本文件 import 显式带 .ts 扩展名：scripts/smoke-client.mjs 以 Node
 *   type stripping 直接加载本模块做机制级冒烟（Vite 构建同样支持）。
 */
import {
  displayError,
  envelopeFieldErrors,
  isApiError,
  request,
  requestUpload,
  type ApiErrorDetails,
} from "./client.ts";

/** 导入文件格式（Contract §2：csv | xlsx，服务端大小写不敏感；本客户端恒发规范小写值）。 */
export type ImportFormat = "csv" | "xlsx";

/** 导入目标资源类型（Contract §5/§6：仅 BARE_METAL / VIRTUAL_MACHINE 两套模板，§9）。 */
export type ImportResourceType = "BARE_METAL" | "VIRTUAL_MACHINE";

/**
 * 行级错误（Contract §1.2 RowError）：
 * - row：1-based 文件行号（表头为第 1 行，数据自第 2 行；CSV 引号内换行按逻辑记录号计）；
 * - field：模板列名（非点路径）；
 * - related_row：文件内重复等场景指向的另一行行号，其余为 null。
 */
export interface ImportRowError {
  row: number;
  field: string;
  reason: string;
  related_row: number | null;
}

/**
 * 聚合校验结果：validate 200 响应体（§3）与 422 IMPORT_VALIDATION_FAILED
 * details（§4）的同形状子集。
 * - importable_rows = total_rows - 出现错误的数据行数；
 * - error_count 为错误项全量计数（非截断后条数）；errors_truncated=true 时
 *   errors 最多 import_error_preview_limit 条（§3/§10）。
 */
export interface ImportValidationResult {
  total_rows: number;
  importable_rows: number;
  error_count: number;
  errors: ImportRowError[];
  errors_truncated: boolean;
}

/** POST /imports/resources/validate 200 响应（合法解析，含行错误；无副作用，§3）。 */
export interface ImportValidateResponse extends ImportValidationResult {
  /** 规范化后的请求格式（csv / xlsx）。 */
  format: ImportFormat;
}

/** POST /imports/resources 201 响应（§4：整批成功；created == total_rows）。 */
export interface ImportCreateResponse {
  created: number;
  total_rows: number;
}

/** 模板列描述（Contract §5：冻结列名 / 必填 / 目标点路径 / 类型 / 单位 / 枚举 / 说明 / 示例）。 */
export interface ImportColumnSpec {
  name: string;
  required: boolean;
  target: string;
  type: "string" | "integer" | "enum";
  /** 单位（MiB / GiB），无单位为 null。 */
  unit: string | null;
  /** 枚举允许值（大写规范值），不适用为 null。 */
  enum: string[] | null;
  description: string;
  example: string;
}

/** 单套模板（Contract §5/§6：resource_type + 冻结顺序的列描述，§6.3 不可重排）。 */
export interface ImportTemplate {
  resource_type: ImportResourceType;
  columns: ImportColumnSpec[];
}

/** GET /imports/resources/templates 200 响应（Contract §5）。 */
export interface ImportTemplatesResponse {
  templates: ImportTemplate[];
}

/** 同步导入文件大小上限（Contract §10 D03 签核值 5,242,880 字节 = 5 MiB；服务端权威）。 */
export const IMPORT_MAX_FILE_BYTES = 5_242_880;

/** 同步导入数据行数上限（Contract §10：不含表头；服务端权威）。 */
export const IMPORT_MAX_ROWS = 5_000;

/** 错误预览上限（Contract §10：errors_truncated=true 时 errors 最多该条数）。 */
export const IMPORT_ERROR_PREVIEW_LIMIT = 1_000;

/** 构造 multipart 表单（Contract §2：file 二进制 + format 字符串，两写入端点共用）。 */
function buildImportFormData(file: File, format: ImportFormat): FormData {
  const data = new FormData();
  data.append("file", file, file.name);
  data.append("format", format);
  return data;
}

/** 预校验：POST /api/v1/imports/resources/validate（IMPORT；无副作用、幂等、不写 Audit、不加锁，§3）。 */
export function validateResourceImport(
  file: File,
  format: ImportFormat,
): Promise<ImportValidateResponse> {
  return requestUpload<ImportValidateResponse>("/imports/resources/validate", {
    body: buildImportFormData(file, format),
  });
}

/** 写入：POST /api/v1/imports/resources（IMPORT；整批成功 201 或整批回滚 422，§4）。 */
export function importResources(
  file: File,
  format: ImportFormat,
): Promise<ImportCreateResponse> {
  return requestUpload<ImportCreateResponse>("/imports/resources", {
    body: buildImportFormData(file, format),
  });
}

/** 模板规范：GET /api/v1/imports/resources/templates（READ 全角色；只读、无 Audit、幂等，§5）。 */
export function getImportTemplates(): Promise<ImportTemplatesResponse> {
  return request<ImportTemplatesResponse>("/imports/resources/templates");
}

// ---------------------------------------------------------------------------
// F023「资源+网卡+IP」三元组批量导入（Contract：docs/api/F023.md v2，READY）
// ---------------------------------------------------------------------------

/** F023 统一宽模板 key（Contract §5：templates 响应 template.key 恒为该字面量）。 */
export type ResourceInterfaceIpTemplateKey = "resource_interfaces_ips";

/** F023 模板列适用行类型（Contract §5/§6 applies_to；逐行由 resource_type 判定，允许混排）。 */
export type ResourceInterfaceIpColumnAppliesTo = "BARE_METAL" | "VIRTUAL_MACHINE";

/**
 * F023 模板列描述（Contract §5）：较 F014 ImportColumnSpec 增加 applies_to
 * （适用行类型清单，§6.1）；type 额外含 boolean（enabled 列，§6 #24）。
 */
export interface ResourceInterfaceIpColumnSpec {
  name: string;
  required: boolean;
  /** 适用行类型（两类均适用时同时列出，如 ["BARE_METAL","VIRTUAL_MACHINE"]）。 */
  applies_to: ResourceInterfaceIpColumnAppliesTo[];
  target: string;
  type: "string" | "integer" | "enum" | "boolean";
  /** 单位（MiB / GiB / Mbps / bytes），无单位为 null。 */
  unit: string | null;
  /** 枚举允许值（大写规范值），不适用为 null。 */
  enum: string[] | null;
  description: string;
  example: string;
}

/** F023 单套统一宽模板（Contract §5/§6：26 列冻结列名与顺序；resource_type 逐行区分 BM/VM）。 */
export interface ResourceInterfaceIpTemplate {
  key: ResourceInterfaceIpTemplateKey;
  columns: ResourceInterfaceIpColumnSpec[];
}

/** GET /imports/resource-interfaces-ips/templates 200 响应（Contract §5：单套模板，非数组）。 */
export interface ResourceInterfaceIpTemplatesResponse {
  template: ResourceInterfaceIpTemplate;
}

/**
 * POST /imports/resource-interfaces-ips 201 响应（Contract §4：整批成功）：
 * - created = 新建 Resource 对象数（按 (cluster,hostname) 合并后组数）；
 * - interfaces_created = 去重后 Interface 数（同资源按 name 去重）；
 * - ip_addresses_created = 新建 IP 数（每行恰 1 个，成功时 == total_rows）。
 */
export interface ResourceInterfaceIpImportResponse {
  created: number;
  total_rows: number;
  interfaces_created: number;
  ip_addresses_created: number;
}

/**
 * 预校验：POST /api/v1/imports/resource-interfaces-ips/validate（IMPORT；无副作用、
 * 幂等、不写 Audit、不加锁，Contract §3）。响应形状与 F014 validate 相同
 * （format/total_rows/importable_rows/error_count/errors/errors_truncated）。
 */
export function validateResourceInterfaceIpImport(
  file: File,
  format: ImportFormat,
): Promise<ImportValidateResponse> {
  return requestUpload<ImportValidateResponse>("/imports/resource-interfaces-ips/validate", {
    body: buildImportFormData(file, format),
  });
}

/**
 * 写入：POST /api/v1/imports/resource-interfaces-ips（IMPORT；同一事务内再校验，
 * 整批成功 201 或整批回滚 422 IMPORT_VALIDATION_FAILED，无部分成功，Contract §4/§12）。
 */
export function importResourceInterfacesIps(
  file: File,
  format: ImportFormat,
): Promise<ResourceInterfaceIpImportResponse> {
  return requestUpload<ResourceInterfaceIpImportResponse>("/imports/resource-interfaces-ips", {
    body: buildImportFormData(file, format),
  });
}

/**
 * 模板规范：GET /api/v1/imports/resource-interfaces-ips/templates（READ 全角色；
 * 只读、无 Audit、幂等，Contract §5）。单一统一宽模板（key=resource_interfaces_ips）。
 */
export function getResourceInterfaceIpImportTemplate(): Promise<
  ResourceInterfaceIpTemplatesResponse
> {
  return request<ResourceInterfaceIpTemplatesResponse>("/imports/resource-interfaces-ips/templates");
}

/** details 数值提取（缺失 / 非数值 → null，不伪造）。 */
function parseNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** details 字符串列表提取（缺失 / 形状不符 → 空数组，不伪造）。 */
function parseStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

/** RowError 解析（形状不符 → null，不伪造行错误）。 */
function parseRowError(value: unknown): ImportRowError | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const { row, field, reason, related_row } = value as Record<string, unknown>;
  if (typeof row !== "number" || typeof field !== "string" || typeof reason !== "string") {
    return null;
  }
  if (related_row !== null && typeof related_row !== "number") {
    return null;
  }
  return { row, field, reason, related_row };
}

/** 422 IMPORT_VALIDATION_FAILED details → 聚合校验结果（形状不符 → null，不伪造）。 */
function parseValidationResult(details: ApiErrorDetails): ImportValidationResult | null {
  const totalRows = parseNumber(details["total_rows"]);
  const importableRows = parseNumber(details["importable_rows"]);
  const errorCount = parseNumber(details["error_count"]);
  if (totalRows === null || importableRows === null || errorCount === null) {
    return null;
  }
  const errors = Array.isArray(details["errors"])
    ? details["errors"]
        .map(parseRowError)
        .filter((item): item is ImportRowError => item !== null)
    : [];
  return {
    total_rows: totalRows,
    importable_rows: importableRows,
    error_count: errorCount,
    errors,
    errors_truncated: details["errors_truncated"] === true,
  };
}

/** 字节数 → MiB 展示值（保留 1 位小数）。 */
function toMiB(bytes: number): string {
  return String(Math.round((bytes / 1_048_576) * 10) / 10);
}

/** IMPORT_INVALID_FILE 已知 reason 的文案（missing_columns/unknown_columns 由拼接补充）。 */
const IMPORT_INVALID_FILE_REASON_MESSAGES: Record<string, string> = {
  unreadable: "文件无法读取或解码（CSV 须为 UTF-8 编码，可含 BOM；请检查文件是否损坏）",
  unsupported_format:
    "不支持的文件格式：xlsx 仅接受 .xlsx（.xls 等旧格式不支持）；CSV 文件请选择 csv 格式上传",
  header_missing: "缺少表头：第 1 行必须是与模板完全一致的列名",
  empty_file: "文件没有数据行：表头之后至少需要一行数据",
  column_order: "列顺序与模板不一致：表头须与冻结模板的列名、顺序完全一致（不按列名自动重排）",
};

/** 导入错误呈现的批次范围：决定整批回滚文案中的对象清单（F014 / F023 端点不同）。 */
export type ImportErrorScope = "resources" | "resource-interfaces-ips";

/** 整批回滚文案的对象清单（F023 §4：Resource/Interface/IPAddress 整批回滚零残留）。 */
const IMPORT_ROLLBACK_LABELS: Record<ImportErrorScope, string> = {
  resources: "未创建任何资源",
  "resource-interfaces-ips": "未创建任何资源、网卡或 IP",
};

/**
 * 面向页面的导入错误描述（F014/F023 Contract §1.2/§3/§4；不抛出、不重试）：
 * - 422 IMPORT_VALIDATION_FAILED → validationFailed 携带整批回滚的行错误明细
 *   （与预校验 errors 同形状）；文案明确「整批回滚」与未创建的对象清单
 *   （scope 默认 F014「未创建任何资源」；F023 传 "resource-interfaces-ips"
 *   →「未创建任何资源、网卡或 IP」）；
 * - 422 IMPORT_INVALID_FILE → invalidFile 携带 reason 与缺失 / 未定义列清单；
 * - 413 → limitBytes / limitRows 携带 details 上限值；
 * - 422 VALIDATION_ERROR → fields（field="format" 缺失 / 非法）；
 * - 401 / 403（permission|csrf）/ 500 / 网络层错误 → 明确文案，错误不伪装成空结果。
 */
export interface ImportActionError {
  message: string;
  code: string | null;
  /** 422 IMPORT_VALIDATION_FAILED：整批回滚的行错误明细（形状不符为 null，不伪造）。 */
  validationFailed: ImportValidationResult | null;
  /** 422 IMPORT_INVALID_FILE：reason + 缺失 / 未定义列（形状不符时列表为空）。 */
  invalidFile: { reason: string; missingColumns: string[]; unknownColumns: string[] } | null;
  /** 413 IMPORT_FILE_TOO_LARGE details.limit_bytes（未知为 null）。 */
  limitBytes: number | null;
  /** 413 IMPORT_ROW_LIMIT_EXCEEDED details.limit_rows（未知为 null）。 */
  limitRows: number | null;
  /** 422 VALIDATION_ERROR 字段级错误（field="format"）。 */
  fields: Record<string, string>;
}

/** 把导入错误归类为页面可直接呈现的结构（不抛出、不重试；scope 见 ImportErrorScope）。 */
export function describeImportError(
  error: unknown,
  scope: ImportErrorScope = "resources",
): ImportActionError {
  if (!isApiError(error)) {
    // 网络层错误（fetch reject）：固定文案，不伪装成业务结果
    return {
      message: "无法连接服务器，请稍后重试",
      code: null,
      validationFailed: null,
      invalidFile: null,
      limitBytes: null,
      limitRows: null,
      fields: {},
    };
  }

  const result: ImportActionError = {
    message: displayError(error),
    code: error.code,
    validationFailed: null,
    invalidFile: null,
    limitBytes: null,
    limitRows: null,
    fields: {},
  };
  const details = error.details ?? {};

  if (error.status === 401) {
    result.message =
      "登录状态已失效（未登录或会话过期），请重新登录后再执行导入（AUTH_REQUIRED）。";
  } else if (error.status === 403) {
    result.message =
      details["reason"] === "csrf"
        ? "跨站请求被拒绝（FORBIDDEN/csrf）；请从本站页面重新发起导入。"
        : "没有导入权限（预校验与写入均需 EDITOR 或 ADMIN；FORBIDDEN/permission）。";
  } else if (error.status === 413 && error.code === "IMPORT_FILE_TOO_LARGE") {
    result.limitBytes = parseNumber(details["limit_bytes"]);
    result.message =
      `文件过大：超过同步导入大小上限` +
      (result.limitBytes !== null
        ? `（${result.limitBytes} 字节，约 ${toMiB(result.limitBytes)} MiB）`
        : "") +
      `；服务端已拒绝，未导入任何数据（IMPORT_FILE_TOO_LARGE）。`;
  } else if (error.status === 413 && error.code === "IMPORT_ROW_LIMIT_EXCEEDED") {
    result.limitRows = parseNumber(details["limit_rows"]);
    result.message =
      `数据行数超过同步导入上限` +
      (result.limitRows !== null ? `（${result.limitRows} 行）` : "") +
      `；服务端已拒绝，未导入任何数据（IMPORT_ROW_LIMIT_EXCEEDED）。`;
  } else if (error.status === 422 && error.code === "IMPORT_INVALID_FILE") {
    const reason = typeof details["reason"] === "string" ? details["reason"] : "";
    const missingColumns = parseStringList(details["missing_columns"]);
    const unknownColumns = parseStringList(details["unknown_columns"]);
    result.invalidFile = { reason, missingColumns, unknownColumns };
    let message =
      IMPORT_INVALID_FILE_REASON_MESSAGES[reason] ??
      `文件不满足导入模板要求（${reason !== "" ? reason : "未知原因"}）`;
    if (missingColumns.length > 0) {
      message += `；缺失列：${missingColumns.join("、")}`;
    }
    if (unknownColumns.length > 0) {
      message += `；未定义列：${unknownColumns.join("、")}`;
    }
    result.message = `${message}（IMPORT_INVALID_FILE）`;
  } else if (error.status === 422 && error.code === "IMPORT_VALIDATION_FAILED") {
    result.validationFailed = parseValidationResult(details);
    if (result.validationFailed !== null) {
      const failed = result.validationFailed;
      result.message =
        `整批失败：写入前再次校验发现 ${failed.error_count} 项错误` +
        `（共 ${failed.total_rows} 行，可导入 ${failed.importable_rows} 行），` +
        `已全部回滚，${IMPORT_ROLLBACK_LABELS[scope]}（IMPORT_VALIDATION_FAILED）。`;
    } else {
      result.message =
        `整批失败：写入前再次校验发现错误，已全部回滚，${IMPORT_ROLLBACK_LABELS[scope]}（IMPORT_VALIDATION_FAILED）。`;
    }
  } else if (error.status === 422 && error.code === "VALIDATION_ERROR") {
    result.fields = envelopeFieldErrors(error.details);
  }
  return result;
}
