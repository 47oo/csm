/**
 * 导入输入载体原语（F034，Contract：docs/api/F014.md / docs/api/F023.md
 * §「CSV 文本载体（加法引用）」增补节 v1，READY 2026-10-26）。
 *
 * 纯逻辑模块（无 JSX / React / antd 依赖）：scripts/smoke-client.mjs 以 Node
 * type stripping 直接加载本模块做机制级冒烟（同 importForm.ts 约定）。
 *
 * 语义边界（architecture §1/§3.2/§3.4，DR-F034-02/03/04/08/09/15）：
 * - 载体只决定 multipart `file` 部分的**产生方式**：文本载体按 UTF-8 编码
 *   构造一个带固定文件名的 `File`，随既有 validate / 写入端点提交；端点、
 *   请求字段（`file` + `format`）、响应形状、错误码、上限、权限与原子性全部
 *   不变（服务端判定始终权威）。
 * - 固定文件名必须存在：`FormData.append("file", file, file.name)` 缺
 *   filename 会让服务端把该 part 解析成普通表单字段，得到误导性的
 *   422 VALIDATION_ERROR{field:"file"}（DR-F034-03）；服务端不读取 filename
 *   （只按 `data` + `format` 解析），固定名不进入任何错误文案或行号口径。
 * - 字节计量按 **UTF-8 编码后的字节数**（TextEncoder），而非 `String.length`
 *   的 UTF-16 code unit 数（DR-F034-04：含中文 / emoji 时两者不同）。
 * - 不做本地归一化（DR-F034-05）：不 trim 内容、不改行尾、不转义、不补尾部
 *   换行、不添加 BOM；若粘贴内容自带 `U+FEFF` 开头则原样提交（服务端按
 *   `utf-8-sig` 解码，与文件载体同口径）。
 * - 指纹（DR-F034-08/09）：`carrier:format:<payload>`；文本 payload 为
 *   内容摘要 + UTF-8 字节长度，任一文本变化（含非 ASCII 单字符）即换指纹，
 *   使既有预校验结果对当前输入失效（T116）。摘要为**同步**双 32 位非加密
 *   哈希（FNV-1a + djb2，均按 UTF-16 code unit 迭代）：不使用异步
 *   `crypto.subtle`（会破坏既有同步校验 / 门控时机），不新增 npm 依赖。
 *   摘要碰撞属理论风险，只是第二道防线：编辑路径本身已重置全部结果态，
 *   写入端点始终由服务端完整再校验。
 */
import type { ImportFormat } from "../api/imports.ts";

/** 导入输入载体（两入口并列：上传文件 / 粘贴 CSV 文本；DR-F034-01）。 */
export type ImportCarrier = "file" | "text";

/** 文本载体构造的 `File` 固定文件名（DR-F034-03：不掺时间戳 / 用户输入 / 摘要）。 */
export const PASTED_CSV_FILE_NAME = "csm-pasted-import.csv";

/** 文本载体构造的 `File` MIME 类型（UTF-8 CSV；不含 BOM，编码由 File 构造按 UTF-8 完成）。 */
export const PASTED_CSV_MIME_TYPE = "text/csv;charset=utf-8";

/**
 * 粘贴文本 → `File`（DR-F034-02/03/11）：每次调用都按当前文本重新构造，
 * 同一文本 ⇒ 同一字节序列 ⇒ 服务端对同一内容完整再校验。
 */
export function pastedCsvFile(text: string): File {
  return new File([text], PASTED_CSV_FILE_NAME, { type: PASTED_CSV_MIME_TYPE });
}

/** 文本的 UTF-8 编码字节数（非 `String.length`；与 `File.size` 同口径，显式计量以免依赖隐式编码假设）。 */
export function utf8ByteLength(text: string): number {
  return new TextEncoder().encode(text).length;
}

/** 空 / 纯空白内容判定（判定用 trim，但 payload 本身不 trim；DR-F034-05）。 */
export function isBlankImportText(text: string): boolean {
  return text.trim() === "";
}

/** FNV-1a 32 位哈希（按 UTF-16 code unit 迭代；`Math.imul` 保持 32 位语义）。 */
function fnv1a32(text: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash = Math.imul(hash ^ text.charCodeAt(index), 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/** djb2 32 位哈希（按 UTF-16 code unit 迭代；`Math.imul` 保持 32 位语义）。 */
function djb2_32(text: string): number {
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = (Math.imul(hash, 33) + text.charCodeAt(index)) >>> 0;
  }
  return hash >>> 0;
}

/**
 * 文本内容摘要 + UTF-8 字节长度（同步、无依赖；DR-F034-09）。
 * digest 为「FNV-1a 36 进制-djb2 36 进制」，与字节长度一起构成文本指纹 payload。
 */
export function importTextDigest(text: string): { digest: string; byteLength: number } {
  return {
    digest: `${fnv1a32(text).toString(36)}-${djb2_32(text).toString(36)}`,
    byteLength: utf8ByteLength(text),
  };
}

/**
 * 文件载体指纹（DR-F034-08）：`file:<format>:<name>:<size>:<lastModified>`。
 * 语义与 F014/F023 改动前的 `${format}:${name}:${size}:${lastModified}` 等价，
 * 只增加 carrier 前缀（文件 / 文本载体互不串用旧结果）。
 */
export function fileImportTargetKey(format: ImportFormat, file: File): string {
  return `file:${format}:${file.name}:${file.size}:${file.lastModified}`;
}

/** 文本载体指纹（DR-F034-08）：`text:csv:<digest>:<byteLength>`（format 恒为 csv）。 */
export function textImportTargetKey(text: string): string {
  const { digest, byteLength } = importTextDigest(text);
  return `text:csv:${digest}:${byteLength}`;
}
