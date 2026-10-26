import { Button, Input, Select, TextArea, DataTable } from "./ui/controls";
import { Alert } from "antd";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { SurfaceCard } from "./ui/surfaces";
import { useEffect, useState } from "react";
import { displayError, isApiError } from "../api/client";
import {
  describeImportError,
  getResourceInterfaceIpImportTemplate,
  IMPORT_MAX_FILE_BYTES,
  IMPORT_MAX_ROWS,
  importResourceInterfacesIps,
  validateResourceInterfaceIpImport,
  type ImportActionError,
  type ImportFormat,
  type ImportValidateResponse,
  type ResourceInterfaceIpImportResponse,
  type ResourceInterfaceIpTemplatesResponse,
} from "../api/imports";
import { ImportErrorsTable } from "./ImportErrorsTable";
import {
  buildResourceInterfaceIpTemplateHeaderCsv,
  canConfirmResourceInterfaceIpImport,
  emptyResourceInterfaceIpImportFormValues,
  RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS,
  resourceInterfaceIpColumnAppliesToLabel,
  resourceInterfaceIpColumnTypeLabel,
  resourceInterfaceIpColumnRequiredLabel,
  resourceInterfaceIpImportCarrierPatch,
  resourceInterfaceIpImportFormFieldFromPath,
  resourceInterfaceIpImportTargetKey,
  parseResourceInterfaceIpImportFormValues,
  resourceInterfaceIpTemplateHeaderCsvFrom,
  type ResourceInterfaceIpImportFormErrors,
  type ResourceInterfaceIpImportFormValues,
} from "./resourceInterfaceIpImportForm";
import {
  PASTED_CSV_FILE_NAME,
  utf8ByteLength,
  type ImportCarrier,
} from "./importCarrier";

/** 预校验结果状态（四态：idle 空态 / loading / success 含结果 / error；Contract §3）。 */
type ValidateState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: ImportValidateResponse }
  | { kind: "error"; described: ImportActionError };

/** 写入结果状态（成功 / 整批失败 / 其他错误；无部分成功语义，Contract §4/§12.1）。 */
type ImportState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: ResourceInterfaceIpImportResponse }
  | { kind: "error"; described: ImportActionError };

/** 模板加载状态（READ 全角色；懒加载，首次展开时获取；错误仅 401/500/网络层，§5）。 */
type TemplateState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: ResourceInterfaceIpTemplatesResponse }
  | { kind: "error"; message: string };

interface ResourceInterfaceIpImportPanelProps {
  /** 整批导入成功后通知父组件（如刷新资源列表）。 */
  onImported?: () => void;
}

/**
 * 「资源+网卡+IP」三元组批量导入面板（F023，Contract：docs/api/F023.md v1；
 * 产品 §24.1）：
 * - 两步流程：先「预校验」（只读、无副作用、不写 Audit、不加锁），一次性展示
 *   全部错误行（行号 / 字段 / 原因 / 关联行，可滚动）；预校验通过（0 错误）
 *   且输入指纹（文件 / 格式）一致后才能「确认导入」——存在错误行时整批不可
 *   能成功，不进入写入（§24-1）。
 * - 写入：服务端在同一事务内基于最新状态再次校验；任一行失败 → 整批回滚
 *   （422 IMPORT_VALIDATION_FAILED 明确提示「未创建任何资源、网卡或 IP」），
 *   成功 → 201 显示资源 / 网卡 / IP 创建数量；无部分成功 UI 语义（§4/§12.1）。
 * - 统一宽模板（§6 冻结 26 列，D03 签核）：单一模板、resource_type 逐行区分
 *   BM/VM、允许混排；模板查看 / 下载消费 GET /imports/resource-interfaces-ips/
 *   templates（§5），逐列说明含适用行、必填、类型、单位、枚举与示例；冻结
 *   表头文本另由本地镜像即时展示（列名 / 顺序与契约一致）。
 * - 输入（文件 / 格式）变化 → 既有预校验与写入结果全部失效重置，避免陈旧
 *   结果误导；同一文件重复确认由服务端按现存 (cluster,hostname)/(cluster,ip)
 *   冲突整批拒绝（§11）。
 * - 文件级错误（413 超限 / 422 IMPORT_INVALID_FILE 表头或格式不符 / 401 /
 *   403）与网络错误显式呈现，不伪装成空结果或 0 错误。
 * - 面板入口由 ResourcesPage 按 IMPORT 权限显示；隐藏不替代服务端校验
 *   （VIEWER 调用仍 403，§1.1）。
 * - F034 输入载体（Contract §「CSV 文本载体（加法引用）」增补节 v1）：
 *   「上传文件（CSV / .xlsx）」与「粘贴 CSV 文本（仅 CSV）」两种载体**并列**
 *   （默认文件载体，既有行为零改动）。文本载体按 UTF-8 编码构造带固定文件名
 *   的 `File`，走同一 multipart 端点；`format` 固定 csv 且只读；本地只做
 *   非权威前置拦截（空 / 纯空白、UTF-8 字节超上限），26 列表头与逗号分隔口径
 *   全由服务端权威判定（前端不解析 CSV、不补表头、不嗅探）。切换载体 /
 *   修改内容 / 修改格式一律重置预校验与写入结果（防陈旧结果，T116）。
 */
export default function ResourceInterfaceIpImportPanel({
  onImported,
}: ResourceInterfaceIpImportPanelProps) {
  const [values, setValues] = useState<ResourceInterfaceIpImportFormValues>(
    emptyResourceInterfaceIpImportFormValues,
  );
  const [localErrors, setLocalErrors] = useState<ResourceInterfaceIpImportFormErrors>({});
  const [validateState, setValidateState] = useState<ValidateState>({ kind: "idle" });
  const [importState, setImportState] = useState<ImportState>({ kind: "idle" });
  /** 预校验通过时的输入指纹（文件 / 格式变化后失效）。 */
  const [validatedKey, setValidatedKey] = useState<string | null>(null);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateState, setTemplateState] = useState<TemplateState>({ kind: "idle" });
  const [templatesReloadToken, setTemplatesReloadToken] = useState(0);

  const busy = validateState.kind === "loading" || importState.kind === "loading";

  // 模板加载（懒加载：首次展开「查看模板」时获取；READ 全角色、幂等）
  useEffect(() => {
    if (!showTemplates) {
      return;
    }
    let cancelled = false;
    setTemplateState({ kind: "loading" });
    getResourceInterfaceIpImportTemplate()
      .then((data) => {
        if (!cancelled) {
          setTemplateState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setTemplateState({
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
  function changeInput(patch: Partial<ResourceInterfaceIpImportFormValues>) {
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
    const parsed = parseResourceInterfaceIpImportFormValues(values);
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
      const data = await validateResourceInterfaceIpImport(file, values.format);
      setValidateState({ kind: "success", data });
      setValidatedKey(resourceInterfaceIpImportTargetKey(values));
      setImportState({ kind: "idle" });
    } catch (error: unknown) {
      setValidateState({
        kind: "error",
        described: describeImportError(error, "resource-interfaces-ips"),
      });
      setValidatedKey(null);
    }
  }

  async function handleImport() {
    if (busy || !canConfirm) {
      return;
    }
    // 写入时按当前载体重新构造 / 重取 File（不缓存字节，DR-F034-11）
    const parsed = parseResourceInterfaceIpImportFormValues(values);
    if (!parsed.ok) {
      setLocalErrors(parsed.errors);
      setValidatedKey(null);
      return;
    }
    setImportState({ kind: "loading" });
    try {
      const data = await importResourceInterfacesIps(parsed.file, values.format);
      setImportState({ kind: "success", data });
      onImported?.();
    } catch (error: unknown) {
      setImportState({
        kind: "error",
        described: describeImportError(error, "resource-interfaces-ips"),
      });
    }
  }

  /**
   * 确认导入可用条件（门控纯逻辑见 canConfirmResourceInterfaceIpImport）：
   * 当前输入已完成预校验且 0 错误（存在错误行时整批不可能成功，不进入写入）
   * 且指纹一致（防止「换了文件但沿用旧校验结果」）；本次导入已成功后禁用
   * （同一文件再导入会因现存冲突被服务端整批拒绝，§11；换文件需重新预校验）。
   */
  const currentKey = resourceInterfaceIpImportTargetKey(values);
  /** 文本载体下非权威 UTF-8 字节计数（纯展示，不参与门控；上限以服务端为准）。 */
  const pastedByteLength = values.carrier === "text" ? utf8ByteLength(values.text) : 0;
  const carrierIsText = values.carrier === "text";
  const canConfirm = canConfirmResourceInterfaceIpImport({
    validated:
      validateState.kind === "success" ? { errorCount: validateState.data.error_count } : null,
    validatedKey,
    currentKey,
    importSucceeded: importState.kind === "success",
  });

  // 服务端 422 VALIDATION_ERROR 字段错误（field="format"）→ 表单字段级呈现
  const serverFormatError: string | null = (() => {
    for (const state of [validateState, importState]) {
      if (state.kind !== "error") {
        continue;
      }
      for (const [path, message] of Object.entries(state.described.fields)) {
        if (resourceInterfaceIpImportFormFieldFromPath(path) === "format") {
          return message;
        }
      }
    }
    return null;
  })();

  /** 由 templates 响应生成表头行 CSV 下载（§5/DR-427；.xlsx 模板使用相同表头）。 */
  function downloadTemplateCsv(columnNames: readonly string[]) {
    const blob = new Blob([resourceInterfaceIpTemplateHeaderCsvFrom(columnNames)], {
      type: "text/csv;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "csm-import-template-resource_interfaces_ips.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <SurfaceCard className="panel">
      <h2>批量导入资源+网卡+IP（CSV / Excel .xlsx，仅新增）</h2>
      <p className="permissions-note">
        三元组导入：每行一个「资源 + 网卡 + IP」；同一 hostname 多行合并为一个资源、
        同一资源内网卡按 name 去重、每行对应一个 IP。两步导入：先「预校验」（只读，
        不写入任何数据、不写审计），一次性查看全部错误行；预校验通过（0 错误）后
        「确认导入」，服务端将在写入前基于最新状态再次校验，任一行失败整批回滚
        （不产生部分成功，未创建任何资源、网卡或 IP）。同步导入上限：单文件 ≤{" "}
        {IMPORT_MAX_FILE_BYTES} 字节（5 MiB）、数据行数 ≤ {IMPORT_MAX_ROWS}（超限在解析前拒绝）。
      </p>

      <div className="form-field">
        <label htmlFor="resource-interface-ip-import-carrier">导入载体（必选）</label>
        <Select
          id="resource-interface-ip-import-carrier"
          value={values.carrier}
          onChange={(event) =>
            changeInput(
              resourceInterfaceIpImportCarrierPatch(values, event.target.value as ImportCarrier),
            )
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
        <label htmlFor="resource-interface-ip-import-format">文件格式（必选）</label>
        <Select
          id="resource-interface-ip-import-format"
          value={values.format}
          onChange={(event) => changeInput({ format: event.target.value as ImportFormat })}
          disabled={busy || carrierIsText}
          aria-describedby={
            carrierIsText ? "resource-interface-ip-import-format-locked" : undefined
          }
        >
          <option value="csv">CSV（UTF-8，逗号分隔，兼容 BOM）</option>
          <option value="xlsx">Excel（.xlsx，取首个工作表，不执行公式 / 宏）</option>
        </Select>
        {carrierIsText && (
          <p className="permissions-note" id="resource-interface-ip-import-format-locked">
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
          <label htmlFor="resource-interface-ip-import-text">粘贴 CSV 文本（必填，仅 CSV）</label>
          <TextArea
            id="resource-interface-ip-import-text"
            className="import-carrier-textarea"
            value={values.text}
            rows={10}
            spellCheck={false}
            placeholder={"cluster,hostname,resource_type,role,status,...,network,ip\nN96P,cn001,BARE_METAL,COMPUTE,ACTIVE,..."}
            onChange={(event) => changeInput({ text: event.target.value })}
            disabled={busy}
            aria-describedby={
              "resource-interface-ip-import-text-hint resource-interface-ip-import-text-counter"
            }
            aria-invalid={localErrors.text ? true : undefined}
          />
          <p className="import-carrier-hint" id="resource-interface-ip-import-text-hint">
            仅逗号分隔（不做分隔符嗅探，制表符分隔不会被受理）；必须包含与冻结{" "}
            {RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS.length} 列统一宽模板逐字逐序一致的表头
            （可先展开「查看模板与逐列说明」复制表头列名或下载 CSV 模板表头行），不自动补表头、
            不按列名重排；内容按 UTF-8 提交，前端不做 trim / 行尾 / 转义改写。
          </p>
          <p className="import-carrier-counter" id="resource-interface-ip-import-text-counter">
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
          <label htmlFor="resource-interface-ip-import-file">导入文件（必选）</label>
          <Input
            id="resource-interface-ip-import-file"
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
          <h3 className="detail-section-title">
            导入模板（统一宽模板，表头第 1 行，{RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS.length}{" "}
            列列名与顺序冻结）
          </h3>
          <p className="permissions-note">
            单一统一宽模板，resource_type 逐行区分 BARE_METAL / VIRTUAL_MACHINE，同一文件
            允许混排（不适用该行类型的列必须留空）。表头须与模板列名、顺序完全一致
            （缺失 / 多余 / 顺序不符会被拒绝，不按列名重排）；可选列留空 = 省略（默认值
            生效，非必填 → null）；枚举取大写规范值。memory_mb 单位 MiB、disk_gb 单位
            GiB、speed_mbps 单位 Mbps、mtu 单位 bytes（未知留空存 null，不以 0 代替）。
            network 列引用同集群已存在 Network（名称或 CIDR），留空时由 ip 的 /掩码
            解析；Network 不存在则整批失败（不创建 Network / IP 池 / 集群 / 宿主机）。
            .xlsx 文件取首个工作表，表头与 CSV 模板一致。
          </p>
          <div className="import-template-header">
            <p>
              表头列名（{RESOURCE_INTERFACE_IP_TEMPLATE_COLUMNS.length} 列，顺序冻结，可直接复制）：
            </p>
            <pre className="import-template-header-text mono">
              {buildResourceInterfaceIpTemplateHeaderCsv().trimEnd()}
            </pre>
          </div>

          {templateState.kind === "loading" && <LoadingState label="正在加载模板规范…" />}

          {templateState.kind === "error" && (
            <ErrorState
              message={`加载模板规范失败：${templateState.message}`}
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

          {templateState.kind === "success" && (
            <div className="import-template-block">
              <div className="table-toolbar">
                <h3>
                  统一宽模板（{templateState.data.template.columns.length} 列）
                </h3>
                <Button
                  type="button"
                  onClick={() =>
                    downloadTemplateCsv(
                      templateState.data.template.columns.map((column) => column.name),
                    )
                  }
                >
                  下载 CSV 模板（表头行）
                </Button>
              </div>
              <div className="table-wrap">
                <DataTable className="data-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>列名</th>
                      <th>适用行</th>
                      <th>必填</th>
                      <th>类型 · 单位 / 枚举</th>
                      <th>说明</th>
                      <th>示例</th>
                    </tr>
                  </thead>
                  <tbody>
                    {templateState.data.template.columns.map((column, index) => (
                      <tr key={column.name}>
                        <td className="mono">{index + 1}</td>
                        <td className="mono">{column.name}</td>
                        <td>{resourceInterfaceIpColumnAppliesToLabel(column)}</td>
                        <td>{resourceInterfaceIpColumnRequiredLabel(column)}</td>
                        <td className="import-col-type">
                          {resourceInterfaceIpColumnTypeLabel(column)}
                        </td>
                        <td className="import-col-desc">{column.description}</td>
                        <td className="mono">{column.example}</td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              </div>
            </div>
          )}
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
          description={`导入成功：新建资源 ${importState.data.created} 个、网卡 ${importState.data.interfaces_created} 个、IP ${importState.data.ip_addresses_created} 个（共 ${importState.data.total_rows} 行，整批成功）。如需导入另一批，请重新选择文件或粘贴文本并预校验。`}
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
