import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  type TableProps,
} from "antd";
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

/** 排序列单元格渲染（code / 时间列等宽字体；status 徽标化并附“已删除”标记）。 */
const SORT_CELL_RENDER: { [F in ClusterSortField]: (cluster: Cluster) => ReactNode } = {
  code: (cluster) => <span className="font-mono">{cluster.code}</span>,
  name: (cluster) => cluster.name,
  status: (cluster) => (
    <span>
      <Tag color={cluster.status === "ACTIVE" ? "success" : "default"}>{cluster.status}</Tag>
      {cluster.deleted_at !== null && (
        <Tag color="red" className="ml-2">
          已删除
        </Tag>
      )}
    </span>
  ),
  created_at: (cluster) => <span className="font-mono">{cluster.created_at}</span>,
  updated_at: (cluster) => <span className="font-mono">{cluster.updated_at}</span>,
};

/** 状态过滤下拉选项（“全部（默认）” + 两种状态；文案与迁移前一致）。 */
const STATUS_FILTER_OPTIONS: { value: "" | ClusterStatus; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "ACTIVE", label: "ACTIVE" },
  { value: "INACTIVE", label: "INACTIVE" },
];

/** 软删可见性选项（exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
const DELETED_MODE_OPTIONS: { value: DeletedMode; label: string }[] = [
  { value: "exclude", label: "未删除（默认）" },
  { value: "include", label: "全部（含已删除）" },
  { value: "only", label: "仅已删除" },
];

/**
 * F003 Clusters 列表页（Contract §4/§5/§6.1）：
 * - 分页（page / page_size 1–100）、排序白名单、过滤（status / code 精确 / q 模糊）AND 组合；
 * - 软删可见性开关仅对具 VIEW_DELETED 的角色显示（服务端仍鉴权，隐藏不替代）；
 * - Loading / Success / Empty / Error 显式区分：错误绝不伪装成空列表；
 * - 403（如无 VIEW_DELETED 却请求 include/only）/ 422 / 500 明确呈现并允许重试。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 组合过滤与排序分页
 * 参数 / 四态 / 权限门控 / 软删开关 / 文案均保持不变）。迁移同时修正了旧版表体
 * 单元格与表头的列序错位（version / created_at / updated_at 现与表头一致）。
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

  /** 点击“筛选”才应用草稿（提交时机由 AntD Form onFinish 接管）。 */
  function applyFilters() {
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

  /** 仅开启软删可见性（include / only）时追加 deleted_at 列（与原实现口径一致）。 */
  const deletedAtColumn: NonNullable<TableProps<Cluster>["columns"]>[number] = {
    title: "deleted_at",
    dataIndex: "deleted_at",
    key: "deleted_at",
    render: (value: string | null) =>
      value !== null ? (
        <span className="font-mono">{value}</span>
      ) : (
        <span className="text-gray-400">—</span>
      ),
  };

  /** 列定义（文案与数据口径同旧版；排序由表头按钮切换，不用 AntD 内置 sorter）。 */
  const columns: TableProps<Cluster>["columns"] = [
    ...SORT_COLUMNS.map(
      ({ field, label }): NonNullable<TableProps<Cluster>["columns"]>[number] => ({
        title: (
          <Button
            type="link"
            size="small"
            className="px-0 font-semibold"
            onClick={() => toggleSort(field)}
          >
            {label}
            {query.sort === field ? (query.order === "asc" ? " ▲" : " ▼") : ""}
          </Button>
        ),
        dataIndex: field,
        key: field,
        render: (_: unknown, cluster: Cluster) => SORT_CELL_RENDER[field](cluster),
      }),
    ),
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeletedColumn ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_, cluster) => (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() => onOpenCluster(cluster)}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <Card
      className="mt-6"
      title="Clusters（集群）"
      extra={
        canWrite ? (
          <Button type="primary" onClick={onCreate}>
            新建集群
          </Button>
        ) : undefined
      }
    >
      <Form
        onFinish={applyFilters}
        className="flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-gray-100 pb-4"
      >
        <div className="flex w-56 flex-col gap-1">
          <label htmlFor="cluster-filter-q" className="text-sm text-gray-700">
            模糊搜索（code / name 子串）
          </label>
          <Input
            id="cluster-filter-q"
            value={draft.q}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            placeholder="大小写不敏感子串匹配"
          />
        </div>
        <div className="flex w-56 flex-col gap-1">
          <label htmlFor="cluster-filter-code" className="text-sm text-gray-700">
            code 精确过滤
          </label>
          <Input
            id="cluster-filter-code"
            value={draft.code}
            onChange={(event) => setDraft({ ...draft, code: event.target.value })}
            placeholder="按归一化后的 code 精确匹配"
          />
        </div>
        <div className="flex w-40 flex-col gap-1">
          <label htmlFor="cluster-filter-status" className="text-sm text-gray-700">
            状态
          </label>
          <Select<"" | ClusterStatus>
            id="cluster-filter-status"
            className="w-full"
            value={draft.status}
            onChange={(value) => setDraft({ ...draft, status: value })}
            options={STATUS_FILTER_OPTIONS}
          />
        </div>
        <div className="flex gap-2">
          <Button type="primary" htmlType="submit">
            筛选
          </Button>
          <Button onClick={resetFilters}>重置</Button>
        </div>
      </Form>

      {canViewDeleted && (
        <div className="mt-4 flex w-56 flex-col gap-1">
          <label htmlFor="cluster-deleted-mode" className="text-sm text-gray-700">
            软删可见性（需 VIEW_DELETED 权限）
          </label>
          <Select<DeletedMode>
            id="cluster-deleted-mode"
            value={query.deleted}
            onChange={(value) => changeDeleted(value)}
            options={DELETED_MODE_OPTIONS}
          />
        </div>
      )}

      {state.kind === "loading" && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
          <Spin />
          <span>正在加载集群列表…</span>
        </div>
      )}

      {state.kind === "error" && (
        <Alert
          className="mt-4"
          type="error"
          showIcon
          message={`加载集群列表失败：${state.message}`}
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
            description="没有符合条件的集群（当前过滤 / 分页下无数据，非错误）。"
          />
        ) : (
          <>
            <Table<Cluster>
              className="mt-4"
              rowKey="id"
              size="middle"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={state.data.items}
              columns={columns}
            />
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
    </Card>
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

/** 分页条（AntD Button / Select 承担控件，文案与行为同迁移前）。 */
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
    <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-gray-600">
      <span>
        共 {total} 条 · 第 {page} / {totalPages} 页
      </span>
      <Button disabled={page <= 1} onClick={() => onGotoPage(page - 1)}>
        上一页
      </Button>
      <Button disabled={page >= totalPages} onClick={() => onGotoPage(page + 1)}>
        下一页
      </Button>
      <label className="flex items-center gap-2">
        每页
        <Select<number>
          className="w-20"
          value={appliedPageSize}
          onChange={(value) => onChangePageSize(value)}
          options={[
            { value: 20, label: "20" },
            { value: 50, label: "50" },
            { value: 100, label: "100" },
          ]}
        />
        条
      </label>
    </div>
  );
}
