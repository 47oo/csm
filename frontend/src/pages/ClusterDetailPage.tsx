import { Button } from "../components/ui/controls";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { ErrorState, LoadingState, WarningState } from "../components/ui/feedback";
import { StatusTag, SurfaceCard, statusTone } from "../components/ui/surfaces";
import { useEffect, useState } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import {
  deleteCluster,
  describeClusterActionError,
  getCluster,
  restoreCluster,
  updateCluster,
  type Cluster,
  type ClusterActionError,
  type UpdateClusterPayload,
} from "../api/clusters";
import ClusterForm, { parseMetadataText, type ClusterFormValues } from "../components/ClusterForm";

interface ClusterDetailPageProps {
  clusterId: string;
  /** 入口上下文是否为已删除对象（已删详情需显式 deleted=true，Contract §5）。 */
  initialDeleted: boolean;
  user: User;
  onBack: () => void;
}

type DetailState =
  | { kind: "loading" }
  | { kind: "success"; cluster: Cluster }
  | { kind: "error"; message: string };

/** 详情加载失败文案（404 不泄露存在性细节，Contract §1.2/§5）。 */
function detailLoadErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 404) {
      return "集群不存在，或已删除且您无权查看（NOT_FOUND）。";
    }
    if (error.status === 403) {
      return "没有权限查看该集群（可能缺少查看已删除对象的权限，FORBIDDEN）。";
    }
    return displayError(error);
  }
  return "无法连接服务器，请稍后重试";
}

/**
 * 构造 PATCH body（Contract §6.4）：仅携带变化字段（省略 = 保持原值不重置）。
 * description 变化时：空文本 → 显式 null（清空）；metadata 整值替换。
 * 无任何变化返回 null（由调用方提示，不发起空更新）。
 */
function buildUpdatePayload(
  cluster: Cluster,
  values: ClusterFormValues,
): UpdateClusterPayload | null {
  const payload: UpdateClusterPayload = { version: cluster.version };
  let changed = false;

  if (values.name !== cluster.name) {
    payload.name = values.name;
    changed = true;
  }
  if (values.status !== cluster.status) {
    payload.status = values.status;
    changed = true;
  }
  if (values.description !== (cluster.description ?? "")) {
    payload.description = values.description === "" ? null : values.description;
    changed = true;
  }
  const metadata = parseMetadataText(values.metadata);
  // 表单提交前已本地校验为合法 JSON / 空；此处再解析一次并整值比较
  if (metadata.ok && JSON.stringify(metadata.value) !== JSON.stringify(cluster.metadata)) {
    payload.metadata = metadata.value;
    changed = true;
  }

  return changed ? payload : null;
}

/**
 * F003 集群详情页（Contract §3/§5/§6.3–§6.6）：
 * - 基础字段全量展示（null 显式标注“未设置”，不伪装为空值）；
 * - 编辑：PATCH 带 version；仅变化字段；code 不可改（前端不提供编辑）；
 *   409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）；
 * - 删除（软删，DELETE_OBJECT）：需确认，409 CONFLICT reference_exists 展示引用；
 * - 恢复（RESTORE，ADMIN）：需确认，带 version；
 * - 操作按钮按服务端返回的 permissions 显示，隐藏不替代鉴权（服务端仍 403/404）。
 */
export default function ClusterDetailPage({
  clusterId,
  initialDeleted,
  user,
  onBack,
}: ClusterDetailPageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  // 已删对象的详情必须显式 deleted=true（Contract §5）；删除成功后切换为 true
  const [deletedFlag, setDeletedFlag] = useState(initialDeleted);
  const [state, setState] = useState<DetailState>({ kind: "loading" });
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<ClusterActionError | null>(null);
  const [action, setAction] = useState<"delete" | "restore" | null>(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<ClusterActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    getCluster(clusterId, { deleted: deletedFlag })
      .then(({ cluster }) => {
        if (!cancelled) {
          setState({ kind: "success", cluster });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ kind: "error", message: detailLoadErrorMessage(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clusterId, deletedFlag, reloadToken]);

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: ClusterFormValues) {
    if (state.kind !== "success") {
      return;
    }
    const payload = buildUpdatePayload(state.cluster, values);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改至少一个字段后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateCluster(state.cluster.id, payload)
      .then(({ cluster: updated }) => {
        setMode("view"); // Success：展示新版本数据（version+1）
        setState({ kind: "success", cluster: updated });
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT → 表单内提示刷新后重改；409/422/403/404 明确呈现
        setFormError(describeClusterActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重载详情并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    setFormError(null);
    setReloadToken((token) => token + 1);
    setFormKey((key) => key + 1);
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete() {
    setActionError(null);
    setAction("delete");
  }

  function confirmDelete() {
    if (state.kind !== "success") {
      return;
    }
    const cluster = state.cluster;
    setActionBusy(true);
    setActionError(null);
    deleteCluster(cluster.id, cluster.version)
      .then(() => {
        // 204：软删成功（不级联）。若具 VIEW_DELETED 则切到已删视图展示结果
        setAction(null);
        setMode("view");
        if (canViewDeleted) {
          setDeletedFlag(true);
          setReloadToken((token) => token + 1);
        } else {
          onBack();
        }
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT → 刷新后重试；409 CONFLICT reference_exists → 展示引用
        setActionError(describeClusterActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore() {
    setActionError(null);
    setAction("restore");
  }

  function confirmRestore() {
    if (state.kind !== "success") {
      return;
    }
    const cluster = state.cluster;
    setActionBusy(true);
    setActionError(null);
    restoreCluster(cluster.id, cluster.version)
      .then(({ cluster: restored }) => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setDeletedFlag(false);
        setState({ kind: "success", cluster: restored });
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        setActionError(describeClusterActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  return (
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>集群详情</h2>
        <Button type="button" onClick={onBack}>
          返回列表
        </Button>
      </div>

      {state.kind === "loading" && <LoadingState label="正在加载集群详情…" />}

      {state.kind === "error" && (
        <ErrorState
          message={`加载集群详情失败：${state.message}`}
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}

      {state.kind === "success" && mode === "view" && (
        <>
          <dl className="detail-grid">
            <dt>id</dt>
            <dd className="mono">{state.cluster.id}</dd>
            <dt>code</dt>
            <dd className="mono">{state.cluster.code}</dd>
            <dt>name</dt>
            <dd>{state.cluster.name}</dd>
            <dt>status</dt>
            <dd>
              <StatusTag tone={statusTone(state.cluster.status)}>{state.cluster.status}</StatusTag>
              {state.cluster.deleted_at !== null && (
                <StatusTag tone="error">已删除</StatusTag>
              )}
            </dd>
            <dt>description</dt>
            <dd>
              {state.cluster.description ?? <span className="unset">未设置（null）</span>}
            </dd>
            <dt>metadata</dt>
            <dd>
              <pre className="json-block">{JSON.stringify(state.cluster.metadata, null, 2)}</pre>
            </dd>
            <dt>version</dt>
            <dd>{state.cluster.version}</dd>
            <dt>created_at</dt>
            <dd className="mono">{state.cluster.created_at}</dd>
            <dt>updated_at</dt>
            <dd className="mono">{state.cluster.updated_at}</dd>
            <dt>deleted_at</dt>
            <dd className="mono">
              {state.cluster.deleted_at ?? <span className="unset">未删除（null）</span>}
            </dd>
          </dl>

          <div className="record-actions">
            {canWrite && state.cluster.deleted_at === null && (
              <Button
                type="button"
                variant="primary"
                onClick={() => {
                  setFormError(null);
                  setMode("edit");
                }}
              >
                编辑
              </Button>
            )}
            {canDelete && state.cluster.deleted_at === null && (
              <Button type="button" danger onClick={requestDelete}>
                删除集群
              </Button>
            )}
            {canRestore && state.cluster.deleted_at !== null && (
              <Button type="button" onClick={requestRestore}>
                恢复集群
              </Button>
            )}
          </div>

          {/* F020：删除 / 恢复二次确认模态（替代原内联确认；请求语义不变，错误块随正文呈现） */}
          <ConfirmDialog
            open={action === "delete"}
            title="删除集群"
            okText="确认删除"
            danger
            confirmLoading={actionBusy}
            onConfirm={confirmDelete}
            onCancel={() => {
              setAction(null);
              setActionError(null);
            }}
          >
            {action === "delete" && (
              <div className="detail-actions">
                <WarningState
                  message={
                    <span>
                      确认软删除集群 {state.cluster.code}？（不级联删除关联对象；软删后 code 不可复用）
                    </span>
                  }
                />
                {actionError && (
                  <ErrorState message={<div className="form-error">
                    <p>{actionError.message}</p>
                    {actionError.references.length > 0 && (
                      <ul>
                        {actionError.references.map((reference) => (
                          <li key={`${reference.object_type}-${reference.object_id}`}>
                            {reference.object_type}：{reference.label}（{reference.object_id}）
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.versionConflict && (
                      <p>
                        <Button
                          type="button"
                          onClick={() => {
                            setActionError(null);
                            setAction(null);
                            setReloadToken((token) => token + 1);
                          }}
                          disabled={actionBusy}
                        >
                          刷新最新数据
                        </Button>
                      </p>
                    )}
                  </div>} />
                )}
              </div>
            )}
          </ConfirmDialog>
          <ConfirmDialog
            open={action === "restore"}
            title="恢复集群"
            okText="确认恢复"
            confirmLoading={actionBusy}
            onConfirm={confirmRestore}
            onCancel={() => {
              setAction(null);
              setActionError(null);
            }}
          >
            {action === "restore" && (
              <div className="detail-actions">
                <WarningState
                  message={
                    <span>确认恢复集群 {state.cluster.code}？（恢复自身，不级联；version 递增）</span>
                  }
                />
                {actionError && (
                  <ErrorState message={<div className="form-error">
                    <p>{actionError.message}</p>
                    {actionError.references.length > 0 && (
                      <ul>
                        {actionError.references.map((reference) => (
                          <li key={`${reference.object_type}-${reference.object_id}`}>
                            {reference.object_type}：{reference.label}（{reference.object_id}）
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.versionConflict && (
                      <p>
                        <Button
                          type="button"
                          onClick={() => {
                            setActionError(null);
                            setAction(null);
                            setReloadToken((token) => token + 1);
                          }}
                          disabled={actionBusy}
                        >
                          刷新最新数据
                        </Button>
                      </p>
                    )}
                  </div>} />
                )}
              </div>
            )}
          </ConfirmDialog>
        </>
      )}

      {state.kind === "success" && mode === "edit" && (
        <ClusterForm
          key={formKey}
          mode="edit"
          cluster={state.cluster}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleEditSubmit}
          onCancel={() => setMode("view")}
          onRefresh={refreshAfterConflict}
        />
      )}
    </SurfaceCard>
  );
}
