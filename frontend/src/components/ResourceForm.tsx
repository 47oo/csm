import { useState, type FormEvent } from "react";
import type {
  Resource,
  ResourceActionError,
  ResourceRole,
  ResourceStatus,
  ResourceType,
} from "../api/resources";
import type { Cluster } from "../api/clusters";
import { parseMetadataText } from "./ClusterForm";

/** 表单原始值（均为字符串；metadata 为 JSON 文本，提交前本地校验并解析）。 */
export interface ResourceFormValues {
  /** create：所选集群 UUID（下拉选择）；edit：不可改（原值透传，不上送）。 */
  cluster: string;
  hostname: string;
  resource_type: ResourceType;
  role: ResourceRole;
  status: ResourceStatus;
  description: string;
  metadata: string;
}

/** 本地校验错误（服务端 422 / 409 字段错误由 serverError.fields 呈现）。 */
interface ResourceFormLocalErrors {
  cluster?: string;
  hostname?: string;
  metadata?: string;
}

interface ResourceFormProps {
  mode: "create" | "edit";
  /** create 模式：供选择的集群列表（父组件已加载，仅未删除集群）。 */
  clusters?: Cluster[];
  /** edit 模式：被编辑的资源（cluster / resource_type 只读展示，创建后不可改，Contract §2.2）。 */
  resource?: Resource;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeResourceActionError 解析后传入）。 */
  serverError: ResourceActionError | null;
  onSubmit: (values: ResourceFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

const RESOURCE_TYPE_OPTIONS: { value: ResourceType; label: string }[] = [
  { value: "BARE_METAL", label: "BARE_METAL（物理机）" },
  { value: "VIRTUAL_MACHINE", label: "VIRTUAL_MACHINE（虚拟机）" },
];

const ROLE_OPTIONS: { value: ResourceRole; label: string }[] = [
  { value: "COMPUTE", label: "COMPUTE（计算）" },
  { value: "LOGIN", label: "LOGIN（登录）" },
  { value: "MANAGEMENT", label: "MANAGEMENT（管理）" },
  { value: "STORAGE", label: "STORAGE（存储）" },
  { value: "SERVICE", label: "SERVICE（服务）" },
  { value: "GPU", label: "GPU" },
  { value: "OTHER", label: "OTHER（其它，默认）" },
];

const STATUS_OPTIONS: { value: ResourceStatus; label: string }[] = [
  { value: "IDLE", label: "IDLE（空闲）" },
  { value: "ALLOC", label: "ALLOC（已分配）" },
  { value: "DOWN", label: "DOWN（故障）" },
  { value: "UNKNOWN", label: "UNKNOWN（未知，默认）" },
];

/**
 * F004 资源创建 / 编辑表单（Contract §2/§6.2/§6.4）：
 * - 创建：cluster / hostname / resource_type 必填（本地非空校验，服务端为最终权威）；
 *   role 默认 OTHER、status 默认 UNKNOWN（可选）；
 * - 编辑：cluster / resource_type 只读展示（不可改），仅提交变化字段（由父组件构造 PATCH body）；
 * - hostname 允许 Unicode，禁内部空白 / 控制字符，≤253（服务端归一化小写存储）；
 * - description 留空 = 创建时省略 / 编辑时清空（显式 null）；
 * - metadata 留空视为 {}，非空必须为合法 JSON 对象；
 * - 409 VERSION_CONFLICT → 明确提示刷新后重改；409 CONFLICT unique_conflict
 *   → hostname 字段级错误；422 → details.fields 字段级错误（cluster 固定 field="cluster"）。
 */
export default function ResourceForm({
  mode,
  clusters,
  resource,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: ResourceFormProps) {
  const isCreate = mode === "create";
  const [cluster, setCluster] = useState("");
  const [hostname, setHostname] = useState(resource?.hostname ?? "");
  const [resourceType, setResourceType] = useState<ResourceType>(
    resource?.resource_type ?? "BARE_METAL",
  );
  const [role, setRole] = useState<ResourceRole>(resource?.role ?? "OTHER");
  const [status, setStatus] = useState<ResourceStatus>(resource?.status ?? "UNKNOWN");
  const [description, setDescription] = useState(resource?.description ?? "");
  const [metadataText, setMetadataText] = useState(
    resource ? JSON.stringify(resource.metadata, null, 2) : "",
  );
  const [localErrors, setLocalErrors] = useState<ResourceFormLocalErrors>({});

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const errors: ResourceFormLocalErrors = {};
    if (isCreate && cluster === "") {
      errors.cluster = "必须选择所属集群（服务端校验 cluster 存在且未删除）";
    }
    if (hostname.trim() === "") {
      errors.hostname = "hostname 不能为空（服务端会去除首尾空白后再校验）";
    }
    const metadata = parseMetadataText(metadataText);
    if (!metadata.ok) {
      errors.metadata = metadata.message;
    }
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    onSubmit({ cluster, hostname, resource_type: resourceType, role, status, description, metadata: metadataText });
  }

  const serverFields = serverError?.fields ?? {};

  return (
    <form onSubmit={handleSubmit} noValidate>
      {isCreate ? (
        <div className="form-field">
          <label htmlFor="resource-cluster">cluster（所属集群，必填，创建后不可修改）</label>
          <select
            id="resource-cluster"
            name="cluster"
            value={cluster}
            onChange={(event) => setCluster(event.target.value)}
            disabled={submitting}
          >
            <option value="">请选择集群</option>
            {(clusters ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.code} — {item.name}
              </option>
            ))}
          </select>
          {(localErrors.cluster ?? serverFields.cluster) && (
            <p className="field-error" role="alert">
              {localErrors.cluster ?? serverFields.cluster}
            </p>
          )}
        </div>
      ) : (
        <div className="form-field">
          <span className="field-label">cluster（创建后不可修改）</span>
          <p className="readonly-value mono">
            {resource?.cluster.code} — {resource?.cluster.name}
            <span className="unset">（id: {resource?.cluster.id}）</span>
          </p>
        </div>
      )}

      <div className="form-field">
        <label htmlFor="resource-hostname">hostname（必填；允许 Unicode 与“.”，禁内部空白 / 控制字符，≤253）</label>
        <input
          id="resource-hostname"
          name="hostname"
          type="text"
          value={hostname}
          onChange={(event) => setHostname(event.target.value)}
          disabled={submitting}
          placeholder="如 cn001；服务端归一化为小写存储，同集群内唯一"
        />
        {(localErrors.hostname ?? serverFields.hostname) && (
          <p className="field-error" role="alert">
            {localErrors.hostname ?? serverFields.hostname}
          </p>
        )}
      </div>

      {isCreate ? (
        <div className="form-field">
          <label htmlFor="resource-type">resource_type（必填，创建后不可修改）</label>
          <select
            id="resource-type"
            name="resource_type"
            value={resourceType}
            onChange={(event) => setResourceType(event.target.value as ResourceType)}
            disabled={submitting}
          >
            {RESOURCE_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {serverFields.resource_type && (
            <p className="field-error" role="alert">
              {serverFields.resource_type}
            </p>
          )}
        </div>
      ) : (
        <div className="form-field">
          <span className="field-label">resource_type（创建后不可修改）</span>
          <p className="readonly-value mono">{resource?.resource_type}</p>
        </div>
      )}

      <div className="form-field">
        <label htmlFor="resource-role">role（角色，可选，默认 OTHER）</label>
        <select
          id="resource-role"
          name="role"
          value={role}
          onChange={(event) => setRole(event.target.value as ResourceRole)}
          disabled={submitting}
        >
          {ROLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {serverFields.role && (
          <p className="field-error" role="alert">
            {serverFields.role}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="resource-status">status（状态，可选，默认 UNKNOWN，人工维护）</label>
        <select
          id="resource-status"
          name="status"
          value={status}
          onChange={(event) => setStatus(event.target.value as ResourceStatus)}
          disabled={submitting}
        >
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {serverFields.status && (
          <p className="field-error" role="alert">
            {serverFields.status}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="resource-description">description（描述，可选）</label>
        <textarea
          id="resource-description"
          name="description"
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={submitting}
          placeholder="可选；编辑时清空表示删除描述（显式置 null）"
        />
        {serverFields.description && (
          <p className="field-error" role="alert">
            {serverFields.description}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="resource-metadata">metadata（JSON 对象，可选）</label>
        <textarea
          id="resource-metadata"
          name="metadata"
          rows={5}
          value={metadataText}
          onChange={(event) => setMetadataText(event.target.value)}
          disabled={submitting}
          placeholder={'可选，例如 {"rack": "R42"}；留空视为 {}'}
        />
        {(localErrors.metadata ?? serverFields.metadata) && (
          <p className="field-error" role="alert">
            {localErrors.metadata ?? serverFields.metadata}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div className="form-error status status-error" role="alert">
          <p>
            {serverError.message}
            {serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}
          </p>
          {serverError.versionConflict && onRefresh && (
            <p>
              <button type="button" onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </button>
            </p>
          )}
        </div>
      )}

      <div className="form-actions">
        <button type="submit" disabled={submitting}>
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </button>
        <button type="button" onClick={onCancel} disabled={submitting}>
          取消
        </button>
      </div>
    </form>
  );
}
