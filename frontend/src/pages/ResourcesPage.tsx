import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import {
  listResources,
  type DeletedMode,
  type Resource,
  type ResourceListResponse,
  type ResourceRole,
  type ResourceSortField,
  type ResourceStatus,
  type ResourceType,
  type SortOrder,
} from "../api/resources";

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
 * - 403（如无 VIEW_DELETED 却请求 include/only）/ 422 / 500 明确呈现并允许重试。
 */
export default function ResourcesPage({ user, onOpenResource, onCreate }: ResourcesPageProps) {
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");
  const canWrite = user.permissions.includes("WRITE");

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
    <section className="panel">
      <div className="table-toolbar">
        <h2>Resources（资源）</h2>
        {canWrite && (
          <button type="button" onClick={onCreate}>
            新建资源
          </button>
        )}
      </div>

      <form className="filter-form" onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="resource-filter-q">模糊搜索（hostname 子串）</label>
          <input
            id="resource-filter-q"
            type="text"
            value={draft.q}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            placeholder="大小写不敏感子串匹配"
          />
        </div>
        <div className="form-field">
          <label htmlFor="resource-filter-cluster">集群 code 精确过滤</label>
          <input
            id="resource-filter-cluster"
            type="text"
            value={draft.cluster}
            onChange={(event) => setDraft({ ...draft, cluster: event.target.value })}
            placeholder="按集群 code（大小写不敏感）精确匹配"
          />
        </div>
        <div className="form-field">
          <label htmlFor="resource-filter-type">类型</label>
          <select
            id="resource-filter-type"
            value={draft.type}
            onChange={(event) =>
              setDraft({ ...draft, type: event.target.value as "" | ResourceType })
            }
          >
            <option value="">全部（默认）</option>
            <option value="BARE_METAL">BARE_METAL（物理机）</option>
            <option value="VIRTUAL_MACHINE">VIRTUAL_MACHINE（虚拟机）</option>
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="resource-filter-role">角色</label>
          <select
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
          </select>
        </div>
        <div className="form-field">
          <label htmlFor="resource-filter-status">状态</label>
          <select
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
          </select>
        </div>
        <div className="filter-actions">
          <button type="submit">筛选</button>
          <button type="button" onClick={resetFilters}>
            重置
          </button>
        </div>
      </form>

      {canViewDeleted && (
        <div className="form-field deleted-toggle">
          <label htmlFor="resource-deleted-mode">软删可见性（需 VIEW_DELETED 权限）</label>
          <select
            id="resource-deleted-mode"
            value={query.deleted}
            onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
          >
            <option value="exclude">未删除（默认）</option>
            <option value="include">全部（含已删除）</option>
            <option value="only">仅已删除</option>
          </select>
        </div>
      )}

      {state.kind === "loading" && (
        <p className="status status-loading">正在加载资源列表…</p>
      )}

      {state.kind === "error" && (
        <div className="status status-error" role="alert">
          <p>加载资源列表失败：{state.message}</p>
          <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
            重试
          </button>
        </div>
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <p className="status status-empty">
            没有符合条件的资源（当前过滤 / 分页下无数据，非错误）。
          </p>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    {SORT_COLUMNS.map(({ field, label }) => (
                      <th key={field}>
                        <button type="button" className="sort-button" onClick={() => toggleSort(field)}>
                          {label}
                          {query.sort === field ? (query.order === "asc" ? " ▲" : " ▼") : ""}
                        </button>
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
                          <span className="badge badge-deleted">已删除</span>
                        )}
                      </td>
                      <td>{resource.resource_type}</td>
                      <td>{resource.role}</td>
                      <td>
                        <span className={`badge badge-${resource.status.toLowerCase()}`}>
                          {resource.status}
                        </span>
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
                        <button type="button" onClick={() => onOpenResource(resource)}>
                          查看
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
    </section>
  );
}

interface PaginationProps {
  page: number;
  pageSize: number;
  total: number;
  appliedPageSize: number;
  onGotoPage: (page: number) => void;
  onChangePageSize: (pageSize: number) => void;
}

function Pagination({
  page,
  pageSize,
  total,
  appliedPageSize,
  onGotoPage,
  onChangePageSize,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pagination">
      <span>
        共 {total} 条 · 第 {page} / {totalPages} 页
      </span>
      <button type="button" disabled={page <= 1} onClick={() => onGotoPage(page - 1)}>
        上一页
      </button>
      <button type="button" disabled={page >= totalPages} onClick={() => onGotoPage(page + 1)}>
        下一页
      </button>
      <label>
        每页
        <select
          value={String(appliedPageSize)}
          onChange={(event) => onChangePageSize(Number(event.target.value))}
        >
          <option value="20">20</option>
          <option value="50">50</option>
          <option value="100">100</option>
        </select>
        条
      </label>
    </div>
  );
}
