import { useState } from "react";
import { Alert, Button, Form, Input, Select } from "antd";
import type { Cluster, ClusterActionError, ClusterStatus } from "../api/clusters";

/** 表单原始值（均为字符串；metadata 为 JSON 文本，提交前本地校验并解析）。 */
export interface ClusterFormValues {
  code: string;
  name: string;
  status: ClusterStatus;
  description: string;
  metadata: string;
}

/** 本地校验错误（服务端 422 / 409 字段错误由 serverError.fields 呈现）。 */
interface ClusterFormLocalErrors {
  code?: string;
  name?: string;
  metadata?: string;
}

export type MetadataParseResult =
  | { ok: true; value: Record<string, unknown> }
  | { ok: false; message: string };

/**
 * metadata 输入解析：空文本视为空对象 {}（Contract §3：默认 {}，整值替换）；
 * 非空时必须是合法的 JSON 对象（不能是数组 / 标量）。
 */
export function parseMetadataText(text: string): MetadataParseResult {
  const trimmed = text.trim();
  if (trimmed === "") {
    return { ok: true, value: {} };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, message: "metadata 必须是合法的 JSON" };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { ok: false, message: "metadata 必须是 JSON 对象（不能是数组或标量）" };
  }
  return { ok: true, value: parsed as Record<string, unknown> };
}

interface ClusterFormProps {
  mode: "create" | "edit";
  /** edit 模式：被编辑的集群（code 只读展示，创建后不可修改，Contract §2.1）。 */
  cluster?: Cluster;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeClusterActionError 解析后传入）。 */
  serverError: ClusterActionError | null;
  onSubmit: (values: ClusterFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/**
 * F003 集群创建 / 编辑表单（Contract §2/§6.2/§6.4）：
 * - 创建：code/name 必填（本地非空校验，服务端为最终权威）；
 * - 编辑：code 只读展示（不可改），仅提交变化字段（由父组件构造 PATCH body）；
 * - description 留空 = 创建时省略 / 编辑时清空（显式 null）；
 * - metadata 留空视为 {}，非空必须为合法 JSON 对象；
 * - 409 VERSION_CONFLICT → 明确提示刷新后重改；409 CONFLICT unique_conflict
 *   → code 字段级错误；422 → details.fields 字段级错误。
 *
 * 迁移说明（AntD + Tailwind）：本地校验仍仅在提交时触发（不使用 antd rules），
 * 以保持原有行为——错误文案只在下次提交时更新，字段级错误优先级为本地 ?? 服务端。
 */
export default function ClusterForm({
  mode,
  cluster,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: ClusterFormProps) {
  const isCreate = mode === "create";
  const [code, setCode] = useState("");
  const [name, setName] = useState(cluster?.name ?? "");
  const [status, setStatus] = useState<ClusterStatus>(cluster?.status ?? "ACTIVE");
  const [description, setDescription] = useState(cluster?.description ?? "");
  const [metadataText, setMetadataText] = useState(
    cluster ? JSON.stringify(cluster.metadata, null, 2) : "",
  );
  const [localErrors, setLocalErrors] = useState<ClusterFormLocalErrors>({});

  function handleSubmit() {
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const errors: ClusterFormLocalErrors = {};
    if (isCreate && code.trim() === "") {
      errors.code = "code 不能为空（服务端会去除首尾空白后再校验）";
    }
    if (name.trim() === "") {
      errors.name = "name 不能为空（服务端会去除首尾空白后再校验）";
    }
    const metadata = parseMetadataText(metadataText);
    if (!metadata.ok) {
      errors.metadata = metadata.message;
    }
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    onSubmit({ code, name, status, description, metadata: metadataText });
  }

  const serverFields = serverError?.fields ?? {};
  const codeError = localErrors.code ?? serverFields.code;
  const nameError = localErrors.name ?? serverFields.name;
  const statusError = serverFields.status;
  const descriptionError = serverFields.description;
  const metadataError = localErrors.metadata ?? serverFields.metadata;

  return (
    <Form
      layout="vertical"
      colon={false}
      onFinish={handleSubmit}
      noValidate
      className="space-y-4"
    >
      {isCreate ? (
        <div>
          <label htmlFor="cluster-code" className="mb-1 block text-sm font-medium">
            code（唯一标识，创建后不可修改）
          </label>
          <Input
            id="cluster-code"
            name="code"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            disabled={submitting}
            status={codeError ? "error" : undefined}
            placeholder="如 N96P；允许中文，禁内部空白 / 控制字符，≤64 字符"
          />
          {codeError && (
            <p className="mt-1 text-sm text-red-600" role="alert">
              {codeError}
            </p>
          )}
        </div>
      ) : (
        <div>
          <span className="mb-1 block text-sm font-medium">code（创建后不可修改）</span>
          <p className="break-all font-mono">{cluster?.code}</p>
        </div>
      )}

      <div>
        <label htmlFor="cluster-name" className="mb-1 block text-sm font-medium">
          name（名称）
        </label>
        <Input
          id="cluster-name"
          name="name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          disabled={submitting}
          status={nameError ? "error" : undefined}
          placeholder="如 N96P 集群；允许中文与内部空格，≤255 字符"
        />
        {nameError && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {nameError}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="cluster-status" className="mb-1 block text-sm font-medium">
          status（状态）
        </label>
        <Select<ClusterStatus>
          id="cluster-status"
          value={status}
          onChange={(value) => setStatus(value)}
          disabled={submitting}
          status={statusError ? "error" : undefined}
          className="w-full"
          options={[
            { value: "ACTIVE", label: "ACTIVE（启用）" },
            { value: "INACTIVE", label: "INACTIVE（停用，仍可维护）" },
          ]}
        />
        {statusError && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {statusError}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="cluster-description" className="mb-1 block text-sm font-medium">
          description（描述，可选）
        </label>
        <Input.TextArea
          id="cluster-description"
          name="description"
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={submitting}
          status={descriptionError ? "error" : undefined}
          placeholder="可选；编辑时清空表示删除描述（显式置 null）"
        />
        {descriptionError && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {descriptionError}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="cluster-metadata" className="mb-1 block text-sm font-medium">
          metadata（JSON 对象，可选）
        </label>
        <Input.TextArea
          id="cluster-metadata"
          name="metadata"
          rows={5}
          value={metadataText}
          onChange={(event) => setMetadataText(event.target.value)}
          disabled={submitting}
          status={metadataError ? "error" : undefined}
          placeholder={'可选，例如 {"region": "shanghai"}；留空视为 {}'}
        />
        {metadataError && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {metadataError}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <Alert
          type="error"
          role="alert"
          message={`${serverError.message}${
            serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""
          }`}
          description={
            serverError.versionConflict && onRefresh ? (
              <Button htmlType="button" onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </Button>
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
