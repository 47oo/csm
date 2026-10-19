import { Button, Input, Select, DataTable } from "../components/ui/controls";
import { EmptyState, ErrorState, LoadingState } from "../components/ui/feedback";
import { ServerPagination as Pagination, StatusTag, SurfaceCard, statusTone } from "../components/ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import {
  listClusters,
  type Cluster,
  type ClusterListResponse,
  type ClusterSortField,
  type ClusterStatus,
  type DeletedMode,
  type SortOrder,
} from "../api/clusters";

interface ClustersPageProps {
  user: User;
  /** 打开详情（携带 deleted 上下文：已删详情需显式 deleted=true，Contract §5）。 */
  onOpenCluster: (cluster: Cluster) => void;
  /** 打开创建页（入口按钮按 WRITE 权限显示）。 */
  onCreate: () => void;
}

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: ClusterListResponse }
  | { kind: "error"; message: string };

/** 已应用的查询（排序 / 分页 / 过滤 / 软删可见性，Contract §4/§5）。 */
interface AppliedQuery {
  q: string;
  code: string;
  status: "" | ClusterStatus;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
  sort: ClusterSortField;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  code: "",
  status: "",
  deleted: "exclude",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

const SORT_COLUMNS: { field: ClusterSortField; label: string }[] = [
  { field: "code", label: "code" },
  { field: "name", label: "name" },
  { field: "status", label: "status" },
  { field: "created_at", label: "创建时间" },
  { field: "updated_at", label: "更新时间" },
];

/**
 * F003 Clusters 列表页（Contract §4/§5/§6.1）：
 * - 分页（page / page_size 1–100）、排序白名单、过滤（status / code 精确 / q 模糊）AND 组合；
 * - 软删可见性开关仅对具 VIEW_DELETED 的角色显示（服务端仍鉴权，隐藏不替代）；
 * - Loading / Success / Empty / Error 显式区分：错误绝不伪装成空列表；
 * - 403（如无 VIEW_DELETED 却请求 include/only）/ 422 / 500 明确呈现并允许重试。
 */
export default function ClustersPage({ user, onOpenCluster, onCreate }: ClustersPageProps) {
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");
  const canWrite = user.permissions.includes("WRITE");

  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  // 筛选表单草稿：点击“筛选”才应用（避免每次击键发请求）；“重置”恢复默认过滤
  const [draft, setDraft] = useState({
    q: DEFAULT_QUERY.q,
    code: DEFAULT_QUERY.code,
    status: DEFAULT_QUERY.status,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listClusters({
      q: query.q || undefined,
      code: query.code || undefined,
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
      code: draft.code,
      status: draft.status,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", code: "", status: "" });
    setQuery((current) => ({ ...current, q: "", code: "", status: "", page: 1 }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: ClusterSortField) {
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
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>Clusters（集群）</h2>
        {canWrite && (
          <Button type="button" onClick={onCreate}>
            新建集群
          </Button>
        )}
      </div>

      <form className="filter-form" onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="cluster-filter-q">模糊搜索（code / name 子串）</label>
          <Input
            id="cluster-filter-q"
            type="text"
            value={draft.q}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            placeholder="大小写不敏感子串匹配"
          />
        </div>
        <div className="form-field">
          <label htmlFor="cluster-filter-code">code 精确过滤</label>
          <Input
            id="cluster-filter-code"
            type="text"
            value={draft.code}
            onChange={(event) => setDraft({ ...draft, code: event.target.value })}
            placeholder="按归一化后的 code 精确匹配"
          />
        </div>
        <div className="form-field">
          <label htmlFor="cluster-filter-status">状态</label>
          <Select
            id="cluster-filter-status"
            value={draft.status}
            onChange={(event) =>
              setDraft({ ...draft, status: event.target.value as "" | ClusterStatus })
            }
          >
            <option value="">全部（默认）</option>
            <option value="ACTIVE">ACTIVE</option>
            <option value="INACTIVE">INACTIVE</option>
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
          <label htmlFor="cluster-deleted-mode">软删可见性（需 VIEW_DELETED 权限）</label>
          <Select
            id="cluster-deleted-mode"
            value={query.deleted}
            onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
          >
            <option value="exclude">未删除（默认）</option>
            <option value="include">全部（含已删除）</option>
            <option value="only">仅已删除</option>
          </Select>
        </div>
      )}

      {state.kind === "loading" && <LoadingState label="正在加载集群列表…" />}

      {state.kind === "error" && (
        <ErrorState
          message={`加载集群列表失败：${state.message}`}
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <EmptyState description="没有符合条件的集群（当前过滤 / 分页下无数据，非错误）。" />
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
                    <th>version</th>
                    {showDeletedColumn && <th>deleted_at</th>}
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((cluster) => (
                    <tr key={cluster.id}>
                      <td className="mono">{cluster.code}</td>
                      <td>{cluster.name}</td>
                      <td>
                        <StatusTag tone={statusTone(cluster.status)}>{cluster.status}</StatusTag>
                        {cluster.deleted_at !== null && (
                          <StatusTag tone="error">已删除</StatusTag>
                        )}
                      </td>
                      <td>{cluster.version}</td>
                      <td className="mono">{cluster.created_at}</td>
                      <td className="mono">{cluster.updated_at}</td>
                      {showDeletedColumn && (
                        <td className="mono">{cluster.deleted_at ?? "—"}</td>
                      )}
                      <td>
                        <Button type="button" onClick={() => onOpenCluster(cluster)}>
                          查看
                        </Button>
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
    </SurfaceCard>
  );
}
