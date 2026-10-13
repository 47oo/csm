import { Button, Input, Select, TextArea } from "./ui/controls";
import { ErrorState } from "./ui/feedback";
import { useState, type FormEvent } from "react";
import type { Resource } from "../api/resources";
import type { Service, ServiceActionError, ServiceStatus } from "../api/services";
import { parseMetadataText } from "./ClusterForm";
import {
  emptyServiceFormValues,
  serviceFormFieldFromPath,
  serviceFormValuesFromService,
  parseServiceFormValues,
  type ServiceFieldKey,
  type ServiceFormErrors,
  type ServiceFormValues,
  type ServiceServerFieldKey,
} from "./serviceForm";

interface ServiceFormProps {
  mode: "create" | "edit";
  /** 供选择的 Resource 列表（父组件已加载，仅未删除；edit 模式下用于归属展示回退）。 */
  resources: Resource[];
  /** edit 模式：被编辑的服务。 */
  service?: Service;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeServiceActionError 解析后传入）。 */
  serverError: ServiceActionError | null;
  onSubmit: (values: ServiceFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/** 服务端字段错误经点路径映射后的键（Contract §2.3 顶层字段）。 */
type ServerFieldKey = ServiceServerFieldKey;

/**
 * Service 创建 / 编辑表单（F011，Contract §2/§6.2/§6.4）：
 * - resource 选择器：创建必填（仅未删除 Resource，服务端校验存在/未软删，
 *   422 field="resource"）；创建后不可改（DR-144），编辑时只读展示所属
 *   Resource hostname；当前 Resource 不在候选（如已软删）时仍展示其引用，
 *   不静默丢失；
 * - name 必填（大小写不敏感（仅 ASCII 折叠）、同 Resource 未删唯一、软删后
 *   可复用，§2.1；允许中文与内部普通空格且不自动合并，≤255 code point）；
 * - status ∈ {RUNNING, STOPPED, UNKNOWN} 默认 UNKNOWN（人工维护的登记状态、
 *   非探测、不由名称或外部监控推导/自动转换，§15/T21）；
 * - description 可选 nullable、无长度上限；清空 = 删除描述（显式 null）；
 * - metadata：JSON object、默认 {}、整值替换、Service 自有（DR-143）；
 * - 422 点路径经 serviceFormFieldFromPath 映射到对应输入，未知路径在通用
 *   错误区呈现（不静默丢弃）；409 unique_conflict{field:"name"} → name
 *   字段级错误；409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）。
 */
export default function ServiceForm({
  mode,
  resources,
  service,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: ServiceFormProps) {
  const isCreate = mode === "create";
  const [values, setValues] = useState<ServiceFormValues>(() =>
    isCreate ? emptyServiceFormValues() : serviceFormValuesFromService(service ?? null),
  );
  const [localErrors, setLocalErrors] = useState<ServiceFormErrors>({});
  const [resourceError, setResourceError] = useState<string | null>(null);
  const [metadataError, setMetadataError] = useState<string | null>(null);

  function setField<K extends keyof ServiceFormValues>(key: K, value: ServiceFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  // 服务端字段错误：点路径归一到表单键；未知路径保留原文在通用错误区呈现
  const serverFields: Partial<Record<ServerFieldKey, string>> = {};
  const unmappedServerFields: { path: string; message: string }[] = [];
  for (const [path, message] of Object.entries(serverError?.fields ?? {})) {
    const key = serviceFormFieldFromPath(path);
    if (key !== null) {
      serverFields[key] = message;
    } else {
      unmappedServerFields.push({ path, message });
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const parsed = parseServiceFormValues(values);
    const errors: ServiceFormErrors = parsed.ok ? {} : parsed.errors;
    const nextResourceError =
      isCreate && values.resource === ""
        ? "必须选择所属资源（服务端校验 resource 存在且未删除；创建后不可更改）"
        : null;
    const metadata = parseMetadataText(values.metadata);
    const nextMetadataError = metadata.ok ? null : metadata.message;
    setLocalErrors(errors);
    setResourceError(nextResourceError);
    setMetadataError(nextMetadataError);
    if (
      !parsed.ok ||
      Object.keys(errors).length > 0 ||
      nextResourceError !== null ||
      nextMetadataError !== null
    ) {
      return;
    }
    onSubmit(values);
  }

  const currentResource = service?.resource ?? null;
  const resourceMissing =
    currentResource !== null && !resources.some((item) => item.id === currentResource.id);

  function fieldError(key: ServiceFieldKey): string | undefined {
    return localErrors[key] ?? serverFields[key];
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {isCreate ? (
        <div className="form-field">
          <label htmlFor="service-resource">
            resource（所属资源，必填；创建后不可更改）
          </label>
          <Select
            id="service-resource"
            name="resource"
            value={values.resource}
            onChange={(event) => setField("resource", event.target.value)}
            disabled={submitting}
          >
            <option value="">请选择资源…</option>
            {resources.map((item) => (
              <option key={item.id} value={item.id}>
                {item.hostname}（{item.cluster.code}）
              </option>
            ))}
          </Select>
          {(resourceError ?? serverFields.resource) && (
            <p className="field-error" role="alert">
              {resourceError ?? serverFields.resource}
            </p>
          )}
        </div>
      ) : (
        <div className="form-field">
          <label htmlFor="service-resource-readonly">
            resource（所属资源，创建后不可更改）
          </label>
          <output id="service-resource-readonly" className="mono">
            {currentResource !== null
              ? currentResource.hostname
              : "未知（资源引用缺失）"}
            {resourceMissing && <span className="unset">（不在当前资源候选列表，如已软删）</span>}
          </output>
          {serverFields.resource && (
            <p className="field-error" role="alert">
              {serverFields.resource}
            </p>
          )}
        </div>
      )}

      <div className="form-field">
        <label htmlFor="service-name">
          name（必填；大小写不敏感，同资源未删除唯一；允许中文与内部空格，≤255）
        </label>
        <Input
          id="service-name"
          name="name"
          type="text"
          value={values.name}
          onChange={(event) => setField("name", event.target.value)}
          disabled={submitting}
          placeholder="如 slurmd；与 Slurmd 视为同名；已软删服务不占用名称；跨资源允许同名"
        />
        {fieldError("name") && (
          <p className="field-error" role="alert">
            {fieldError("name")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="service-status">
          status（人工维护的登记状态；不由名称或外部监控推导 / 自动转换）
        </label>
        <Select
          id="service-status"
          name="status"
          value={values.status}
          onChange={(event) => setField("status", event.target.value as ServiceStatus)}
          disabled={submitting}
        >
          <option value="UNKNOWN">UNKNOWN（状态未知，默认）</option>
          <option value="RUNNING">RUNNING（运行中，人工登记）</option>
          <option value="STOPPED">STOPPED（已停止，人工登记）</option>
        </Select>
        {serverFields.status && (
          <p className="field-error" role="alert">
            {serverFields.status}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="service-description">description（描述，可选）</label>
        <TextArea
          id="service-description"
          name="description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          placeholder="可选，无长度上限；编辑时清空表示删除描述（显式置 null）"
        />
        {serverFields.description && (
          <p className="field-error" role="alert">
            {serverFields.description}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="service-metadata">
          metadata（JSON 对象，可选，默认 {}；整值替换，Service 自有）
        </label>
        <TextArea
          id="service-metadata"
          name="metadata"
          rows={4}
          value={values.metadata}
          onChange={(event) => setField("metadata", event.target.value)}
          disabled={submitting}
          placeholder='如 {"port": 6818}；留空 = {}；必须为 JSON 对象（不能是数组或标量）'
        />
        {(metadataError ?? serverFields.metadata) && (
          <p className="field-error" role="alert">
            {metadataError ?? serverFields.metadata}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <ErrorState
          message={
            <div className="form-error">
              <p>{serverError.message}{serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}</p>
              {unmappedServerFields.length > 0 && (
                <ul>
                  {unmappedServerFields.map(({ path, message }) => <li key={path}>{path}：{message}</li>)}
                </ul>
              )}
              {serverError.references.length > 0 && (
                <ul>
                  {serverError.references.map((reference) => (
                    <li key={`${reference.object_type}-${reference.object_id}`}>
                      引用端点：{reference.label ?? reference.object_id}（{reference.object_type}）
                    </li>
                  ))}
                </ul>
              )}
            </div>
          }
          action={
            serverError.versionConflict && onRefresh ? (
              <Button type="button" onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </Button>
            ) : undefined
          }
        />
      )}

      <div className="form-actions">
        <Button type="submit" disabled={submitting}>
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </Button>
        <Button type="button" onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </div>
    </form>
  );
}
