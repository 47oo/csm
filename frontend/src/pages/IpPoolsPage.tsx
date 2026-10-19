import { Button, Input, Select, DataTable } from "../components/ui/controls";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState, WarningState } from "../components/ui/feedback";
import { ServerPagination as Pagination, StatusTag, SurfaceCard, statusTone } from "../components/ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import { listNetworks, type Network } from "../api/networks";
import {
  createIpPool,
  deleteIpPool,
  describeIpPoolActionError,
  getIpPool,
  listIpPools,
  restoreIpPool,
  updateIpPool,
  type DeletedMode,
  type IpPool,
  type IpPoolActionError,
  type IpPoolAllocationMode,
  type IpPoolListResponse,
  type IpPoolSortField,
  type SortOrder,
} from "../api/ipPools";
import IpPoolForm from "../components/IpPoolForm";
import {
  buildIpPoolCreateInput,
  buildIpPoolPatch,
  parseIpPoolFormValues,
  type IpPoolFormValues,
} from "../components/ipPoolForm";

interface IpPoolsPageProps {
  user: User;
}

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: IpPoolListResponse }
  | { kind: "error"; message: string };

/** 网络下拉数据加载状态（仅未删除网络；分页上限 100，Contract §4）。 */
type NetworkOptionsState =
  | { kind: "loading" }
  | { kind: "success"; networks: Network[]; total: number }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单 / 编辑表单。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "edit"; ipPool: IpPool };

/** 已应用的查询（排序 / 分页 / 过滤 / 软删可见性，Contract §4/§5）。 */
interface AppliedQuery {
  q: string;
  networkId: string;
  allocationMode: "" | IpPoolAllocationMode;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
  sort: IpPoolSortField;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  networkId: "",
  allocationMode: "",
  deleted: "exclude",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

const SORT_COLUMNS: { field: IpPoolSortField; label: string }[] = [
  { field: "name", label: "name" },
  { field: "start_address", label: "start_address" },
  { field: "end_address", label: "end_address" },
  { field: "allocation_mode", label: "allocation_mode" },
  { field: "created_at", label: "创建时间" },
  { field: "updated_at", label: "更新时间" },
];

/**
 * F009 IP Pools 地址池管理页（Contract §4/§5/§6）：
 * - 列表：GET /api/v1/ip-pools（分页 page/page_size 1–100、排序白名单、过滤
 *   network_id/allocation_mode/q AND 组合，软删可见性开关仅对具 VIEW_DELETED
 *   的角色显示，服务端仍鉴权）；Loading / Empty / Error 显式区分，错误绝不
 *   伪装成空列表；
 * - 创建 / 编辑（WRITE）：IpPoolForm（network 选择器（创建可选、编辑只读，
 *   DR-107）/ 起止 IPv4 / allocation_mode / description）；提交带 version
 *   （编辑）；409 unique_conflict{field:"name"} → name 字段级错误；
 *   409 range_overlap → start/end 字段级错误 + 重叠池明细；
 *   409 address_in_use → 对应字段错误 + 占用数量与明细预览（conflicts_truncated
 *   呈现截断）；409 VERSION_CONFLICT → 刷新后重改，不静默重试；
 * - 删除（DELETE_OBJECT，软删不级联；不做 IP 分配来源引用检查、不回收已分配
 *   IP，DR-108）；
 * - 恢复（RESTORE）：409 not_deleted / unique_conflict / dependency_deleted
 *   （所属 Network 仍删）/ 422（Network cidr 变更后越界）/ range_overlap /
 *   address_in_use 明确呈现。
 */
export default function IpPoolsPage({ user }: IpPoolsPageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const [networkOptions, setNetworkOptions] = useState<NetworkOptionsState>({ kind: "loading" });
  const [networkReloadToken, setNetworkReloadToken] = useState(0);
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  // 筛选表单草稿：点击“筛选”才应用（避免每次击键发请求）
  const [draft, setDraft] = useState({
    q: DEFAULT_QUERY.q,
    networkId: DEFAULT_QUERY.networkId,
    allocationMode: DEFAULT_QUERY.allocationMode,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<IpPoolActionError | null>(null);
  const [action, setAction] = useState<{ kind: "delete" | "restore"; ipPool: IpPool } | null>(
    null,
  ); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<IpPoolActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // 网络下拉（表单 network 选择器 + 过滤），仅未删除网络
  useEffect(() => {
    let cancelled = false;
    setNetworkOptions({ kind: "loading" });
    listNetworks({ page: 1, page_size: 100, sort: "name", order: "asc" })
      .then((data) => {
        if (!cancelled) {
          setNetworkOptions({ kind: "success", networks: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setNetworkOptions({
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
  }, [networkReloadToken]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listIpPools({
      network_id: query.networkId || undefined,
      allocation_mode: query.allocationMode || undefined,
      q: query.q || undefined,
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

  // ---- 创建（POST，Contract §6.2）----

  function handleCreateSubmit(values: IpPoolFormValues) {
    const parsed = parseIpPoolFormValues(values);
    if (!parsed.ok) {
      return; // 表单本地校验已拦截；防御双保险（不发起请求）
    }
    if (values.network === "") {
      return; // 同上：创建必须选择网络
    }
    setSubmitting(true);
    setFormError(null);
    createIpPool(buildIpPoolCreateInput(values.network, parsed.fields))
      .then(() => {
        // 201：创建成功（version=1）；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 unique_conflict / range_overlap / address_in_use / 422 / 403 明确呈现
        setFormError(describeIpPoolActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: IpPoolFormValues) {
    if (mode.kind !== "edit") {
      return;
    }
    const parsed = parseIpPoolFormValues(values);
    if (!parsed.ok) {
      return;
    }
    const payload = buildIpPoolPatch(mode.ipPool, parsed.fields);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改至少一个字段后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        rangeConflicts: [],
        occupancy: null,
        dependencyConflicts: [],
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateIpPool(mode.ipPool.id, payload)
      .then(() => {
        // 200：version+1；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / unique_conflict / range_overlap / address_in_use
        // / 422 / 403：明确呈现，不静默重试
        setFormError(describeIpPoolActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该地址池并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.ipPool.id;
    setFormError(null);
    setSubmitting(true);
    getIpPool(id)
      .then(({ ip_pool: fresh }) => {
        setMode({ kind: "edit", ipPool: fresh });
        setFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setFormError(describeIpPoolActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete(ipPool: IpPool) {
    setActionError(null);
    setAction({ kind: "delete", ipPool });
  }

  function confirmDelete() {
    if (action === null) {
      return;
    }
    const ipPool = action.ipPool;
    setActionBusy(true);
    setActionError(null);
    deleteIpPool(ipPool.id, ipPool.version)
      .then(() => {
        // 204：软删成功（不级联、不回收已分配 IP，DR-108）；重载列表
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT 等明确呈现
        setActionError(describeIpPoolActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore(ipPool: IpPool) {
    setActionError(null);
    setAction({ kind: "restore", ipPool });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const ipPool = action.ipPool;
    setActionBusy(true);
    setActionError(null);
    restoreIpPool(ipPool.id, ipPool.version)
      .then(() => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        // / range_overlap / address_in_use、422（cidr 变更后越界）明确呈现
        setActionError(describeIpPoolActionError(error));
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
      networkId: draft.networkId,
      allocationMode: draft.allocationMode,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", networkId: "", allocationMode: "" });
    setQuery((current) => ({
      ...current,
      q: "",
      networkId: "",
      allocationMode: "",
      page: 1,
    }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: IpPoolSortField) {
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

  const networks = networkOptions.kind === "success" ? networkOptions.networks : [];
  const showDeletedColumn = query.deleted !== "exclude";

  return (
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>IP Pools（地址池）</h2>
        {canWrite && mode.kind === "list" && (
          <Button
            type="button"
            onClick={() => {
              setFormError(null);
              setMode({ kind: "create" });
            }}
          >
            新建地址池
          </Button>
        )}
      </div>

      {mode.kind === "list" && (
        <>
          {networkOptions.kind === "error" && (
            <ErrorState
              message={`加载网络下拉失败：${networkOptions.message}`}
              action={
                <Button type="button" onClick={() => setNetworkReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          <form className="filter-form" onSubmit={applyFilters}>
            <div className="form-field">
              <label htmlFor="ip-pool-filter-q">模糊搜索（name 子串，大小写不敏感）</label>
              <Input
                id="ip-pool-filter-q"
                type="text"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="form-field">
              <label htmlFor="ip-pool-filter-network">所属网络</label>
              <Select
                id="ip-pool-filter-network"
                value={draft.networkId}
                onChange={(event) => setDraft({ ...draft, networkId: event.target.value })}
                disabled={networkOptions.kind !== "success"}
              >
                <option value="">全部（默认）</option>
                {networks.map((network) => (
                  <option key={network.id} value={network.id}>
                    {network.name}（{network.cidr}）
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-field">
              <label htmlFor="ip-pool-filter-mode">allocation_mode</label>
              <Select
                id="ip-pool-filter-mode"
                value={draft.allocationMode}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    allocationMode: event.target.value as "" | IpPoolAllocationMode,
                  })
                }
              >
                <option value="">全部（默认）</option>
                <option value="MANUAL">MANUAL（仅手动）</option>
                <option value="AUTO">AUTO（自动与手动）</option>
                <option value="RESERVED">RESERVED（保留）</option>
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
              <label htmlFor="ip-pool-deleted-mode">软删可见性（需 VIEW_DELETED 权限）</label>
              <Select
                id="ip-pool-deleted-mode"
                value={query.deleted}
                onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
              >
                <option value="exclude">未删除（默认）</option>
                <option value="include">全部（含已删除）</option>
                <option value="only">仅已删除</option>
              </Select>
            </div>
          )}

          {state.kind === "loading" && <LoadingState label="正在加载地址池列表…" />}

          {state.kind === "error" && (
            <ErrorState
              message={`加载地址池列表失败：${state.message}`}
              action={
                <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          {state.kind === "success" &&
            (state.data.items.length === 0 ? (
              <EmptyState description="没有符合条件的地址池（当前过滤 / 分页下无数据，非错误）。" />
            ) : (
              <>
                <div className="table-wrap">
                  <DataTable className="data-table">
                    <thead>
                      <tr>
                        <th>network</th>
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
                        <th>version</th>
                        {showDeletedColumn && <th>deleted_at</th>}
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.items.map((ipPool) => (
                        <tr key={ipPool.id}>
                          <td>
                            <span className="mono">{ipPool.network.name}</span>
                            <span className="unset">（{ipPool.network.cidr}）</span>
                          </td>
                          <td>
                            {ipPool.name}
                            {ipPool.deleted_at !== null && (
                              <StatusTag tone="error">已删除</StatusTag>
                            )}
                          </td>
                          <td className="mono">{ipPool.start_address}</td>
                          <td className="mono">{ipPool.end_address}</td>
                          <td>
                            <StatusTag tone={statusTone(ipPool.allocation_mode)}>
                              {ipPool.allocation_mode}
                            </StatusTag>
                          </td>
                          <td className="mono">{ipPool.created_at}</td>
                          <td className="mono">{ipPool.updated_at}</td>
                          <td>{ipPool.version}</td>
                          {showDeletedColumn && (
                            <td className="mono">
                              {ipPool.deleted_at ?? <span className="unset">—</span>}
                            </td>
                          )}
                          <td>
                            {canWrite && ipPool.deleted_at === null && (
                              <Button
                                type="button"
                                className="link-button"
                                onClick={() => {
                                  setFormError(null);
                                  setMode({ kind: "edit", ipPool });
                                  setFormKey((key) => key + 1);
                                }}
                              >
                                编辑
                              </Button>
                            )}
                            {canDelete && ipPool.deleted_at === null && (
                              <Button
                                type="button"
                                danger
                                className="link-button"
                                onClick={() => requestDelete(ipPool)}
                              >
                                删除
                              </Button>
                            )}
                            {canRestore && ipPool.deleted_at !== null && (
                              <Button
                                type="button"
                                className="link-button"
                                onClick={() => requestRestore(ipPool)}
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
            title={action?.kind === "delete" ? "删除地址池" : "恢复地址池"}
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
                        确认软删除地址池 {action.ipPool.name}？（不级联删除关联对象；不回收、
                        不删除已分配的 IP 地址；同网络内名称与地址范围软删后可复用）
                      </span>
                    ) : (
                      <span>
                        确认恢复地址池 {action.ipPool.name}？（仅恢复自身，不级联；将重检同网络
                        名称唯一性、所属网络有效性、起止仍属网络 CIDR、范围不重叠，RESERVED
                        另检占用冲突，失败不覆盖新对象；version 递增）
                      </span>
                    )
                  }
                />
                {actionError && (
                  <ErrorState message={<div className="form-error">
                    <p>{actionError.message}</p>
                    {actionError.rangeConflicts.length > 0 && (
                      <ul>
                        {actionError.rangeConflicts.map((conflict) => (
                          <li key={`${conflict.object_type}-${conflict.object_id}`}>
                            重叠地址池：
                            {conflict.label ? `${conflict.label}（` : "("}
                            {conflict.start_address} – {conflict.end_address}）
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.occupancy !== null && (
                      <>
                        <p>
                          占用冲突共 {actionError.occupancy.count} 个未删除 IP 地址
                          {actionError.occupancy.truncated
                            ? "（以下明细已被截断，仅显示前若干条；完整明细可通过 IP 地址列表查询）"
                            : "："}
                        </p>
                        {actionError.occupancy.conflicts.length > 0 && (
                          <ul>
                            {actionError.occupancy.conflicts.map((item) => (
                              <li key={`${item.object_type}-${item.object_id}`}>
                                {occupancyItemText(item)}
                              </li>
                            ))}
                          </ul>
                        )}
                      </>
                    )}
                    {actionError.dependencyConflicts.length > 0 && (
                      <ul>
                        {actionError.dependencyConflicts.map((conflict) => (
                          <li key={`${conflict.object_type}-${conflict.object_id}`}>
                            所属网络仍处于已删除状态或已不存在（{conflict.object_id}）
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
        <IpPoolForm
          mode="create"
          networks={networks}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleCreateSubmit}
          onCancel={() => setMode({ kind: "list" })}
        />
      )}

      {mode.kind === "edit" && (
        <IpPoolForm
          key={formKey}
          mode="edit"
          networks={networks}
          ipPool={mode.ipPool}
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

/** address_in_use 明细条目文案（含未绑定；接口 / 资源引用缺失时如实展示）。 */
function occupancyItemText(item: {
  object_type: string;
  object_id: string;
  address: string;
  bound: boolean;
  interface_id: string | null;
  resource_id: string | null;
  resource_hostname: string | null;
}): string {
  const parts: string[] = [item.address];
  if (item.bound) {
    parts.push(
      item.interface_id !== null ? `已绑定接口（${item.interface_id}）` : "已绑定接口",
    );
  } else {
    parts.push("未绑定接口");
  }
  if (item.resource_hostname !== null) {
    parts.push(
      item.resource_id !== null
        ? `资源 ${item.resource_hostname}（${item.resource_id}）`
        : `资源 ${item.resource_hostname}`,
    );
  } else if (item.resource_id !== null) {
    parts.push(`资源（${item.resource_id}）`);
  }
  return parts.join(" — ");
}
