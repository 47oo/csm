import { useState, type FormEvent } from "react";
import type { Cluster } from "../api/clusters";
import type {
  Network,
  NetworkActionError,
  NetworkStatus,
} from "../api/networks";
import { parseMetadataText } from "./ClusterForm";
import {
  emptyNetworkFormValues,
  networkFormValuesFromNetwork,
  parseNetworkFormValues,
  type NetworkFormErrors,
  type NetworkFormValues,
} from "./networkForm";

interface NetworkFormProps {
  mode: "create" | "edit";
  /** 供选择的集群列表（父组件已加载；edit 模式下用于改所属集群）。 */
  clusters: Cluster[];
  /** edit 模式：被编辑的 Network。 */
  network?: Network;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeNetworkActionError 解析后传入）。 */
  serverError: NetworkActionError | null;
  onSubmit: (values: NetworkFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/**
 * Network 创建 / 编辑表单（F008，Contract §2/§6.2/§6.4）：
 * - cluster 选择器：创建必填（仅未删除集群，服务端校验存在/未软删，422
 *   field="cluster"）；编辑时允许改所属集群（有未删 Pool/IP 引用时服务端
 *   409 reference_exists）；当前集群不在候选（如已软删）时仍展示为选项，
 *   不静默丢失；
 * - name 必填（大小写不敏感、同 Cluster 未删唯一，软删后可复用，§2.1）；
 * - cidr 必填合法 IPv4 CIDR（host 位由服务端归一化，§2.2）；同 Cluster
 *   未删不重叠（INACTIVE 参与）由服务端 409 range_overlap 承载；
 * - gateway 可选 IPv4（属 CIDR 基础可用地址且非禁用范围由服务端校验）；
 * - status 默认 ACTIVE；auto_allocate 默认 false（仅控自动分配）；
 * - description 清空 = 删除描述（显式 null）；metadata 留空视为 {}；
 * - 422 点路径映射到对应输入；409 unique_conflict → name 字段级错误；
 *   409 range_overlap → cidr 字段级错误 + 重叠明细；409 VERSION_CONFLICT →
 *   提示刷新后重改（不静默重试）。
 */
export default function NetworkForm({
  mode,
  clusters,
  network,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: NetworkFormProps) {
  const isCreate = mode === "create";
  const [values, setValues] = useState<NetworkFormValues>(() =>
    isCreate ? emptyNetworkFormValues() : networkFormValuesFromNetwork(network ?? null),
  );
  const [localErrors, setLocalErrors] = useState<NetworkFormErrors>({});
  // metadata 本地校验错误单独存放（NetworkFormErrors 不含 metadata 键，
  // 服务端 422 field="metadata" 直接经 serverFields 呈现）
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [clusterError, setClusterError] = useState<string | null>(null);

  function setField<K extends keyof NetworkFormValues>(key: K, value: NetworkFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const parsed = parseNetworkFormValues(values);
    const errors: NetworkFormErrors = parsed.ok ? {} : parsed.errors;
    const metadata = parseMetadataText(values.metadata);
    const nextClusterError =
      values.cluster === "" ? "必须选择所属集群（服务端校验 cluster 存在且未删除）" : null;
    setLocalErrors(errors);
    setClusterError(nextClusterError);
    if (!metadata.ok) {
      setMetadataError(metadata.message);
      return;
    }
    setMetadataError(null);
    if (!parsed.ok || Object.keys(errors).length > 0 || nextClusterError !== null) {
      return;
    }
    onSubmit(values);
  }

  const serverFields = serverError?.fields ?? {};
  const currentCluster = network?.cluster ?? null;
  const clusterMissing =
    currentCluster !== null && !clusters.some((item) => item.id === currentCluster.id);

  function fieldError(key: keyof NetworkFormErrors): string | undefined {
    return localErrors[key] ?? serverFields[key];
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="form-field">
        <label htmlFor="network-cluster">cluster（所属集群，必填）</label>
        <select
          id="network-cluster"
          name="cluster"
          value={values.cluster}
          onChange={(event) => setField("cluster", event.target.value)}
          disabled={submitting}
        >
          <option value="">请选择集群…</option>
          {clusterMissing && currentCluster !== null && (
            <option value={currentCluster.id}>
              {currentCluster.code} — {currentCluster.name}（当前集群）
            </option>
          )}
          {clusters.map((item) => (
            <option key={item.id} value={item.id}>
              {item.code} — {item.name}
            </option>
          ))}
        </select>
        {(clusterError ?? serverFields.cluster) && (
          <p className="field-error" role="alert">
            {clusterError ?? serverFields.cluster}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="network-name">
          name（必填；大小写不敏感，同集群未删除唯一；允许中文与内部空格，≤255）
        </label>
        <input
          id="network-name"
          name="name"
          type="text"
          value={values.name}
          onChange={(event) => setField("name", event.target.value)}
          disabled={submitting}
          placeholder="如 MGMT；与 mgmt 视为同名；已软删网络不占用名称"
        />
        {fieldError("name") && (
          <p className="field-error" role="alert">
            {fieldError("name")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="network-cidr">
          cidr（必填；合法 IPv4 CIDR；同集群未删除网络不可重叠，INACTIVE 同样占用）
        </label>
        <input
          id="network-cidr"
          name="cidr"
          type="text"
          value={values.cidr}
          onChange={(event) => setField("cidr", event.target.value)}
          disabled={submitting}
          placeholder="如 10.0.0.0/24；host 位会被归一化为网络地址（10.0.0.5/24 → 10.0.0.0/24）"
        />
        {fieldError("cidr") && (
          <p className="field-error" role="alert">
            {fieldError("cidr")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="network-gateway">
          gateway（网关，可选 IPv4；须属该 CIDR 基础可用地址且非禁用范围）
        </label>
        <input
          id="network-gateway"
          name="gateway"
          type="text"
          value={values.gateway}
          onChange={(event) => setField("gateway", event.target.value)}
          disabled={submitting}
          placeholder="如 10.0.0.1；留空 = 未设置（null）；/32 网段必须留空"
        />
        {fieldError("gateway") && (
          <p className="field-error" role="alert">
            {fieldError("gateway")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="network-status">status（状态）</label>
        <select
          id="network-status"
          name="status"
          value={values.status}
          onChange={(event) => setField("status", event.target.value as NetworkStatus)}
          disabled={submitting}
        >
          <option value="ACTIVE">ACTIVE（启用，默认）</option>
          <option value="INACTIVE">INACTIVE（停用，禁止新增分配，仍参与 CIDR 重叠检查）</option>
        </select>
        {serverFields.status && (
          <p className="field-error" role="alert">
            {serverFields.status}
          </p>
        )}
      </div>

      <div className="form-field checkbox-field">
        <label htmlFor="network-auto-allocate">
          <input
            id="network-auto-allocate"
            name="auto_allocate"
            type="checkbox"
            checked={values.auto_allocate}
            onChange={(event) => setField("auto_allocate", event.target.checked)}
            disabled={submitting}
          />
          auto_allocate（允许自动分配 IP，默认关闭；不绕过 status 与地址约束）
        </label>
        {serverFields.auto_allocate && (
          <p className="field-error" role="alert">
            {serverFields.auto_allocate}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="network-description">description（描述，可选）</label>
        <textarea
          id="network-description"
          name="description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
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
        <label htmlFor="network-metadata">metadata（JSON 对象，可选；网络自有扩展，整值替换）</label>
        <textarea
          id="network-metadata"
          name="metadata"
          rows={5}
          value={values.metadata}
          onChange={(event) => setField("metadata", event.target.value)}
          disabled={submitting}
          placeholder={'可选，例如 {"vlan": 100}；留空视为 {}；与所属集群的 metadata 相互独立'}
        />
        {(metadataError ?? serverFields.metadata) && (
          <p className="field-error" role="alert">
            {metadataError ?? serverFields.metadata}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div className="form-error status status-error" role="alert">
          <p>
            {serverError.message}
            {serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}
          </p>
          {serverError.rangeConflicts.length > 0 && (
            <ul>
              {serverError.rangeConflicts.map((conflict) => (
                <li key={`${conflict.object_type}-${conflict.object_id}`}>
                  {conflict.object_type}
                  {conflict.label ? `：${conflict.label}` : ""}（{conflict.object_id}）
                </li>
              ))}
            </ul>
          )}
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