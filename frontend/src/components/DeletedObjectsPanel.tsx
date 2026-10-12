import { useEffect, useState, type FormEvent } from "react";
import type { User } from "../api/auth";
import {
  describeDeletedActionError,
  describeDeletedQueryError,
  listDeleted,
  restoreDeletedItem,
  type DeletedActionError,
  type DeletedItem,
  type DeletedListResponse,
  type DeletedObjectType,
} from "../api/deleted";

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: DeletedListResponse }
  | { kind: "error"; message: string };

/** 已应用的查询（object_type 过滤 + 分页 + 排序；sort 恒 deleted_at，Contract §3.1）。 */
interface AppliedQuery {
  objectType: "" | DeletedObjectType;
  page: number;
  pageSize: number;
  order: "asc" | "desc";
}

const DEFAULT_QUERY: AppliedQuery = {
  objectType: "",
  page: 1,
  pageSize: 20,
  order: "desc",
};

const OBJECT_TYPE_OPTIONS: { value: DeletedObjectType; label: string }[] = [
  { value: "cluster", label: "cluster（集群）" },
  { value: "resource", label: "resource（资源）" },
  { value: "interface", label: "interface（网络接口）" },
  { value: "network", label: "network（网络）" },
  { value: "ip_pool", label: "ip_pool（IP 池）" },
  { value: "ip_address", label: "ip_address（IP 地址）" },
  { value: "service", label: "service（服务）" },
  { value: "service_endpoint", label: "service_endpoint（服务端点）" },
];

const OBJECT_TYPE_LABELS: Record<DeletedObjectType, string> = {
  cluster: "cluster",
  resource: "resource",
  interface: "interface",
  network: "network",
  ip_pool: "ip_pool",
  ip_address: "ip_address",
  service: "service",
  service_endpoint: "service_endpoint",
};

interface DeletedObjectsPanelProps {
  user: User;
}

/**
 * 已删除对象统一管理面板（F015，Contract §3/§5；§21/T24/T41；DR-216/DR-224）：
 * - 列表：GET /api/v1/deleted（VIEW_DELETED，仅 ADMIN）：跨 8 类已软删对象聚合
 *   （不含 user，账号以停用代替删除）；object_type 过滤 + 分页 + deleted_at
 *   排序（同刻 object_type/object_id 升序由服务端保证）；Loading / Empty /
 *   Error 显式区分，错误绝不伪装成空列表；
 * - 恢复：按 object_type 调各域既有 restore（POST /api/v1/{object}/{id}/
 *   restore?version=，RESTORE，不新增统一写端点）；仅恢复当前对象、不级联、
 *   重检唯一 / 依赖、失败不覆盖（I-5/I-6/I-7）；409 reason
 *   （unique_conflict / dependency_deleted / not_deleted）/ VERSION_CONFLICT
 *   明确呈现，不静默重试；
 * - 恢复按钮仅对具 RESTORE 的角色显示；服务端仍鉴权（隐藏不替代）。
 */
export default function DeletedObjectsPanel({ user }: DeletedObjectsPanelProps) {
  const canRestore = user.permissions.includes("RESTORE");

  const [draft, setDraft] = useState<{ objectType: "" | DeletedObjectType }>({
    objectType: "",
  });
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [action, setAction] = useState<{ item: DeletedItem } | null>(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<DeletedActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listDeleted({
      object_type: query.objectType === "" ? undefined : query.objectType,
      page: query.page,
      page_size: query.pageSize,
      sort: "deleted_at",
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
        // 401/403/422/500/网络层：显式呈现，可重试，不伪装成空列表
        setState({ kind: "error", message: describeDeletedQueryError(error).message });
      });
    return () => {
      cancelled = true;
    };
  }, [query, reloadToken]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery((current) => ({ ...current, objectType: draft.objectType, page: 1 }));
  }

  function resetFilters() {
    setDraft({ objectType: "" });
    setQuery((current) => ({ ...current, objectType: "", page: 1 }));
  }

  /** 排序仅 deleted_at：点击表头切换 asc/desc；回到第 1 页。 */
  function toggleOrder() {
    setQuery((current) => ({
      ...current,
      order: current.order === "asc" ? "desc" : "asc",
      page: 1,
    }));
  }

  function gotoPage(page: number) {
    setQuery((current) => ({ ...current, page }));
  }

  function changePageSize(pageSize: number) {
    setQuery((current) => ({ ...current, pageSize, page: 1 }));
  }

  function requestRestore(item: DeletedItem) {
    setActionError(null);
    setAction({ item });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const item = action.item;
    setActionBusy(true);
    setActionError(null);
    restoreDeletedItem(item.object_type, item.object_id, item.version)
      .then(() => {
        // 200：恢复成功（仅恢复自身不级联、deleted_at=null、version+1、写
        // RESTORE Audit 同事务）；重载列表，该对象不再出现在已删聚合中
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 unique_conflict / dependency_deleted / not_deleted /
        // VERSION_CONFLICT：明确呈现 reason，不静默重试、不覆盖新对象
        setActionError(describeDeletedActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  return (
    <div>
      <p className="status">
        跨 8 类对象（Cluster / Resource / Interface / Network / IP Pool / IP Address /
        Service / ServiceEndpoint）的已软删对象统一视图（不含用户账号；账号以停用
        代替删除）。恢复按对象类型调用其所属域的既有恢复端点：仅恢复当前对象、
        不级联；将重检唯一性与依赖有效性，失败不覆盖新对象。
      </p>

      <form className="filter-form" onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="deleted-filter-object-type">object_type</label>
          <select
            id="deleted-filter-object-type"
            value={draft.objectType}
            onChange={(event) =>
              setDraft({ objectType: event.target.value as "" | DeletedObjectType })
            }
          >
            <option value="">全部（默认）</option>
            {OBJECT_TYPE_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="filter-actions">
          <button type="submit">筛选</button>
          <button type="button" onClick={resetFilters}>
            重置
          </button>
        </div>
      </form>

      {state.kind === "loading" && (
        <p className="status status-loading">正在加载已删除对象…</p>
      )}

      {state.kind === "error" && (
        <div className="status status-error" role="alert">
          <p>加载已删除对象失败：{state.message}</p>
          <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
            重试
          </button>
        </div>
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <p className="status status-empty">
            没有已删除对象（当前过滤 / 分页下无数据，非错误）。
          </p>
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>object_type</th>
                    <th>label</th>
                    <th>cluster</th>
                    <th>object_id</th>
                    <th>version</th>
                    <th>
                      <button type="button" className="sort-button" onClick={toggleOrder}>
                        deleted_at
                        {query.order === "asc" ? " ▲" : " ▼"}
                      </button>
                    </th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((item) => (
                    <tr key={`${item.object_type}-${item.object_id}`}>
                      <td className="mono">{OBJECT_TYPE_LABELS[item.object_type]}</td>
                      <td>{item.label}</td>
                      <td>
                        {item.cluster ? (
                          `${item.cluster.code}（${item.cluster.name}）`
                        ) : (
                          <span className="unset">—</span>
                        )}
                      </td>
                      <td className="mono">{item.object_id}</td>
                      <td>{item.version}</td>
                      <td className="mono">{item.deleted_at}</td>
                      <td>
                        {canRestore ? (
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => requestRestore(item)}
                          >
                            恢复
                          </button>
                        ) : (
                          <span className="unset">—</span>
                        )}
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

      <div className="detail-actions">
        {actionError && (
          <div className="status status-error action-error" role="alert">
            <p>{actionError.message}</p>
            {actionError.versionConflict && (
              <p>
                <button
                  type="button"
                  onClick={() => {
                    setActionError(null);
                    setAction(null);
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

        {action !== null && (
          <div className="inline-confirm">
            <span>
              确认恢复 {OBJECT_TYPE_LABELS[action.item.object_type]}
              「{action.item.label}」？（仅恢复当前对象、不级联；将按该对象类型的
              既有规则重检唯一性与依赖有效性，失败不覆盖新对象；version 递增）
            </span>
            <button type="button" onClick={confirmRestore} disabled={actionBusy}>
              {actionBusy ? "正在恢复…" : "确认恢复"}
            </button>
            <button type="button" onClick={() => setAction(null)} disabled={actionBusy}>
              取消
            </button>
          </div>
        )}
      </div>
    </div>
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
