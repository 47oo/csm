import { useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Empty, Select, Spin, Table, type TableProps } from "antd";
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

/** 过滤下拉选项（“全部（默认）” + 8 类；文案与迁移前一致）。 */
const OBJECT_TYPE_FILTER_OPTIONS: { value: "" | DeletedObjectType; label: string }[] = [
  { value: "", label: "全部（默认）" },
  ...OBJECT_TYPE_OPTIONS,
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

/** 按服务端返回的分页口径推总页数（与迁移前 Pagination 组件一致）。 */
function totalPagesOf(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

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

  const columns: TableProps<DeletedItem>["columns"] = [
    {
      title: "object_type",
      dataIndex: "object_type",
      key: "object_type",
      render: (_, item) => (
        <span className="font-mono">{OBJECT_TYPE_LABELS[item.object_type]}</span>
      ),
    },
    { title: "label", dataIndex: "label", key: "label" },
    {
      title: "cluster",
      key: "cluster",
      render: (_, item) =>
        item.cluster ? (
          `${item.cluster.code}（${item.cluster.name}）`
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
    {
      title: "object_id",
      dataIndex: "object_id",
      key: "object_id",
      render: (_, item) => <span className="font-mono">{item.object_id}</span>,
    },
    { title: "version", dataIndex: "version", key: "version" },
    {
      title: (
        <Button type="link" size="small" className="px-0" onClick={toggleOrder}>
          deleted_at{query.order === "asc" ? " ▲" : " ▼"}
        </Button>
      ),
      dataIndex: "deleted_at",
      key: "deleted_at",
      render: (_, item) => <span className="font-mono">{item.deleted_at}</span>,
    },
    {
      title: "操作",
      key: "actions",
      render: (_, item) =>
        canRestore ? (
          <Button
            type="link"
            size="small"
            className="px-0"
            onClick={() => requestRestore(item)}
          >
            恢复
          </Button>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
  ];

  return (
    <div>
      <Alert
        className="mb-4"
        type="info"
        showIcon
        message="跨 8 类对象（Cluster / Resource / Interface / Network / IP Pool / IP Address / Service / ServiceEndpoint）的已软删对象统一视图（不含用户账号；账号以停用代替删除）。恢复按对象类型调用其所属域的既有恢复端点：仅恢复当前对象、不级联；将重检唯一性与依赖有效性，失败不覆盖新对象。"
      />

      <form
        className="mb-4 flex flex-wrap items-end gap-4 border-b border-gray-100 pb-4"
        onSubmit={applyFilters}
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="deleted-filter-object-type" className="text-sm text-gray-700">
            object_type
          </label>
          <Select<"" | DeletedObjectType>
            id="deleted-filter-object-type"
            className="w-60"
            value={draft.objectType}
            onChange={(value) => setDraft({ objectType: value })}
            options={OBJECT_TYPE_FILTER_OPTIONS}
          />
        </div>
        <div className="flex gap-2">
          <Button type="primary" htmlType="submit">
            筛选
          </Button>
          <Button onClick={resetFilters}>重置</Button>
        </div>
      </form>

      {state.kind === "loading" && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
          <Spin />
          <span>正在加载已删除对象…</span>
        </div>
      )}

      {state.kind === "error" && (
        <Alert
          type="error"
          showIcon
          message={`加载已删除对象失败：${state.message}`}
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
            description="没有已删除对象（当前过滤 / 分页下无数据，非错误）。"
          />
        ) : (
          <>
            <Table<DeletedItem>
              className="mt-4"
              rowKey={(item) => `${item.object_type}-${item.object_id}`}
              size="middle"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={state.data.items}
              columns={columns}
            />
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span>
                共 {state.data.total} 条 · 第 {state.data.page} /{" "}
                {totalPagesOf(state.data.total, state.data.page_size)} 页
              </span>
              <Button
                disabled={state.data.page <= 1}
                onClick={() => gotoPage(state.data.page - 1)}
              >
                上一页
              </Button>
              <Button
                disabled={
                  state.data.page >= totalPagesOf(state.data.total, state.data.page_size)
                }
                onClick={() => gotoPage(state.data.page + 1)}
              >
                下一页
              </Button>
              <label className="flex items-center gap-2">
                每页
                <Select
                  className="w-20"
                  value={query.pageSize}
                  onChange={(value) => changePageSize(value)}
                  options={[
                    { value: 20, label: "20" },
                    { value: 50, label: "50" },
                    { value: 100, label: "100" },
                  ]}
                />
                条
              </label>
            </div>
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
                actionError.versionConflict ? (
                  <Button
                    size="small"
                    danger
                    disabled={actionBusy}
                    onClick={() => {
                      setActionError(null);
                      setAction(null);
                      setReloadToken((token) => token + 1);
                    }}
                  >
                    刷新最新数据
                  </Button>
                ) : null
              }
            />
          )}

          {action !== null && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
              <span>
                确认恢复 {OBJECT_TYPE_LABELS[action.item.object_type]}
                「{action.item.label}」？（仅恢复当前对象、不级联；将按该对象类型的
                既有规则重检唯一性与依赖有效性，失败不覆盖新对象；version 递增）
              </span>
              <Button type="primary" onClick={confirmRestore} disabled={actionBusy}>
                {actionBusy ? "正在恢复…" : "确认恢复"}
              </Button>
              <Button onClick={() => setAction(null)} disabled={actionBusy}>
                取消
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
