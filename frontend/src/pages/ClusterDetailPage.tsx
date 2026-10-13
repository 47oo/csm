import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Modal,
  Spin,
  Tag,
  type DescriptionsProps,
} from "antd";
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
 * 详情字段展示（Contract §3/§5）：基础字段全量展示，null 显式标注“未设置 /
 * 未删除”，不伪装为空值；status 徽标化并附“已删除”标记（口径同列表页）。
 */
function clusterDetailItems(cluster: Cluster): DescriptionsProps["items"] {
  return [
    { key: "id", label: "id", children: <span className="font-mono">{cluster.id}</span> },
    { key: "code", label: "code", children: <span className="font-mono">{cluster.code}</span> },
    { key: "name", label: "name", children: cluster.name },
    {
      key: "status",
      label: "status",
      children: (
        <span>
          <Tag color={cluster.status === "ACTIVE" ? "success" : "default"}>{cluster.status}</Tag>
          {cluster.deleted_at !== null && (
            <Tag color="red" className="ml-2">
              已删除
            </Tag>
          )}
        </span>
      ),
    },
    {
      key: "description",
      label: "description",
      children: cluster.description ?? <span className="text-gray-400">未设置（null）</span>,
    },
    {
      key: "metadata",
      label: "metadata",
      children: (
        <pre className="m-0 max-w-full overflow-x-auto rounded-md border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-sm">
          {JSON.stringify(cluster.metadata, null, 2)}
        </pre>
      ),
    },
    { key: "version", label: "version", children: cluster.version },
    {
      key: "created_at",
      label: "created_at",
      children: <span className="font-mono">{cluster.created_at}</span>,
    },
    {
      key: "updated_at",
      label: "updated_at",
      children: <span className="font-mono">{cluster.updated_at}</span>,
    },
    {
      key: "deleted_at",
      label: "deleted_at",
      children:
        cluster.deleted_at !== null ? (
          <span className="font-mono">{cluster.deleted_at}</span>
        ) : (
          <span className="text-gray-400">未删除（null）</span>
        ),
    },
  ];
}

/**
 * F003 集群详情页（Contract §3/§5/§6.3–§6.6）：
 * - 基础字段全量展示（null 显式标注“未设置”，不伪装为空值）；
 * - 编辑：PATCH 带 version；仅变化字段；code 不可改（前端不提供编辑）；
 *   409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）；
 * - 删除（软删，DELETE_OBJECT）：需确认，409 CONFLICT reference_exists 展示引用；
 * - 恢复（RESTORE，ADMIN）：需确认，带 version；
 * - 操作按钮按服务端返回的 permissions 显示，隐藏不替代鉴权（服务端仍 403/404）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 详情字段与 null 标注 /
 * 编辑与删除恢复流程 / 软删 / 权限门控 / 四态 / 文案均保持不变）。原行内二次确认
 * 改为 Modal：确认框开启期间错误（含引用列表、版本冲突刷新按钮）在框内呈现，
 * 取消后仍保留在操作区，行为口径同迁移前（失败后确认框保持待确认状态）。
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

  // 操作错误提示（AntD Alert 自带 role="alert"）：确认框开启期间渲染在 Modal 内，
  // 取消确认后保留在操作区展示（同迁移前的呈现位置与文案）
  const actionErrorAlert = actionError ? (
    <Alert
      type="error"
      message={actionError.message}
      description={
        actionError.references.length > 0 || actionError.versionConflict ? (
          <>
            {actionError.references.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.references.map((reference) => (
                  <li key={`${reference.object_type}-${reference.object_id}`}>
                    {reference.object_type}：{reference.label}（{reference.object_id}）
                  </li>
                ))}
              </ul>
            )}
            {actionError.versionConflict && (
              <Button
                className="mt-2"
                onClick={() => {
                  setActionError(null);
                  setReloadToken((token) => token + 1);
                }}
                disabled={actionBusy}
              >
                刷新最新数据
              </Button>
            )}
          </>
        ) : undefined
      }
    />
  ) : null;

  // 二次确认框的可见口径同迁移前的行内确认块：仅 Success + 查看模式渲染
  const confirmVisible = state.kind === "success" && mode === "view";

  return (
    <>
      <Card
        className="mt-6"
        title="集群详情"
        extra={
          <Button htmlType="button" onClick={onBack}>
            返回列表
          </Button>
        }
      >
        {state.kind === "loading" && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
            <Spin />
            <span>正在加载集群详情…</span>
          </div>
        )}

        {state.kind === "error" && (
          <Alert
            type="error"
            showIcon
            message={`加载集群详情失败：${state.message}`}
            action={
              <Button
                size="small"
                danger
                onClick={() => setReloadToken((token) => token + 1)}
              >
                重试
              </Button>
            }
          />
        )}

        {state.kind === "success" && mode === "view" && (
          <>
            <Descriptions
              column={1}
              items={clusterDetailItems(state.cluster)}
              contentStyle={{ overflowWrap: "anywhere" }}
            />

            <div className="mt-5 flex flex-col gap-4">
              {action === null && actionErrorAlert}

              {action === null && (
                <div className="flex flex-wrap gap-3">
                  {canWrite && state.cluster.deleted_at === null && (
                    <Button
                      onClick={() => {
                        setFormError(null);
                        setMode("edit");
                      }}
                    >
                      编辑
                    </Button>
                  )}
                  {canDelete && state.cluster.deleted_at === null && (
                    <Button danger onClick={requestDelete}>
                      删除集群
                    </Button>
                  )}
                  {canRestore && state.cluster.deleted_at !== null && (
                    <Button onClick={requestRestore}>恢复集群</Button>
                  )}
                </div>
              )}
            </div>
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
      </Card>

      {/* 删除二次确认（软删，Contract §6.5）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action === "delete" && confirmVisible}
        title="确认软删除该集群？（不级联删除关联对象；软删后 code 不可复用）"
        okText={actionBusy ? "正在删除…" : "确认删除"}
        okButtonProps={{ danger: true }}
        cancelText="取消"
        cancelButtonProps={{ disabled: actionBusy }}
        confirmLoading={actionBusy}
        maskClosable={false}
        keyboard={false}
        onOk={confirmDelete}
        onCancel={() => {
          if (!actionBusy) {
            setAction(null);
          }
        }}
      >
        {actionErrorAlert}
      </Modal>

      {/* 恢复二次确认（RESTORE，Contract §6.6）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action === "restore" && confirmVisible}
        title="确认恢复该集群？（恢复自身，不级联；version 递增）"
        okText={actionBusy ? "正在恢复…" : "确认恢复"}
        cancelText="取消"
        cancelButtonProps={{ disabled: actionBusy }}
        confirmLoading={actionBusy}
        maskClosable={false}
        keyboard={false}
        onOk={confirmRestore}
        onCancel={() => {
          if (!actionBusy) {
            setAction(null);
          }
        }}
      >
        {actionErrorAlert}
      </Modal>
    </>
  );
}
