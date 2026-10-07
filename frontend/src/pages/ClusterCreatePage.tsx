import { useState } from "react";
import type { User } from "../api/auth";
import {
  createCluster,
  describeClusterActionError,
  type Cluster,
  type ClusterActionError,
} from "../api/clusters";
import ClusterForm, { parseMetadataText, type ClusterFormValues } from "../components/ClusterForm";

interface ClusterCreatePageProps {
  user: User;
  onCancel: () => void;
  /** 创建成功（201），跳转到新集群详情。 */
  onCreated: (cluster: Cluster) => void;
}

/**
 * F003 集群创建页（Contract §6.2）：
 * - code / name 必填；status 默认 ACTIVE；description / metadata 可选；
 * - 409 CONFLICT{unique_conflict} → code 字段级错误（含软删占用）；
 * - 422 VALIDATION_ERROR → details.fields 字段级错误；403 → 明确提示。
 * 入口按钮已按 WRITE 隐藏；此处再显式拦截（服务端仍是权威）。
 */
export default function ClusterCreatePage({ user, onCancel, onCreated }: ClusterCreatePageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ClusterActionError | null>(null);

  function handleSubmit(values: ClusterFormValues) {
    if (!canWrite) {
      // 防御：权限数据过期等情况下明确提示，不发起注定失败的请求
      setError({
        message: "当前账号没有创建集群的权限（WRITE）。",
        code: "FORBIDDEN",
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
      });
      return;
    }
    const metadata = parseMetadataText(values.metadata);
    if (!metadata.ok) {
      return; // 表单本地校验已拦截，防御性返回
    }
    setSubmitting(true);
    setError(null);
    createCluster({
      code: values.code,
      name: values.name,
      status: values.status,
      ...(values.description.trim() === "" ? {} : { description: values.description }),
      ...(values.metadata.trim() === "" ? {} : { metadata: metadata.value }),
    })
      .then(({ cluster }) => {
        onCreated(cluster); // 201 Success → 跳转详情
      })
      .catch((err: unknown) => {
        // 409 CONFLICT unique_conflict / 422 / 403：明确呈现，不静默重试
        setError(describeClusterActionError(err));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  return (
    <section className="panel">
      <div className="table-toolbar">
        <h2>新建集群</h2>
        <button type="button" onClick={onCancel} disabled={submitting}>
          返回列表
        </button>
      </div>
      {!canWrite ? (
        <p className="status status-error" role="alert">
          当前账号没有创建集群的权限（WRITE，服务端鉴权为准）。
        </p>
      ) : (
        <ClusterForm
          mode="create"
          submitting={submitting}
          serverError={error}
          onSubmit={handleSubmit}
          onCancel={onCancel}
        />
      )}
    </section>
  );
}
