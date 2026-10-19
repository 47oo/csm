import { Button, Input, Select, DataTable } from "../components/ui/controls";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { EmptyState, ErrorState, LoadingState, WarningState } from "../components/ui/feedback";
import { ServerPagination as Pagination, StatusTag, SurfaceCard, statusTone } from "../components/ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import {
  deleteResource,
  describeResourceActionError,
  listResources,
  type DeletedMode,
  type Resource,
  type ResourceActionError,
  type ResourceListResponse,
  type ResourceRole,
  type ResourceSortField,
  type ResourceStatus,
  type ResourceType,
  type SortOrder,
} from "../api/resources";
import { conflictItemText, referenceItemText } from "../components/resourceActionMessages.ts";
import ResourceImportPanel from "../components/ResourceImportPanel";
import ResourceInterfaceIpImportPanel from "../components/ResourceInterfaceIpImportPanel";

interface ResourcesPageProps {
  user: User;
  /** 打开详情（携带 deleted 上下文：已删详情需显式 deleted=true，Contract §5）。 */
  onOpenResource: (resource: Resource) => void;
  /** 打开创建页（入口按钮按 WRITE 权限显示）。 */
  onCreate: () => void;
}

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: ResourceListResponse }
  | { kind: "error"; message: string };

/** 已应用的查询（排序 / 分页 / 过滤 / 软删可见性，Contract §4/§5）。 */
interface AppliedQuery {
  q: string;
  cluster: string;
  type: "" | ResourceType;
  role: "" | ResourceRole;
  status: "" | ResourceStatus;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
  sort: ResourceSortField;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  cluster: "",
  type: "",
  role: "",
  status: "",
  deleted: "exclude",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

const SORT_COLUMNS: { field: ResourceSortField; label: string }[] = [
  { field: "hostname", label: "hostname" },
  { field: "resource_type", label: "类型" },
  { field: "role", label: "角色" },
  { field: "status", label: "状态" },
  { field: "created_at", label: "创建时间" },
  { field: "updated_at", label: "更新时间" },
];

/**
 * F004 Resources 列表页（Contract §4/§5/§6.1）：
 * - 分页（page / page_size 1–100）、排序白名单（sort=hostname 实际按 hostname_key）、
 *   过滤（cluster code 精确 / type / role / status 枚举 / q hostname 模糊）AND 组合；
 * - 软删可见性开关仅对具 VIEW_DELETED 的角色显示（服务端仍鉴权，隐藏不替代）；
 * - Loading / Success / Empty / Error 显式区分：错误绝不伪装成空列表；
 * - 403（如无 VIEW_DELETED 却请求 include/only）/ 422 / 500 明确呈现并允许重试；
 * - F014：工具栏提供 CSV / .xlsx 批量导入入口（仅 IMPORT 权限显示，服务端仍
 *   鉴权；面板内预校验 → 确认导入，成功后刷新列表）；
 * - F023：另提供「资源+网卡+IP」三元组批量导入入口（统一宽模板 26 列，
 *   独立第三套面板；同样仅 IMPORT 权限显示，不影响 F014 既有面板）；
 * - F021：行内单行删除入口（仅 DELETE_OBJECT 且未删行显示；复用详情页删除
 *   语义与 ConfirmDialog 二次确认；409 引用 / 版本冲突在对话框内呈现）。
 */
export default function ResourcesPage({ user, onOpenResource, onCreate }: ResourcesPageProps) {
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");
  const canWrite = user.permissions.includes("WRITE");
  const canImport = user.permissions.includes("IMPORT");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const [showImport, setShowImport] = useState(false);
  const [showInterfaceIpImport, setShowInterfaceIpImport] = useState(false);

  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  // 筛选表单草稿：点击“筛选”才应用（避免每次击键发请求）；“重置”恢复默认过滤
  const [draft, setDraft] = useState({
    q: DEFAULT_QUERY.q,
    cluster: DEFAULT_QUERY.cluster,
    type: DEFAULT_QUERY.type,
    role: DEFAULT_QUERY.role,
    status: DEFAULT_QUERY.status,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [action, setAction] = useState<{ kind: "delete"; resource: Resource } | null>(
    null,
  ); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<ResourceActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listResources({
      q: query.q || undefined,
      cluster: query.cluster || undefined,
      type: query.type || undefined,
      role: query.role || undefined,
      status: query.status || undefined,
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
        // 401 已由 client 全局处理器回登录页；403 / 422 / 500 / 网络错误显式呈现
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

  // ---- 删除（软删，DELETE_OBJECT，Contract §6.5；F021 行内入口）----

  function requestDelete(resource: Resource) {
    setActionError(null);
    setAction({ kind: "delete", resource });
  }

  function confirmDelete() {
    if (action === null) {
      return;
    }
    const resource = action.resource;
    setActionBusy(true);
    setActionError(null);
    deleteResource(resource.id, resource.version)
      .then(() => {
        // 204：软删成功（不级联）；关闭对话框并重载列表（过滤/排序/分页 query 全保留）
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 reference_exists（宿主机被未删 VM 引用）/ VERSION_CONFLICT
        // 在对话框内明确呈现；保持对话框打开，不静默重试
        setActionError(describeResourceActionError(error));
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
      cluster: draft.cluster,
      type: draft.type,
      role: draft.role,
      status: draft.status,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", cluster: "", type: "", role: "", status: "" });
    setQuery((current) => ({
      ...current,
      q: "",
      cluster: "",
      type: "",
      role: "",
      status: "",
      page: 1,
    }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: ResourceSortField) {
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

  const showDeletedColumn = query.deleted !== "exclude";

  return (
    <>
      <SurfaceCard className="panel">
        <div className="table-toolbar">
          <h2>Resources（资源）</h2>
          <div className="filter-actions">
            {canImport && (
              <Button type="button" onClick={() => setShowImport((visible) => !visible)}>
                {showImport ? "收起批量导入" : "批量导入…"}
              </Button>
            )}
            {canImport && (
              <Button
                type="button"
                onClick={() => setShowInterfaceIpImport((visible) => !visible)}
              >
                {showInterfaceIpImport ? "收起资源+网卡+IP 导入" : "资源+网卡+IP 批量导入…"}
              </Button>
            )}
            {canWrite && (
              <Button type="button" onClick={onCreate}>
                新建资源
              </Button>
            )}
          </div>
        </div>

        <form className="filter-form" onSubmit={applyFilters}>
          <div className="form-field">
            <label htmlFor="resource-filter-q">模糊搜索（hostname 子串）</label>
            <Input
              id="resource-filter-q"
              type="text"
              value={draft.q}
              onChange={(event) => setDraft({ ...draft, q: event.target.value })}
              placeholder="大小写不敏感子串匹配"
            />
          </div>
          <div className="form-field">
            <label htmlFor="resource-filter-cluster">集群 code 精确过滤</label>
            <Input
              id="resource-filter-cluster"
              type="text"
              value={draft.cluster}
              onChange={(event) => setDraft({ ...draft, cluster: event.target.value })}
              placeholder="按集群 code（大小写不敏感）精确匹配"
            />
          </div>
          <div className="form-field">
            <label htmlFor="resource-filter-type">类型</label>
            <Select
              id="resource-filter-type"
              value={draft.type}
              onChange={(event) =>
                setDraft({ ...draft, type: event.target.value as "" | ResourceType })
              }
            >
              <option value="">全部（默认）</option>
              <option value="BARE_METAL">BARE_METAL（物理机）</option>
              <option value="VIRTUAL_MACHINE">VIRTUAL_MACHINE（虚拟机）</option>
            </Select>
          </div>
          <div className="form-field">
            <label htmlFor="resource-filter-role">角色</label>
            <Select
              id="resource-filter-role"
              value={draft.role}
              onChange={(event) =>
                setDraft({ ...draft, role: event.target.value as "" | ResourceRole })
              }
            >
              <option value="">全部（默认）</option>
              <option value="COMPUTE">COMPUTE</option>
              <option value="LOGIN">LOGIN</option>
              <option value="MANAGEMENT">MANAGEMENT</option>
              <option value="STORAGE">STORAGE</option>
              <option value="SERVICE">SERVICE</option>
              <option value="GPU">GPU</option>
              <option value="OTHER">OTHER</option>
            </Select>
          </div>
          <div className="form-field">
            <label htmlFor="resource-filter-status">状态</label>
            <Select
              id="resource-filter-status"
              value={draft.status}
              onChange={(event) =>
                setDraft({ ...draft, status: event.target.value as "" | ResourceStatus })
              }
            >
              <option value="">全部（默认）</option>
              <option value="IDLE">IDLE</option>
              <option value="ALLOC">ALLOC</option>
              <option value="DOWN">DOWN</option>
              <option value="UNKNOWN">UNKNOWN</option>
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
            <label htmlFor="resource-deleted-mode">软删可见性（需 VIEW_DELETED 权限）</label>
            <Select
              id="resource-deleted-mode"
              value={query.deleted}
              onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
            >
              <option value="exclude">未删除（默认）</option>
              <option value="include">全部（含已删除）</option>
              <option value="only">仅已删除</option>
            </Select>
          </div>
        )}

        {state.kind === "loading" && <LoadingState label="正在加载资源列表…" />}

        {state.kind === "error" && (
          <ErrorState
            message={`加载资源列表失败：${state.message}`}
            action={
              <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                重试
              </Button>
            }
          />
        )}

        {state.kind === "success" &&
          (state.data.items.length === 0 ? (
            <EmptyState description="没有符合条件的资源（当前过滤 / 分页下无数据，非错误）。" />
          ) : (
            <>
              <div className="table-wrap">
                <DataTable className="data-table">
                  <thead>
                    <tr>
                      {SORT_COLUMNS.map(({ field, label }) => (
                        <th key={field}>
                          <Button type="button" className="sort-button" onClick={() => toggleSort(field)}>
                            {label}
                            {query.sort === field ? (query.order === "asc" ? " ▲" : " ▼") : ""}
                          </Button>
                        </th>
                      ))}
                      <th>所属集群</th>
                      <th>version</th>
                      {showDeletedColumn && <th>deleted_at</th>}
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.items.map((resource) => (
                      <tr key={resource.id}>
                        <td className="mono">
                          {resource.hostname}
                          {resource.deleted_at !== null && (
                            <StatusTag tone="error">已删除</StatusTag>
                          )}
                        </td>
                        <td>{resource.resource_type}</td>
                        <td>{resource.role}</td>
                        <td>
                          <StatusTag tone={statusTone(resource.status)}>{resource.status}</StatusTag>
                        </td>
                        <td className="mono">{resource.created_at}</td>
                        <td className="mono">{resource.updated_at}</td>
                        <td>
                          <span className="mono">{resource.cluster.code}</span>
                        </td>
                        <td>{resource.version}</td>
                        {showDeletedColumn && (
                          <td className="mono">{resource.deleted_at ?? "—"}</td>
                        )}
                        <td>
                          <Button type="button" onClick={() => onOpenResource(resource)}>
                            查看
                          </Button>
                          {canDelete && resource.deleted_at === null && (
                            <Button
                              type="button"
                              danger
                              className="link-button"
                              onClick={() => requestDelete(resource)}
                            >
                              删除
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

        {/* F020/F021：行内删除二次确认模态（复用 ConfirmDialog；请求语义与详情页
            删除一致，错误块随正文呈现；取消 / 关闭不发请求） */}
        <ConfirmDialog
          open={action !== null}
          title="删除资源"
          okText="确认删除"
          danger
          confirmLoading={actionBusy}
          onConfirm={confirmDelete}
          onCancel={() => {
            setAction(null);
            setActionError(null);
          }}
        >
          {action !== null && (
            <div className="detail-actions">
              <WarningState
                message={
                  <span>
                    确认软删除资源 {action.resource.hostname}？（不级联删除关联对象；软删后
                    同集群 hostname 可被新资源复用
                    {action.resource.resource_type === "BARE_METAL"
                      ? "；若仍有未删除的虚拟机（VM）引用本宿主机，将被拒绝并显示引用列表"
                      : ""}
                    ）
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
                          {referenceItemText(reference)}（{reference.object_id}）
                        </li>
                      ))}
                    </ul>
                  )}
                  {actionError.conflicts.length > 0 && (
                    <ul>
                      {actionError.conflicts.map((conflict) => (
                        <li key={`${conflict.object_type}-${conflict.object_id}`}>
                          {conflictItemText(conflict)}
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
      </SurfaceCard>

      {showImport && (
        <ResourceImportPanel onImported={() => setReloadToken((token) => token + 1)} />
      )}

      {showInterfaceIpImport && (
        <ResourceInterfaceIpImportPanel
          onImported={() => setReloadToken((token) => token + 1)}
        />
      )}
    </>
  );
}
