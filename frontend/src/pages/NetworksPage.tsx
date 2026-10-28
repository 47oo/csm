import { Button, Input, Select, DataTable } from "../components/ui/controls";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState, WarningState } from "../components/ui/feedback";
import { ServerPagination as Pagination, StatusTag, SurfaceCard, statusTone } from "../components/ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import { listClusters, type Cluster } from "../api/clusters";
import {
  createNetwork,
  deleteNetwork,
  describeNetworkActionError,
  getNetwork,
  listNetworks,
  restoreNetwork,
  updateNetwork,
  type DeletedMode,
  type Network,
  type NetworkActionError,
  type NetworkListResponse,
  type NetworkSortField,
  type NetworkStatus,
  type SortOrder,
} from "../api/networks";
import NetworkForm from "../components/NetworkForm";
import { parseMetadataText } from "../components/ClusterForm";
import {
  buildNetworkCreateInput,
  buildNetworkPatch,
  parseNetworkFormValues,
  type NetworkFormValues,
} from "../components/networkForm";

interface NetworksPageProps {
  user: User;
}

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: NetworkListResponse }
  | { kind: "error"; message: string };

/** 集群下拉数据加载状态（仅未删除集群；分页上限 100，Contract §4）。 */
type ClusterOptionsState =
  | { kind: "loading" }
  | { kind: "success"; clusters: Cluster[]; total: number }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单 / 编辑表单。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "edit"; network: Network };

/** 已应用的查询（排序 / 分页 / 过滤 / 软删可见性，Contract §4/§5）。 */
interface AppliedQuery {
  q: string;
  clusterId: string;
  status: "" | NetworkStatus;
  /** auto_allocate 过滤：空 = 全部，true / false 精确过滤。 */
  autoAllocate: "" | "true" | "false";
  deleted: DeletedMode;
  page: number;
  pageSize: number;
  sort: NetworkSortField;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  clusterId: "",
  status: "",
  autoAllocate: "",
  deleted: "exclude",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

const SORT_COLUMNS: { field: NetworkSortField; label: string }[] = [
  { field: "name", label: "name" },
  { field: "cidr", label: "cidr" },
  { field: "status", label: "status" },
  { field: "created_at", label: "创建时间" },
  { field: "updated_at", label: "更新时间" },
];

/**
 * CONFLICT range_overlap / reference_exists 单条明细的呈现文案
 * （Contract §1.2）：network=重叠网络（label=name）；ip_pool/ip_address=
 * 未删子对象（F009/F010，F008 交付时为空集，预留呈现）；cluster=依赖集群；
 * 未知 object_type 原样展示，不伪装成已知类型。
 */
function conflictItemText(item: {
  object_type: string;
  object_id: string;
  label: string | null;
}): string {
  if (item.object_type === "network") {
    return item.label ? `重叠网络：${item.label}` : `重叠网络（${item.object_id}）`;
  }
  if (item.object_type === "ip_pool") {
    return item.label ? `地址池：${item.label}` : `地址池（${item.object_id}）`;
  }
  if (item.object_type === "ip_address") {
    return item.label ? `IP 地址：${item.label}` : `IP 地址（${item.object_id}）`;
  }
  if (item.object_type === "cluster") {
    return item.label ? `集群：${item.label}` : `集群（${item.object_id}）`;
  }
  return item.label ? `${item.object_type}：${item.label}` : item.object_type;
}

/**
 * F008 Networks 网络管理页（Contract §4/§5/§6）：
 * - 列表：GET /api/v1/networks（分页 page/page_size 1–100、排序白名单、
 *   过滤 cluster_id/status/auto_allocate/q AND 组合，软删可见性开关仅对具
 *   VIEW_DELETED 的角色显示，服务端仍鉴权）；Loading / Empty / Error 显式区分，
 *   错误绝不伪装成空列表；
 * - 创建 / 编辑（WRITE）：NetworkForm（cluster 选择器 / cidr / gateway /
 *   status / auto_allocate / metadata）；提交带 version（编辑）；
 *   409 unique_conflict{field:"name"} → name 字段级错误；
 *   409 range_overlap{field:"cidr"} → cidr 字段级错误 + 重叠明细；
 *   409 reference_exists（改 cidr/cluster 被未删 Pool/IP 引用）明确呈现；
 *   409 VERSION_CONFLICT → 刷新后重改，不静默重试；
 * - 删除（DELETE_OBJECT，软删不级联）：被未删 Pool/IP 引用 → 409 reference_exists；
 * - 恢复（RESTORE，ADMIN）：409 not_deleted / unique_conflict / dependency_deleted
 *   （所属 Cluster 仍删）/ range_overlap 明确呈现。
 */
export default function NetworksPage({ user }: NetworksPageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const [clusterOptions, setClusterOptions] = useState<ClusterOptionsState>({ kind: "loading" });
  const [clusterReloadToken, setClusterReloadToken] = useState(0);
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  // 筛选表单草稿：点击“筛选”才应用（避免每次击键发请求）
  const [draft, setDraft] = useState({
    q: DEFAULT_QUERY.q,
    clusterId: DEFAULT_QUERY.clusterId,
    status: DEFAULT_QUERY.status,
    autoAllocate: DEFAULT_QUERY.autoAllocate,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<NetworkActionError | null>(null);
  const [action, setAction] = useState<{ kind: "delete" | "restore"; network: Network } | null>(
    null,
  ); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<NetworkActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // 集群下拉（表单 cluster 选择器 + 过滤），仅未删除集群
  useEffect(() => {
    let cancelled = false;
    setClusterOptions({ kind: "loading" });
    listClusters({ page: 1, page_size: 100, sort: "code", order: "asc" })
      .then((data) => {
        if (!cancelled) {
          setClusterOptions({ kind: "success", clusters: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setClusterOptions({
            kind: "error",
            message: isApiError(error)
              ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
              : displayError(error),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clusterReloadToken]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listNetworks({
      q: query.q || undefined,
      cluster_id: query.clusterId || undefined,
      status: query.status || undefined,
      auto_allocate: query.autoAllocate === "" ? undefined : query.autoAllocate === "true",
      deleted: query.deleted,
      page: query.page,
      page_size: query.pageSize,
      sort: query.sort,
      order: query.order,
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
  }, [query, reloadToken]);

  /** 表单原始值 → 解析 + metadata 解析（复用 ClusterForm.parseMetadataText）。 */
  function parseSubmission(values: NetworkFormValues) {
    const parsed = parseNetworkFormValues(values);
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

  function handleCreateSubmit(values: NetworkFormValues) {
    const parsed = parseSubmission(values);
    if (parsed === null) {
      return;
    }
    setSubmitting(true);
    setFormError(null);
    createNetwork(buildNetworkCreateInput(values.cluster, parsed.fields, parsed.metadata))
      .then(() => {
        // 201：创建成功（version=1）；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 unique_conflict / range_overlap / 422 / 403 明确呈现
        setFormError(describeNetworkActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: NetworkFormValues) {
    if (mode.kind !== "edit") {
      return;
    }
    const parsed = parseSubmission(values);
    if (parsed === null) {
      return;
    }
    const payload = buildNetworkPatch(mode.network, values.cluster, parsed.fields, parsed.metadata);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改至少一个字段后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
        rangeConflicts: [],
        dependencyConflicts: [],
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateNetwork(mode.network.id, payload)
      .then(() => {
        // 200：version+1；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / unique_conflict / range_overlap / reference_exists
        // / 422 / 403：明确呈现，不静默重试
        setFormError(describeNetworkActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该网络并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.network.id;
    setFormError(null);
    setSubmitting(true);
    getNetwork(id)
      .then(({ network: fresh }) => {
        setMode({ kind: "edit", network: fresh });
        setFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setFormError(describeNetworkActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete(network: Network) {
    setActionError(null);
    setAction({ kind: "delete", network });
  }

  function confirmDelete() {
    if (action === null) {
      return;
    }
    const network = action.network;
    setActionBusy(true);
    setActionError(null);
    deleteNetwork(network.id, network.version)
      .then(() => {
        // 204：软删成功（不级联）；重载列表
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 reference_exists（未删 Pool / IP）/ VERSION_CONFLICT 明确呈现
        setActionError(describeNetworkActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore(network: Network) {
    setActionError(null);
    setAction({ kind: "restore", network });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const network = action.network;
    setActionBusy(true);
    setActionError(null);
    restoreNetwork(network.id, network.version)
      .then(() => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        // / range_overlap 明确呈现
        setActionError(describeNetworkActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery((current) => ({
      ...current,
      q: draft.q,
      clusterId: draft.clusterId,
      status: draft.status,
      autoAllocate: draft.autoAllocate,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", clusterId: "", status: "", autoAllocate: "" });
    setQuery((current) => ({
      ...current,
      q: "",
      clusterId: "",
      status: "",
      autoAllocate: "",
      page: 1,
    }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: NetworkSortField) {
    setQuery((current) => ({
      ...current,
      sort: field,
      order: current.sort === field && current.order === "asc" ? "desc" : "asc",
      page: 1,
    }));
  }

  function changeDeleted(deleted: DeletedMode) {
    setQuery((current) => ({ ...current, deleted, page: 1 }));
  }

  function gotoPage(page: number) {
    setQuery((current) => ({ ...current, page }));
  }

  function changePageSize(pageSize: number) {
    setQuery((current) => ({ ...current, pageSize, page: 1 }));
  }

  const clusters = clusterOptions.kind === "success" ? clusterOptions.clusters : [];
  const showDeletedColumn = query.deleted !== "exclude";

  return (
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>Networks（网络）</h2>
        {canWrite && mode.kind === "list" && (
          <Button
            type="button"
            variant="primary"
            onClick={() => {
              setFormError(null);
              setMode({ kind: "create" });
            }}
          >
            新建网络
          </Button>
        )}
      </div>

      {mode.kind === "list" && (
        <>
          {clusterOptions.kind === "error" && (
            <ErrorState
              message={`加载集群下拉失败：${clusterOptions.message}`}
              action={
                <Button type="button" onClick={() => setClusterReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          <form className="filter-form" onSubmit={applyFilters}>
            <div className="form-field">
              <label htmlFor="network-filter-q">模糊搜索（name 子串，大小写不敏感）</label>
              <Input
                id="network-filter-q"
                type="text"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="form-field">
              <label htmlFor="network-filter-cluster">所属集群</label>
              <Select
                id="network-filter-cluster"
                value={draft.clusterId}
                onChange={(event) => setDraft({ ...draft, clusterId: event.target.value })}
                disabled={clusterOptions.kind !== "success"}
              >
                <option value="">全部（默认）</option>
                {clusters.map((cluster) => (
                  <option key={cluster.id} value={cluster.id}>
                    {cluster.code} — {cluster.name}
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-field">
              <label htmlFor="network-filter-status">状态</label>
              <Select
                id="network-filter-status"
                value={draft.status}
                onChange={(event) =>
                  setDraft({ ...draft, status: event.target.value as "" | NetworkStatus })
                }
              >
                <option value="">全部（默认）</option>
                <option value="ACTIVE">ACTIVE</option>
                <option value="INACTIVE">INACTIVE</option>
              </Select>
            </div>
            <div className="form-field">
              <label htmlFor="network-filter-auto">auto_allocate</label>
              <Select
                id="network-filter-auto"
                value={draft.autoAllocate}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    autoAllocate: event.target.value as "" | "true" | "false",
                  })
                }
              >
                <option value="">全部（默认）</option>
                <option value="true">true（允许自动分配）</option>
                <option value="false">false（不允许）</option>
              </Select>
            </div>
            <div className="filter-actions">
              <Button type="submit">筛选</Button>
              <Button type="button" onClick={resetFilters}>
                重置
              </Button>
            </div>
          </form>

          {canViewDeleted && (
            <div className="form-field deleted-toggle">
              <label htmlFor="network-deleted-mode">软删可见性（需 VIEW_DELETED 权限）</label>
              <Select
                id="network-deleted-mode"
                value={query.deleted}
                onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
              >
                <option value="exclude">未删除（默认）</option>
                <option value="include">全部（含已删除）</option>
                <option value="only">仅已删除</option>
              </Select>
            </div>
          )}

          {state.kind === "loading" && <LoadingState label="正在加载网络列表…" />}

          {state.kind === "error" && (
            <ErrorState
              message={`加载网络列表失败：${state.message}`}
              action={
                <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          {state.kind === "success" &&
            (state.data.items.length === 0 ? (
              <EmptyState description="没有符合条件的网络（当前过滤 / 分页下无数据，非错误）。" />
            ) : (
              <>
                <div className="table-wrap">
                  <DataTable className="data-table">
                    <thead>
                      <tr>
                        <th>cluster</th>
                        {SORT_COLUMNS.map(({ field, label }) => (
                          <th key={field}>
                            <Button
                              type="button"
                              className="sort-button"
                              onClick={() => toggleSort(field)}
                            >
                              {label}
                              {query.sort === field ? (query.order === "asc" ? " ▲" : " ▼") : ""}
                            </Button>
                          </th>
                        ))}
                        <th>gateway</th>
                        <th>auto_allocate</th>
                        <th>version</th>
                        {showDeletedColumn && <th>deleted_at</th>}
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.items.map((network) => (
                        <tr key={network.id}>
                          <td>
                            <span className="mono">{network.cluster.code}</span>
                            <span className="unset">（{network.cluster.name}）</span>
                          </td>
                          <td>
                            {network.name}
                            {network.deleted_at !== null && (
                              <StatusTag tone="error">已删除</StatusTag>
                            )}
                          </td>
                          <td className="mono">{network.cidr}</td>
                          <td>
                            <StatusTag tone={statusTone(network.status)}>{network.status}</StatusTag>
                          </td>
                          <td className="mono">{network.created_at}</td>
                          <td className="mono">{network.updated_at}</td>
                          <td className="mono">
                            {network.gateway ?? <span className="unset">—</span>}
                          </td>
                          <td>{network.auto_allocate ? "true" : "false"}</td>
                          <td>{network.version}</td>
                          {showDeletedColumn && (
                            <td className="mono">
                              {network.deleted_at ?? <span className="unset">—</span>}
                            </td>
                          )}
                          <td>
                            {canWrite && network.deleted_at === null && (
                              <Button
                                type="button"
                                className="link-button"
                                onClick={() => {
                                  setFormError(null);
                                  setMode({ kind: "edit", network });
                                  setFormKey((key) => key + 1);
                                }}
                              >
                                编辑
                              </Button>
                            )}
                            {canDelete && network.deleted_at === null && (
                              <Button
                                type="button"
                                danger
                                className="link-button"
                                onClick={() => requestDelete(network)}
                              >
                                删除
                              </Button>
                            )}
                            {canRestore && network.deleted_at !== null && (
                              <Button
                                type="button"
                                className="link-button"
                                onClick={() => requestRestore(network)}
                              >
                                恢复
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </DataTable>
                </div>
                <Pagination
                  page={state.data.page}
                  pageSize={state.data.page_size}
                  total={state.data.total}
                  appliedPageSize={query.pageSize}
                  onGotoPage={gotoPage}
                  onChangePageSize={changePageSize}
                />
              </>
            ))}

          {/* F020：删除 / 恢复二次确认模态（替代原内联确认；请求语义不变，错误块随正文呈现） */}
          <ConfirmDialog
            open={action !== null}
            title={action?.kind === "delete" ? "删除网络" : "恢复网络"}
            okText={action?.kind === "delete" ? "确认删除" : "确认恢复"}
            danger={action?.kind === "delete"}
            confirmLoading={actionBusy}
            onConfirm={action?.kind === "delete" ? confirmDelete : confirmRestore}
            onCancel={() => {
              setAction(null);
              setActionError(null);
            }}
          >
            {action !== null && (
              <div className="detail-actions">
                <WarningState
                  message={
                    action.kind === "delete" ? (
                      <span>
                        确认软删除网络 {action.network.name}？（不级联删除关联对象；同集群内名称软删后可复用；
                        若仍有未删除的地址池或 IP 引用，将被拒绝并显示引用列表）
                      </span>
                    ) : (
                      <span>
                        确认恢复网络 {action.network.name}？（仅恢复自身，不级联；将重检同集群名称唯一性、
                        所属集群有效性与 CIDR 不重叠，失败不覆盖新对象；version 递增）
                      </span>
                    )
                  }
                />
                {actionError && (
                  <ErrorState message={<div className="form-error">
                    <p>{actionError.message}</p>
                    {actionError.references.length > 0 && (
                      <ul>
                        {actionError.references.map((reference) => (
                          <li key={`${reference.object_type}-${reference.object_id}`}>
                            {conflictItemText(reference)}（{reference.object_id}）
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.rangeConflicts.length > 0 && (
                      <ul>
                        {actionError.rangeConflicts.map((conflict) => (
                          <li key={`${conflict.object_type}-${conflict.object_id}`}>
                            {conflictItemText(conflict)}（{conflict.object_id}）
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.dependencyConflicts.length > 0 && (
                      <ul>
                        {actionError.dependencyConflicts.map((conflict) => (
                          <li key={`${conflict.object_type}-${conflict.object_id}`}>
                            {conflictItemText(conflict)}（{conflict.object_id}）
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

      {mode.kind === "create" && (
        <NetworkForm
          mode="create"
          clusters={clusters}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleCreateSubmit}
          onCancel={() => setMode({ kind: "list" })}
        />
      )}

      {mode.kind === "edit" && (
        <NetworkForm
          key={formKey}
          mode="edit"
          clusters={clusters}
          network={mode.network}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleEditSubmit}
          onCancel={() => setMode({ kind: "list" })}
          onRefresh={refreshAfterConflict}
        />
      )}
    </SurfaceCard>
  );
}
