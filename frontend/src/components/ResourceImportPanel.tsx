import { Button, Input, Select, TextArea, DataTable } from "./ui/controls";
import { Alert } from "antd";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { SurfaceCard } from "./ui/surfaces";
import { useEffect, useState } from "react";
import { displayError, isApiError } from "../api/client";
import {
  describeImportError,
  getImportTemplates,
  IMPORT_MAX_FILE_BYTES,
  IMPORT_MAX_ROWS,
  importResources,
  validateResourceImport,
  type ImportActionError,
  type ImportCreateResponse,
  type ImportFormat,
  type ImportTemplate,
  type ImportTemplatesResponse,
  type ImportValidateResponse,
} from "../api/imports";
import { ImportErrorsTable } from "./ImportErrorsTable";
import {
  buildTemplateCsv,
  emptyImportFormValues,
  importCarrierPatch,
  importFormFieldFromPath,
  importTargetKey,
  parseImportFormValues,
  templateColumnTypeLabel,
  templateColumnRequiredLabel,
  type ImportFormErrors,
  type ImportFormValues,
} from "./importForm";
import {
  PASTED_CSV_FILE_NAME,
  utf8ByteLength,
  type ImportCarrier,
} from "./importCarrier";

/** 预校验结果状态（四态：idle 空态 / loading / success 含结果 / error；§3）。 */
type ValidateState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: ImportValidateResponse }
  | { kind: "error"; described: ImportActionError };

/** 写入结果状态（成功 / 整批失败 / 其他错误；无部分成功语义，§4）。 */
type ImportState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: ImportCreateResponse }
  | { kind: "error"; described: ImportActionError };

/** 模板加载状态（READ 全角色；懒加载，首次展开时获取）。 */
type TemplatesState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: ImportTemplatesResponse }
  | { kind: "error"; message: string };

interface ResourceImportPanelProps {
  /** 整批导入成功后通知父组件（如刷新资源列表）。 */
  onImported?: () => void;
}

/**
 * 资源批量导入面板（F014，Contract：docs/api/F014.md v1；产品 §24/§2.2）：
 * - 两步流程：先「预校验」（只读、无副作用、不写 Audit），一次性展示全部
 *   错误行（行号 / 字段 / 原因 / 关联行，可滚动）；预校验通过（0 错误）后
 *   才能「确认导入」——存在错误行时整批不可能成功，不进入写入（§24-1）。
 * - 写入：服务端重新上传同一文件并在事务内基于最新状态再次校验；任一行
 *   失败 → 整批回滚（422 IMPORT_VALIDATION_FAILED 明确提示「未创建任何
 *   资源」），成功 → 201 显示创建数量；无部分成功 UI 语义（§4/I-1）。
 * - 输入（文件 / 格式）变化 → 既有预校验与写入结果全部失效重置，避免陈旧
 *   结果误导；同一文件重复确认由服务端按 hostname 冲突整批拒绝（A23）。
 * - 文件级错误（413 超限 / 422 IMPORT_INVALID_FILE 表头或格式不符 / 401 /
 *   403）与网络错误显式呈现，不伪装成空结果或 0 错误。
 * - 模板查看 / 下载（A25）：消费 GET /imports/resources/templates（DR-208），
 *   逐列说明含必填、类型、单位（MiB/GiB）、枚举与示例；可下载表头行 CSV。
 * - 面板入口由 ResourcesPage 按 IMPORT 权限显示；隐藏不替代服务端校验
 *   （VIEWER 调用仍 403，§1.1/I-11）。
 * - F034 输入载体（Contract §「CSV 文本载体（加法引用）」增补节 v1）：
 *   「上传文件（CSV / .xlsx）」与「粘贴 CSV 文本（仅 CSV）」两种载体**并列**
 *   （默认文件载体，既有行为零改动）。文本载体把粘贴内容按 UTF-8 编码构造为
 *   带固定文件名的 `File`，走同一 multipart 端点；`format` 固定 csv 且只读；
 *   本地只做非权威前置拦截（空 / 纯空白、UTF-8 字节超上限），表头与分隔符
 *   口径全由服务端权威判定（前端不解析 CSV、不补表头、不嗅探）。切换载体 /
 *   修改内容 / 修改格式一律重置预校验与写入结果（防陈旧结果，T116）。
 */
export default function ResourceImportPanel({ onImported }: ResourceImportPanelProps) {
  const [values, setValues] = useState<ImportFormValues>(emptyImportFormValues);
  const [localErrors, setLocalErrors] = useState<ImportFormErrors>({});
  const [validateState, setValidateState] = useState<ValidateState>({ kind: "idle" });
  const [importState, setImportState] = useState<ImportState>({ kind: "idle" });
  /** 预校验通过时的输入指纹（文件 / 格式变化后失效）。 */
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templatesState, setTemplatesState] = useState<TemplatesState>({ kind: "idle" });
  const [templatesReloadToken, setTemplatesReloadToken] = useState(0);

  const busy = validateState.kind === "loading" || importState.kind === "loading";

  // 模板加载（懒加载：首次展开「查看模板」时获取；READ 全角色、幂等）
  useEffect(() => {
    if (!showTemplates) {
      return;
    }
    let cancelled = false;
    setTemplatesState({ kind: "loading" });
    getImportTemplates()
      .then((data) => {
        if (!cancelled) {
          setTemplatesState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setTemplatesState({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [showTemplates, templatesReloadToken]);

  /** 输入变化：既有预校验 / 写入结果对当前输入不再适用，全部重置。 */
  function changeInput(patch: Partial<ImportFormValues>) {
    setValues((prev) => ({ ...prev, ...patch }));
    setLocalErrors({});
    setValidateState({ kind: "idle" });
    setImportState({ kind: "idle" });
    setValidatedKey(null);
  }

  async function handleValidate() {
    if (busy) {
      return;
    }
    const parsed = parseImportFormValues(values);
    if (!parsed.ok) {
      // 空输入 / 超限 / 格式不符：本地提示，不发起请求
      setLocalErrors(parsed.errors);
      setValidateState({ kind: "idle" });
      setValidatedKey(null);
      return;
    }
    // 按当前载体取实际提交的 File（文本载体为新建的 csm-pasted-import.csv）
    const file = parsed.file;
    setLocalErrors({});
    setValidateState({ kind: "loading" });
    try {
      const data = await validateResourceImport(file, values.format);
      setValidateState({ kind: "success", data });
      setValidatedKey(importTargetKey(values));
      setImportState({ kind: "idle" });
    } catch (error: unknown) {
      setValidateState({ kind: "error", described: describeImportError(error) });
      setValidatedKey(null);
    }
  }

  async function handleImport() {
    if (busy || !canConfirm) {
      return;
    }
    // 写入时按当前载体重新构造 / 重取 File（不缓存字节，DR-F034-11）
    const parsed = parseImportFormValues(values);
    if (!parsed.ok) {
      setLocalErrors(parsed.errors);
      setValidatedKey(null);
      return;
    }
    setImportState({ kind: "loading" });
    try {
      const data = await importResources(parsed.file, values.format);
      setImportState({ kind: "success", data });
      onImported?.();
    } catch (error: unknown) {
      setImportState({ kind: "error", described: describeImportError(error) });
    }
  }

  /**
   * 确认导入可用条件：当前输入已完成预校验且 0 错误（存在错误行时整批不可能
   * 成功，不进入写入，§24-1）；指纹一致防止「换了文件但沿用旧校验结果」；
   * 本次导入已成功后禁用（同一文件再导入会因 hostname 冲突被服务端整批
   * 拒绝，A23；换文件需重新预校验）。
   */
  const currentKey = importTargetKey(values);
  /** 文本载体下非权威 UTF-8 字节计数（纯展示，不参与门控；上限以服务端为准）。 */
  const pastedByteLength = values.carrier === "text" ? utf8ByteLength(values.text) : 0;
  const carrierIsText = values.carrier === "text";
  const validatePassed =
    validateState.kind === "success" &&
    validateState.data.error_count === 0 &&
    validatedKey !== null &&
    validatedKey === currentKey;
  const canConfirm = validatePassed && importState.kind !== "success";

  // 服务端 422 VALIDATION_ERROR 字段错误（field="format"）→ 表单字段级呈现
  const serverFormatError: string | null = (() => {
    for (const state of [validateState, importState]) {
      if (state.kind !== "error") {
        continue;
      }
      for (const [path, message] of Object.entries(state.described.fields)) {
        if (importFormFieldFromPath(path) === "format") {
          return message;
        }
      }
    }
    return null;
  })();

  /** 由 templates 响应生成表头行 CSV 下载（DR-208；xlsx 模板使用相同表头）。 */
  function downloadTemplateCsv(template: ImportTemplate) {
    const blob = new Blob([buildTemplateCsv(template)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `csm-import-template-${template.resource_type}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <SurfaceCard className="panel">
      <h2>批量导入资源（CSV / Excel .xlsx，仅新增）</h2>
      <p className="permissions-note">
        两步导入：先「预校验」（只读，不写入任何数据、不写审计），一次性查看全部错误行；
        预校验通过（0 错误）后「确认导入」，服务端将在写入前基于最新状态再次校验，
        任一行失败整批回滚，不产生部分成功。同步导入上限：单文件 ≤{" "}
        {IMPORT_MAX_FILE_BYTES} 字节（5 MiB）、数据行数 ≤ {IMPORT_MAX_ROWS}（超限在解析前拒绝）。
      </p>

      <div className="form-field">
        <label htmlFor="resource-import-carrier">导入载体（必选）</label>
        <Select
          id="resource-import-carrier"
          value={values.carrier}
          onChange={(event) =>
            changeInput(importCarrierPatch(values, event.target.value as ImportCarrier))
          }
          disabled={busy}
        >
          <option value="file">上传文件（CSV / .xlsx）</option>
          <option value="text">粘贴 CSV 文本（仅 CSV）</option>
        </Select>
        {localErrors.carrier && (
          <p className="field-error" role="alert">
            {localErrors.carrier}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="resource-import-format">文件格式（必选）</label>
        <Select
          id="resource-import-format"
          value={values.format}
          onChange={(event) => changeInput({ format: event.target.value as ImportFormat })}
          disabled={busy || carrierIsText}
          aria-describedby={carrierIsText ? "resource-import-format-locked" : undefined}
        >
          <option value="csv">CSV（UTF-8，逗号分隔，兼容 BOM）</option>
          <option value="xlsx">Excel（.xlsx，取首个工作表，不执行公式 / 宏）</option>
        </Select>
        {carrierIsText && (
          <p className="permissions-note" id="resource-import-format-locked">
            粘贴 CSV 文本时格式固定为 CSV（不提供 .xlsx 文本载体）。
          </p>
        )}
        {(localErrors.format ?? serverFormatError) && (
          <p className="field-error" role="alert">
            {localErrors.format ?? serverFormatError}
          </p>
        )}
      </div>

      {carrierIsText ? (
        <div className="form-field">
          <label htmlFor="resource-import-text">粘贴 CSV 文本（必填，仅 CSV）</label>
          <TextArea
            id="resource-import-text"
            className="import-carrier-textarea"
            value={values.text}
            rows={10}
            spellCheck={false}
            placeholder={"cluster,hostname,resource_type\nN96P,cn001,BARE_METAL"}
            onChange={(event) => changeInput({ text: event.target.value })}
            disabled={busy}
            aria-describedby="resource-import-text-hint resource-import-text-counter"
            aria-invalid={localErrors.text ? true : undefined}
          />
          <p className="import-carrier-hint" id="resource-import-text-hint">
            仅逗号分隔（不做分隔符嗅探，制表符分隔不会被受理）；必须包含与模板逐字逐序
            一致的表头（可先展开「查看模板与逐列说明」查看表头列名并下载 CSV 模板表头行），
            不自动补表头、不按列名重排；内容按 UTF-8 提交，前端不做 trim / 行尾 / 转义改写。
          </p>
          <p className="import-carrier-counter" id="resource-import-text-counter">
            UTF-8 字节数（非权威提示）：{pastedByteLength} /{" "}
            {IMPORT_MAX_FILE_BYTES.toLocaleString("en-US")}；以固定文件名（
            {PASTED_CSV_FILE_NAME}）与 text/csv 类型提交，服务端按同一上限值权威判定。
          </p>
          {localErrors.text && (
            <p className="field-error" role="alert">
              {localErrors.text}
            </p>
          )}
        </div>
      ) : (
        <div className="form-field">
          <label htmlFor="resource-import-file">导入文件（必选）</label>
          <Input
            id="resource-import-file"
            type="file"
            accept={values.format === "csv" ? ".csv" : ".xlsx"}
            onChange={(event) => changeInput({ file: event.target.files?.[0] ?? null })}
            disabled={busy}
          />
          {localErrors.file && (
            <p className="field-error" role="alert">
              {localErrors.file}
            </p>
          )}
        </div>
      )}

      <div className="form-actions">
        <Button type="button" onClick={handleValidate} disabled={busy}>
          {validateState.kind === "loading" ? "正在预校验…" : "预校验（不写入数据）"}
        </Button>
        <Button type="button" onClick={handleImport} disabled={!canConfirm || busy}>
          {importState.kind === "loading" ? "正在导入…" : "确认导入"}
        </Button>
        <Button
          type="button"
          onClick={() => setShowTemplates((visible) => !visible)}
          disabled={busy}
        >
          {showTemplates ? "收起模板说明" : "查看模板与逐列说明"}
        </Button>
      </div>

      {showTemplates && (
        <div className="import-templates">
          <h3 className="detail-section-title">导入模板（表头第 1 行，列名与顺序冻结）</h3>
          <p className="permissions-note">
            表头须与模板列名、顺序完全一致（缺失 / 多余 / 顺序不符会被拒绝，不按列名重排）；
            可选列留空 = 省略（默认值生效，非必填 → null）；枚举取大写规范值；
            memory_mb 单位 MiB、disk_gb 单位 GiB（未知留空存 null，不以 0 代替）。
            .xlsx 文件取首个工作表，表头与 CSV 模板一致。
          </p>

          {templatesState.kind === "loading" && <LoadingState label="正在加载模板规范…" />}

          {templatesState.kind === "error" && (
            <ErrorState
              message={`加载模板规范失败：${templatesState.message}`}
              action={
                <Button
                  type="button"
                  onClick={() => setTemplatesReloadToken((token) => token + 1)}
                >
                  重试
                </Button>
              }
            />
          )}

          {templatesState.kind === "success" &&
            (templatesState.data.templates.length === 0 ? (
              <EmptyState description="服务端未返回任何模板定义（与契约不符，请联系管理员核对后端版本）。" />
            ) : (
              templatesState.data.templates.map((template) => (
                <div key={template.resource_type} className="import-template-block">
                  <div className="table-toolbar">
                    <h3>
                      {template.resource_type} 模板（{template.columns.length} 列）
                    </h3>
                    <Button type="button" onClick={() => downloadTemplateCsv(template)}>
                      下载 CSV 模板（表头行）
                    </Button>
                  </div>
                  <div className="table-wrap">
                    <DataTable className="data-table">
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>列名</th>
                          <th>必填</th>
                          <th>类型 · 单位 / 枚举</th>
                          <th>说明</th>
                          <th>示例</th>
                        </tr>
                      </thead>
                      <tbody>
                        {template.columns.map((column, index) => (
                          <tr key={column.name}>
                            <td className="mono">{index + 1}</td>
                            <td className="mono">{column.name}</td>
                            <td>{templateColumnRequiredLabel(column)}</td>
                            <td className="import-col-type">
                              {templateColumnTypeLabel(column)}
                            </td>
                            <td className="import-col-desc">{column.description}</td>
                            <td className="mono">{column.example}</td>
                          </tr>
                        ))}
                      </tbody>
                    </DataTable>
                  </div>
                </div>
              ))
            ))}
        </div>
      )}

      <h3 className="detail-section-title">预校验结果</h3>

      {validateState.kind === "idle" && (
        <EmptyState description="尚未预校验。选择文件或粘贴 CSV 文本后点击「预校验」查看全部错误行（只读，不写入任何数据）。" />
      )}

      {validateState.kind === "loading" && (
        <LoadingState label="正在预校验（解析文件并逐行校验，不写入数据）…" />
      )}

      {validateState.kind === "error" && (
        <ErrorState message={`预校验失败：${validateState.described.message}`} />
      )}

      {validateState.kind === "success" && (
        <>
          <InfoState message={`预校验完成（${validateState.data.format}）：共 ${validateState.data.total_rows} 行数据，可导入 ${validateState.data.importable_rows} 行，错误 ${validateState.data.error_count} 项。`} />
          {validateState.data.errors_truncated && (
            <InfoState message={`错误较多：仅显示前 ${validateState.data.errors.length} 条（共 ${validateState.data.error_count} 项，超出服务端预览上限）；修复后请重新预校验。`} />
          )}
          {validateState.data.error_count === 0 ? (
            <Alert
              description="预校验通过：未发现行错误。可点击「确认导入」；写入时服务端将基于最新状态再次校验，若状态变化导致冲突仍会整批回滚。"
              showIcon
              type="success"
            />
          ) : (
            <>
              <ErrorState message={`预校验发现 ${validateState.data.error_count} 项错误：存在错误行时整批不可能成功，「确认导入」不可用；请修正文件后重新预校验。`} />
              <ImportErrorsTable result={validateState.data} />
            </>
          )}
        </>
      )}

      <h3 className="detail-section-title">写入结果</h3>

      {importState.kind === "idle" && (
        <EmptyState description="尚未导入（需先通过预校验）。" />
      )}

      {importState.kind === "loading" && (
        <LoadingState label="正在导入（事务内再次校验并整批写入）…" />
      )}

      {importState.kind === "success" && (
        <Alert
          description={`导入成功：已创建 ${importState.data.created} 条资源（共 ${importState.data.total_rows} 行，整批成功）。如需导入另一批资源，请重新选择文件或粘贴文本并预校验。`}
          showIcon
          type="success"
        />
      )}

      {importState.kind === "error" && (
        <>
          <ErrorState message={importState.described.message} />
          {importState.described.validationFailed !== null && (
            <ImportErrorsTable result={importState.described.validationFailed} />
          )}
        </>
      )}
    </SurfaceCard>
  );
}
