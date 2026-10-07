import { useEffect, useState } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import {
  deleteResource,
  describeResourceActionError,
  getResource,
  restoreResource,
  updateResource,
  type Resource,
  type ResourceActionError,
  type UpdateResourcePayload,
} from "../api/resources";
import ResourceForm, { type ResourceFormValues } from "../components/ResourceForm";
import { parseMetadataText } from "../components/ClusterForm";

interface ResourceDetailPageProps {
  resourceId: string;
  /** 入口上下文是否为已删除对象（已删详情需显式 deleted=true，Contract §5）。 */
  initialDeleted: boolean;
  user: User;
  onBack: () => void;
}

type DetailState =
  | { kind: "loading" }
  | { kind: "success"; resource: Resource }
  | { kind: "error"; message: string };

/** 详情加载失败文案（404 不泄露存在性细节，Contract §1.2/§5）。 */
function detailLoadErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 404) {
      return "资源不存在，或已删除且您无权查看（NOT_FOUND）。";
    }
    if (error.status === 403) {
      return "没有权限查看该资源（可能缺少查看已删除对象的权限，FORBIDDEN）。";
    }
    return displayError(error);
  }
  return "无法连接服务器，请稍后重试";
}

/**
 * 构造 PATCH body（Contract §6.4）：仅携带变化字段（省略 = 保持原值不重置）。
 * description 变化时：空文本 → 显式 null（清空）；metadata 整值替换。
 * cluster / resource_type 不可改（表单只读展示，不上送）。
 * 无任何变化返回 null（由调用方提示，不发起空更新）。
 */
function buildUpdatePayload(
  resource: Resource,
  values: ResourceFormValues,
): UpdateResourcePayload | null {
  const payload: UpdateResourcePayload = { version: resource.version };
  let changed = false;

  if (values.hostname !== resource.hostname) {
    payload.hostname = values.hostname;
    changed = true;
  }
  if (values.role !== resource.role) {
    payload.role = values.role;
    changed = true;
  }
  if (values.status !== resource.status) {
    payload.status = values.status;
    changed = true;
  }
  if (values.description !== (resource.description ?? "")) {
    payload.description = values.description === "" ? null : values.description;
    changed = true;
  }
  const metadata = parseMetadataText(values.metadata);
  // 表单提交前已本地校验为合法 JSON / 空；此处再解析一次并整值比较
  if (metadata.ok && JSON.stringify(metadata.value) !== JSON.stringify(resource.metadata)) {
    payload.metadata = metadata.value;
    changed = true;
  }

  return changed ? payload : null;
}

/** F005+ 交付的 Detail 区域（Contract §9：本 Feature 仅交付 Overview，其余占位）。 */
const PLACEHOLDER_AREAS: { title: string; note: string }[] = [
  { title: "硬件信息（Hardware）", note: "物理机 / 虚拟机硬件明细，F005+ 提供" },
  { title: "接口信息（Interfaces）", note: "网络接口明细，F005+ 提供" },
  { title: "IP 地址（IP）", note: "IP 地址与分配明细，后续 Feature 提供" },
  { title: "虚拟机（VMs）", note: "宿主机上的虚拟机列表，后续 Feature 提供" },
  { title: "服务（Services）", note: "运行服务登记，后续 Feature 提供" },
];

/**
 * F004 资源详情页（Contract §3/§5/§6.3–§6.6，§9 业务边界）：
 * - Overview 六要素：Hostname / Cluster / Type / Role / Status / Description
 *   （§18）；Hardware / Interfaces / IP / VMs / Services 区域占位（F005+）；
 * - 编辑：PATCH 带 version；仅变化字段；cluster / resource_type 不可改（只读展示）；
 *   409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）；
 * - 删除（软删，DELETE_OBJECT）：需确认，409 VERSION_CONFLICT / reference_exists 明确呈现；
 * - 恢复（RESTORE）：需确认，带 version；409 not_deleted / unique_conflict /
 *   dependency_deleted（所属 Cluster 仍软删）明确呈现；
 * - 操作按钮按服务端返回的 permissions 显示，隐藏不替代鉴权（服务端仍 403/404）。
 */
export default function ResourceDetailPage({
  resourceId,
  initialDeleted,
  user,
  onBack,
}: ResourceDetailPageProps) {
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
  const [formError, setFormError] = useState<ResourceActionError | null>(null);
  const [action, setAction] = useState<"delete" | "restore" | null>(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<ResourceActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    getResource(resourceId, { deleted: deletedFlag })
      .then(({ resource }) => {
        if (!cancelled) {
          setState({ kind: "success", resource });
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
  }, [resourceId, deletedFlag, reloadToken]);

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: ResourceFormValues) {
    if (state.kind !== "success") {
      return;
    }
    const payload = buildUpdatePayload(state.resource, values);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改至少一个字段后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
        conflicts: [],
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateResource(state.resource.id, payload)
      .then(({ resource: updated }) => {
        setMode("view"); // Success：展示新版本数据（version+1）
        setState({ kind: "success", resource: updated });
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT → 表单内提示刷新后重改；409/422/403/404 明确呈现
        setFormError(describeResourceActionError(error));
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
    const resource = state.resource;
    setActionBusy(true);
    setActionError(null);
    deleteResource(resource.id, resource.version)
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
        setActionError(describeResourceActionError(error));
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
    const resource = state.resource;
    setActionBusy(true);
    setActionError(null);
    restoreResource(resource.id, resource.version)
      .then(({ resource: restored }) => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setDeletedFlag(false);
        setState({ kind: "success", resource: restored });
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        setActionError(describeResourceActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  return (
    <section className="panel">
      <div className="table-toolbar">
        <h2>资源详情</h2>
        <button type="button" onClick={onBack}>
          返回列表
        </button>
      </div>

      {state.kind === "loading" && (
        <p className="status status-loading">正在加载资源详情…</p>
      )}

      {state.kind === "error" && (
        <div className="status status-error" role="alert">
          <p>加载资源详情失败：{state.message}</p>
          <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
            重试
          </button>
        </div>
      )}

      {state.kind === "success" && mode === "view" && (
        <>
          <h3 className="detail-section-title">Overview</h3>
          <dl className="detail-grid">
            <dt>hostname</dt>
            <dd className="mono">{state.resource.hostname}</dd>
            <dt>cluster</dt>
            <dd>
              <span className="mono">{state.resource.cluster.code}</span> —{" "}
              {state.resource.cluster.name}
              <span className="unset">（id: {state.resource.cluster.id}）</span>
            </dd>
            <dt>type</dt>
            <dd className="mono">{state.resource.resource_type}</dd>
            <dt>role</dt>
            <dd>{state.resource.role}</dd>
            <dt>status</dt>
            <dd>
              <span className={`badge badge-${state.resource.status.toLowerCase()}`}>
                {state.resource.status}
              </span>
              {state.resource.deleted_at !== null && (
                <span className="badge badge-deleted">已删除</span>
              )}
            </dd>
            <dt>description</dt>
            <dd>
              {state.resource.description ?? <span className="unset">未设置（null）</span>}
            </dd>
          </dl>

          <h3 className="detail-section-title">系统信息</h3>
          <dl className="detail-grid">
            <dt>metadata</dt>
            <dd>
              <pre className="json-block">{JSON.stringify(state.resource.metadata, null, 2)}</pre>
            </dd>
            <dt>version</dt>
            <dd>{state.resource.version}</dd>
            <dt>created_at</dt>
            <dd className="mono">{state.resource.created_at}</dd>
            <dt>updated_at</dt>
            <dd className="mono">{state.resource.updated_at}</dd>
            <dt>deleted_at</dt>
            <dd className="mono">
              {state.resource.deleted_at ?? <span className="unset">未删除（null）</span>}
            </dd>
          </dl>

          <h3 className="detail-section-title">明细区域</h3>
          <div className="placeholder-areas">
            {PLACEHOLDER_AREAS.map((area) => (
              <div key={area.title} className="placeholder-box">
                <strong>{area.title}</strong>
                <p>{area.note}</p>
              </div>
            ))}
          </div>

          <div className="detail-actions">
            {actionError && (
              <div className="status status-error action-error" role="alert">
                <p>{actionError.message}</p>
                {actionError.references.length > 0 && (
                  <ul>
                    {actionError.references.map((reference) => (
                      <li key={`${reference.object_type}-${reference.object_id}`}>
                        {reference.object_type}
                        {reference.label ? `：${reference.label}` : ""}（{reference.object_id}）
                      </li>
                    ))}
                  </ul>
                )}
                {actionError.conflicts.length > 0 && (
                  <ul>
                    {actionError.conflicts.map((conflict) => (
                      <li key={`${conflict.object_type}-${conflict.object_id}`}>
                        所属 {conflict.object_type}（{conflict.object_id}）仍处于已删除状态，
                        需先恢复该集群后再恢复资源。
                      </li>
                    ))}
                  </ul>
                )}
                {actionError.versionConflict && (
                  <p>
                    <button
                      type="button"
                      onClick={() => {
                        setActionError(null);
                        setReloadToken((token) => token + 1);
                      }}
                      disabled={actionBusy}
                    >
                      刷新最新数据
                    </button>
                  </p>
                )}
              </div>
            )}

            {action === "delete" ? (
              <div className="inline-confirm">
                <span>
                  确认软删除该资源？（不级联删除关联对象；软删后同集群 hostname 可被新资源复用）
                </span>
                <button type="button" onClick={confirmDelete} disabled={actionBusy}>
                  {actionBusy ? "正在删除…" : "确认删除"}
                </button>
                <button type="button" onClick={() => setAction(null)} disabled={actionBusy}>
                  取消
                </button>
              </div>
            ) : action === "restore" ? (
              <div className="inline-confirm">
                <span>
                  确认恢复该资源？（恢复自身，不级联；将重检同集群 hostname 唯一性与所属集群有效性；version 递增）
                </span>
                <button type="button" onClick={confirmRestore} disabled={actionBusy}>
                  {actionBusy ? "正在恢复…" : "确认恢复"}
                </button>
                <button type="button" onClick={() => setAction(null)} disabled={actionBusy}>
                  取消
                </button>
              </div>
            ) : (
              <>
                {canWrite && state.resource.deleted_at === null && (
                  <button
                    type="button"
                    onClick={() => {
                      setFormError(null);
                      setMode("edit");
                    }}
                  >
                    编辑
                  </button>
                )}
                {canDelete && state.resource.deleted_at === null && (
                  <button type="button" onClick={requestDelete}>
                    删除资源
                  </button>
                )}
                {canRestore && state.resource.deleted_at !== null && (
                  <button type="button" onClick={requestRestore}>
                    恢复资源
                  </button>
                )}
              </>
            )}
          </div>
        </>
      )}

      {state.kind === "success" && mode === "edit" && (
        <ResourceForm
          key={formKey}
          mode="edit"
          resource={state.resource}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleEditSubmit}
          onCancel={() => setMode("view")}
          onRefresh={refreshAfterConflict}
        />
      )}
    </section>
  );
}
