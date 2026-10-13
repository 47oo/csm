import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Space,
  Spin,
  Table,
  Tag,
  type TableProps,
} from "antd";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import type { Resource } from "../api/resources";
import {
  createInterface,
  deleteInterface,
  describeInterfaceActionError,
  getInterface,
  listInterfaces,
  restoreInterface,
  updateInterface,
  type Interface,
  type InterfaceActionError,
  type InterfaceListResponse,
} from "../api/interfaces";
import InterfaceForm from "./InterfaceForm";
import {
  buildInterfaceCreateInput,
  buildInterfacePatch,
  parseInterfaceFormValues,
  type InterfaceFormValues,
} from "./interfaceForm";
import { parseMetadataText } from "./ClusterForm";

/** 接口列表加载状态（分页上限 100，Contract §4）。 */
type InterfaceListState =
  | { kind: "loading" }
  | { kind: "success"; data: InterfaceListResponse }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单 / 编辑表单。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "edit"; iface: Interface };

/** Table 行数据类型（取自 InterfaceListResponse.items 元素）。 */
type InterfaceItem = InterfaceListResponse["items"][number];

interface InterfacesPanelProps {
  /** 所属 Resource（归属创建后不可改；已删资源不可新建 / 恢复接口）。 */
  resource: Resource;
  user: User;
}

/**
 * CONFLICT reference_exists 单条引用的呈现文案（Contract §1.2，DR-80/DR-82）：
 * interface=未删子接口（label=子接口 name）；ip_address=F010 IP 地址
 * （F007 交付时为空集，预留呈现）；未知 object_type 原样展示，不伪装成已知类型。
 */
function referenceItemText(reference: {
  object_type: string;
  object_id: string;
  label: string | null;
}): string {
  if (reference.object_type === "interface") {
    return reference.label ? `子接口：${reference.label}` : `子接口（${reference.object_id}）`;
  }
  if (reference.object_type === "ip_address") {
    return reference.label ? `IP 地址：${reference.label}` : `IP 地址（${reference.object_id}）`;
  }
  return reference.label ? `${reference.object_type}：${reference.label}` : reference.object_type;
}

/** 数值字段：null → 占位，绝不以 0 代替（D01 §5.6：未知存 null 不转 0）。 */
function interfaceNumber(value: number | null): ReactNode {
  if (value === null) {
    return <span className="text-gray-400">—</span>;
  }
  return String(value);
}

/**
 * Resource Detail 的 Interfaces 区域（F007，§18 A19 / DR-84；Contract §4/§5/§6）：
 * - 列表：GET /api/v1/interfaces?resource_id=<资源 id>（默认未删除；
 *   已删开关 → deleted=include，需 VIEW_DELETED，服务端仍 403 把关）；
 *   Loading / Empty / Error 显式区分，错误可重试、绝不伪装成空列表；
 * - 未知 mac / speed_mbps / mtu 显示「—」，绝不以 0 代替；
 * - 创建 / 编辑（WRITE）：InterfaceForm（类型下拉 / parent 选择器 / enabled
 *   开关 / 正整数校验 / 422 字段映射）；提交带 version（编辑），
 *   409 unique_conflict{field:"name"} / VERSION_CONFLICT 明确呈现；
 * - 删除（DELETE_OBJECT，软删不级联）：被未删子接口 / IP 引用 → 409
 *   reference_exists 展示引用列表；
 * - 恢复（RESTORE，ADMIN）：409 not_deleted / unique_conflict /
 *   dependency_deleted（所属资源 / 父接口仍删）明确呈现；
 * - 操作按钮按服务端返回的 permissions 显示，隐藏不替代鉴权；所属资源已
 *   软删时隐藏新建 / 恢复入口（服务端确定性拒绝：创建 422 field="resource"、
 *   恢复 409 dependency_deleted），编辑 / 删除未删接口契约未禁止、照常提供。
 */
export default function InterfacesPanel({ resource, user }: InterfacesPanelProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const resourceDeleted = resource.deleted_at !== null;
  const [showDeleted, setShowDeleted] = useState(false);
  const [state, setState] = useState<InterfaceListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<InterfaceActionError | null>(null);
  const [action, setAction] = useState<
    { kind: "delete" | "restore"; iface: Interface } | null
  >(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<InterfaceActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    // 已删开关：include 需 VIEW_DELETED（开关仅在具备权限时渲染；服务端仍 403 把关）
    listInterfaces({
      resource_id: resource.id,
      deleted: showDeleted ? "include" : "exclude",
      page_size: 100,
      sort: "created_at",
      order: "desc",
    })
      .then((data) => {
        if (!cancelled) {
          setState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setState({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [resource.id, showDeleted, reloadToken]);

  /** 表单原始值 → 解析 + metadata 解析（复用 ClusterForm.parseMetadataText）。 */
  function parseSubmission(values: InterfaceFormValues) {
    const parsed = parseInterfaceFormValues(values);
    if (!parsed.ok) {
      return null;
    }
    const metadata = parseMetadataText(values.metadata);
    if (!metadata.ok) {
      return null; // 表单本地校验已拦截；防御双保险（不发起请求）
    }
    return { fields: parsed.fields, metadata: metadata.value };
  }

  // ---- 创建（POST，Contract §6.2）----

  function handleCreateSubmit(values: InterfaceFormValues) {
    const parsed = parseSubmission(values);
    if (parsed === null) {
      return;
    }
    setSubmitting(true);
    setFormError(null);
    createInterface(
      buildInterfaceCreateInput(resource.id, parsed.fields, parsed.metadata),
    )
      .then(() => {
        // 201：创建成功（version=1）；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 422（body / resource / parent）/ 409 unique_conflict 明确呈现
        setFormError(describeInterfaceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: InterfaceFormValues) {
    if (mode.kind !== "edit") {
      return;
    }
    const parsed = parseSubmission(values);
    if (parsed === null) {
      return;
    }
    const payload = buildInterfacePatch(mode.iface, parsed.fields, parsed.metadata);
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
    updateInterface(mode.iface.id, payload)
      .then(() => {
        // 200：version+1；回列表并重载（刷新 parent 展开与版本）
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT → 表单内提示刷新后重改；409/422/403/404 明确呈现
        setFormError(describeInterfaceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该接口并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.iface.id;
    setFormError(null);
    setSubmitting(true);
    getInterface(id)
      .then(({ interface: fresh }) => {
        setMode({ kind: "edit", iface: fresh });
        setFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setFormError(describeInterfaceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete(iface: Interface) {
    setActionError(null);
    setAction({ kind: "delete", iface });
  }

  function confirmDelete() {
    if (action === null) {
      return;
    }
    const iface = action.iface;
    setActionBusy(true);
    setActionError(null);
    deleteInterface(iface.id, iface.version)
      .then(() => {
        // 204：软删成功（不级联）；重载列表（已删开关开启时仍可见并带徽标）
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 reference_exists（子接口 / IP 引用）/ VERSION_CONFLICT 明确呈现
        setActionError(describeInterfaceActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore(iface: Interface) {
    setActionError(null);
    setAction({ kind: "restore", iface });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const iface = action.iface;
    setActionBusy(true);
    setActionError(null);
    restoreInterface(iface.id, iface.version)
      .then(() => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        setActionError(describeInterfaceActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // 仅开启已删开关时追加 deleted_at 列（与原实现口径一致）
  const deletedAtColumn: NonNullable<TableProps<InterfaceItem>["columns"]>[number] = {
    title: "deleted_at",
    dataIndex: "deleted_at",
    key: "deleted_at",
    render: (value) =>
      value != null ? (
        <span className="font-mono text-xs">{value}</span>
      ) : (
        <span className="text-gray-400">—</span>
      ),
  };

  const columns: TableProps<InterfaceItem>["columns"] = [
    {
      title: "name",
      dataIndex: "name",
      key: "name",
      render: (_, iface) => (
        <span>
          <span className="font-mono text-xs">{iface.name}</span>
          {iface.deleted_at !== null && (
            <Tag color="red" className="ml-2">
              已删除
            </Tag>
          )}
        </span>
      ),
    },
    {
      title: "interface_type",
      dataIndex: "interface_type",
      key: "interface_type",
    },
    {
      title: "mac_address",
      dataIndex: "mac_address",
      key: "mac_address",
      render: (value) =>
        value != null ? (
          <span className="font-mono text-xs">{value}</span>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
    {
      title: "speed_mbps",
      dataIndex: "speed_mbps",
      key: "speed_mbps",
      render: (value) => interfaceNumber(value),
    },
    {
      title: "mtu",
      dataIndex: "mtu",
      key: "mtu",
      render: (value) => interfaceNumber(value),
    },
    {
      title: "parent_interface",
      dataIndex: "parent_interface",
      key: "parent_interface",
      render: (_, iface) =>
        iface.parent_interface === null ? (
          <span className="text-gray-400">—</span>
        ) : (
          <span className="font-mono text-xs">{iface.parent_interface.name}</span>
        ),
    },
    {
      title: "enabled",
      dataIndex: "enabled",
      key: "enabled",
      render: (_, iface) => (
        <Tag color={iface.enabled ? "success" : "default"}>
          {iface.enabled ? "启用" : "停用"}
        </Tag>
      ),
    },
    ...(showDeleted ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_, iface) => (
        <Space size={4}>
          {canWrite && iface.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => {
                setFormError(null);
                setMode({ kind: "edit", iface });
                setFormKey((key) => key + 1);
              }}
            >
              编辑
            </Button>
          )}
          {canDelete && iface.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              danger
              onClick={() => requestDelete(iface)}
            >
              删除
            </Button>
          )}
          {canRestore && iface.deleted_at !== null && !resourceDeleted && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRestore(iface)}
            >
              恢复
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <h3 className="mb-1 text-base font-semibold text-gray-900">Interfaces（网络接口）</h3>

      {mode.kind === "list" && (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-gray-500">
              经 GET /api/v1/interfaces?resource_id 过滤（{resource.hostname}）
            </span>
            <span>
              {canWrite && !resourceDeleted && (
                <Button
                  type="primary"
                  onClick={() => {
                    setFormError(null);
                    setMode({ kind: "create" });
                  }}
                >
                  新建接口
                </Button>
              )}
            </span>
          </div>

          {resourceDeleted && (
            <Alert
              className="mb-3"
              type="warning"
              showIcon
              message="所属资源处于已删除状态：无法新建接口（服务端拒绝引用已删资源），恢复接口需先恢复所属资源。"
            />
          )}

          {canViewDeleted && (
            <div className="mb-3">
              <Checkbox
                id="interfaces-deleted-toggle"
                checked={showDeleted}
                onChange={(event) => setShowDeleted(event.target.checked)}
              >
                显示已删除接口（deleted=include，需 VIEW_DELETED）
              </Checkbox>
            </div>
          )}

          {state.kind === "loading" && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
              <Spin />
              <span>正在加载该资源的网络接口…</span>
            </div>
          )}

          {state.kind === "error" && (
            <Alert
              className="mb-3"
              type="error"
              showIcon
              message={`加载接口列表失败：${state.message}`}
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

          {state.kind === "success" &&
            (state.data.items.length === 0 ? (
              <Empty
                className="py-8"
                description={
                  showDeleted
                    ? "该资源暂无接口登记（含已删除）。"
                    : "该资源暂无未删除的接口登记（非错误）。"
                }
              />
            ) : (
              <>
                {state.data.total > state.data.items.length && (
                  <Alert
                    className="mb-3"
                    type="info"
                    showIcon
                    message={`接口总数 ${state.data.total} 个，仅显示前 ${state.data.items.length} 个（按 created_at 排序；列表分页上限 100）。`}
                  />
                )}
                <Table<InterfaceItem>
                  rowKey="id"
                  size="middle"
                  pagination={false}
                  scroll={{ x: "max-content" }}
                  dataSource={state.data.items}
                  columns={columns}
                />
              </>
            ))}

          {(actionError !== null || action !== null) && (
            <div className="mt-5 flex flex-col gap-3">
              {actionError && (
                <Alert
                  type="error"
                  showIcon
                  message={actionError.message}
                  description={
                    <>
                      {actionError.references.length > 0 && (
                        <ul className="list-disc pl-5">
                          {actionError.references.map((reference) => (
                            <li key={`${reference.object_type}-${reference.object_id}`}>
                              {referenceItemText(reference)}（{reference.object_id}）
                            </li>
                          ))}
                        </ul>
                      )}
                      {actionError.conflicts.length > 0 && (
                        <ul className="list-disc pl-5">
                          {actionError.conflicts.map((conflict) => (
                            <li key={`${conflict.object_type}-${conflict.object_id}`}>
                              {conflict.object_type === "resource"
                                ? `所属资源（${conflict.object_id}）仍处于已删除状态或已不存在`
                                : `父接口（${conflict.object_id}）仍处于已删除状态或已不存在`}
                            </li>
                          ))}
                        </ul>
                      )}
                      {actionError.versionConflict && (
                        <Button
                          size="small"
                          danger
                          className="mt-2"
                          disabled={actionBusy}
                          onClick={() => {
                            setActionError(null);
                            setAction(null);
                            setReloadToken((token) => token + 1);
                          }}
                        >
                          刷新最新数据
                        </Button>
                      )}
                    </>
                  }
                />
              )}

              {action !== null && (
                <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <span>
                    {action.kind === "delete" ? (
                      <span>
                        确认软删除接口 {action.iface.name}？（不级联删除关联对象；同资源内名称软删后可复用；
                        若仍有未删除的子接口或 IP 引用，将被拒绝并显示引用列表）
                      </span>
                    ) : (
                      <span>
                        确认恢复接口 {action.iface.name}？（仅恢复自身，不级联；将重检同资源名称唯一性、
                        所属资源与父接口有效性，失败不覆盖新对象；version 递增）
                      </span>
                    )}
                  </span>
                  <Button
                    type="primary"
                    danger={action.kind === "delete"}
                    onClick={action.kind === "delete" ? confirmDelete : confirmRestore}
                    disabled={actionBusy}
                  >
                    {actionBusy
                      ? action.kind === "delete"
                        ? "正在删除…"
                        : "正在恢复…"
                      : action.kind === "delete"
                        ? "确认删除"
                        : "确认恢复"}
                  </Button>
                  <Button onClick={() => setAction(null)} disabled={actionBusy}>
                    取消
                  </Button>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {mode.kind === "create" && (
        <InterfaceForm
          mode="create"
          resource={{ id: resource.id, hostname: resource.hostname }}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleCreateSubmit}
          onCancel={() => setMode({ kind: "list" })}
        />
      )}

      {mode.kind === "edit" && (
        <InterfaceForm
          key={formKey}
          mode="edit"
          resource={{ id: resource.id, hostname: resource.hostname }}
          iface={mode.iface}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleEditSubmit}
          onCancel={() => setMode({ kind: "list" })}
          onRefresh={refreshAfterConflict}
        />
      )}
    </>
  );
}
