import { useState } from "react";
import { Alert, Button, Form, Input, Select, Typography } from "antd";
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

  // AntD Form onFinish 已 preventDefault；提交入口行为与原生 form onSubmit 一致
  function handleSubmit() {
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
    <Form layout="vertical" colon={false} noValidate onFinish={handleSubmit}>
      {isCreate ? (
        <Form.Item
          htmlFor="service-resource"
          label="resource（所属资源，必填；创建后不可更改）"
          validateStatus={(resourceError ?? serverFields.resource) ? "error" : undefined}
          help={resourceError ?? serverFields.resource}
        >
          <Select
            id="service-resource"
            className="w-full"
            value={values.resource}
            onChange={(value: string) => setField("resource", value)}
            disabled={submitting}
            options={[
              { value: "", label: "请选择资源…" },
              ...resources.map((item) => ({
                value: item.id,
                label: `${item.hostname}（${item.cluster.code}）`,
              })),
            ]}
          />
        </Form.Item>
      ) : (
        <Form.Item
          htmlFor="service-resource-readonly"
          label="resource（所属资源，创建后不可更改）"
          validateStatus={serverFields.resource ? "error" : undefined}
          help={serverFields.resource}
        >
          <Typography.Text id="service-resource-readonly" className="font-mono">
            {currentResource !== null
              ? currentResource.hostname
              : "未知（资源引用缺失）"}
            {resourceMissing && (
              <span className="text-amber-600">（不在当前资源候选列表，如已软删）</span>
            )}
          </Typography.Text>
        </Form.Item>
      )}

      <Form.Item
        htmlFor="service-name"
        label="name（必填；大小写不敏感，同资源未删除唯一；允许中文与内部空格，≤255）"
        validateStatus={fieldError("name") ? "error" : undefined}
        help={fieldError("name")}
      >
        <Input
          id="service-name"
          value={values.name}
          onChange={(event) => setField("name", event.target.value)}
          disabled={submitting}
          placeholder="如 slurmd；与 Slurmd 视为同名；已软删服务不占用名称；跨资源允许同名"
        />
      </Form.Item>

      <Form.Item
        htmlFor="service-status"
        label="status（人工维护的登记状态；不由名称或外部监控推导 / 自动转换）"
        validateStatus={serverFields.status ? "error" : undefined}
        help={serverFields.status}
      >
        <Select
          id="service-status"
          className="w-full"
          value={values.status}
          onChange={(value: ServiceStatus) => setField("status", value)}
          disabled={submitting}
          options={[
            { value: "UNKNOWN", label: "UNKNOWN（状态未知，默认）" },
            { value: "RUNNING", label: "RUNNING（运行中，人工登记）" },
            { value: "STOPPED", label: "STOPPED（已停止，人工登记）" },
          ]}
        />
      </Form.Item>

      <Form.Item
        htmlFor="service-description"
        label="description（描述，可选）"
        validateStatus={serverFields.description ? "error" : undefined}
        help={serverFields.description}
      >
        <Input.TextArea
          id="service-description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          placeholder="可选，无长度上限；编辑时清空表示删除描述（显式置 null）"
        />
      </Form.Item>

      <Form.Item
        htmlFor="service-metadata"
        label="metadata（JSON 对象，可选，默认 {}；整值替换，Service 自有）"
        validateStatus={(metadataError ?? serverFields.metadata) ? "error" : undefined}
        help={metadataError ?? serverFields.metadata}
      >
        <Input.TextArea
          id="service-metadata"
          rows={4}
          value={values.metadata}
          onChange={(event) => setField("metadata", event.target.value)}
          disabled={submitting}
          placeholder='如 {"port": 6818}；留空 = {}；必须为 JSON 对象（不能是数组或标量）'
        />
      </Form.Item>

      {serverError && serverError.message && (
        <Alert
          type="error"
          className="mb-6"
          message={`${serverError.message}${
            serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""
          }`}
          description={
            unmappedServerFields.length > 0 ||
            serverError.references.length > 0 ||
            (serverError.versionConflict && onRefresh) ? (
              <div className="space-y-2">
                {unmappedServerFields.length > 0 && (
                  <ul className="list-disc pl-5">
                    {unmappedServerFields.map(({ path, message }) => (
                      <li key={path}>
                        {path}：{message}
                      </li>
                    ))}
                  </ul>
                )}
                {serverError.references.length > 0 && (
                  <ul className="list-disc pl-5">
                    {serverError.references.map((reference) => (
                      <li key={`${reference.object_type}-${reference.object_id}`}>
                        引用端点：{reference.label ?? reference.object_id}（{reference.object_type}）
                      </li>
                    ))}
                  </ul>
                )}
                {serverError.versionConflict && onRefresh && (
                  <Button htmlType="button" onClick={onRefresh} disabled={submitting}>
                    刷新最新数据（放弃本次未保存的修改，重做变更）
                  </Button>
                )}
              </div>
            ) : undefined
          }
        />
      )}

      <div className="flex gap-3">
        <Button type="primary" htmlType="submit" disabled={submitting}>
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </Button>
        <Button htmlType="button" onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </div>
    </Form>
  );
}
