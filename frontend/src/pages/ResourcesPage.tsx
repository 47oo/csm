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
import ResourceImportPanel from "../components/ResourceImportPanel";

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

/** 资源状态徽标配色（沿用旧版 badge-idle/alloc/down/unknown 的绿/蓝/红/灰）。 */
const STATUS_TAG_COLOR: Record<ResourceStatus, string> = {
  IDLE: "success",
  ALLOC: "processing",
  DOWN: "error",
  UNKNOWN: "default",
};

/** 排序列单元格渲染（hostname / 时间等宽字体；status 徽标化并附“已删除”标记）。 */
const SORT_CELL_RENDER: { [F in ResourceSortField]: (resource: Resource) => ReactNode } = {
  hostname: (resource) => (
    <span>
      <span className="font-mono">{resource.hostname}</span>
      {resource.deleted_at !== null && (
        <Tag color="red" className="ml-2">
          已删除
        </Tag>
      )}
    </span>
  ),
  resource_type: (resource) => resource.resource_type,
  role: (resource) => resource.role,
  status: (resource) => <Tag color={STATUS_TAG_COLOR[resource.status]}>{resource.status}</Tag>,
  created_at: (resource) => <span className="font-mono">{resource.created_at}</span>,
  updated_at: (resource) => <span className="font-mono">{resource.updated_at}</span>,
};

/** 类型过滤下拉选项（“全部（默认）” + 两种类型；文案与迁移前一致）。 */
const TYPE_FILTER_OPTIONS: { value: "" | ResourceType; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "BARE_METAL", label: "BARE_METAL（物理机）" },
  { value: "VIRTUAL_MACHINE", label: "VIRTUAL_MACHINE（虚拟机）" },
];

/** 角色过滤下拉选项。 */
const ROLE_FILTER_OPTIONS: { value: "" | ResourceRole; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "COMPUTE", label: "COMPUTE" },
  { value: "LOGIN", label: "LOGIN" },
  { value: "MANAGEMENT", label: "MANAGEMENT" },
  { value: "STORAGE", label: "STORAGE" },
  { value: "SERVICE", label: "SERVICE" },
  { value: "GPU", label: "GPU" },
  { value: "OTHER", label: "OTHER" },
];

/** 状态过滤下拉选项。 */
const STATUS_FILTER_OPTIONS: { value: "" | ResourceStatus; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "IDLE", label: "IDLE" },
  { value: "ALLOC", label: "ALLOC" },
  { value: "DOWN", label: "DOWN" },
  { value: "UNKNOWN", label: "UNKNOWN" },
];

/** 软删可见性选项（exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
const DELETED_MODE_OPTIONS: { value: DeletedMode; label: string }[] = [
  { value: "exclude", label: "未删除（默认）" },
  { value: "include", label: "全部（含已删除）" },
  { value: "only", label: "仅已删除" },
];

/**
 * F004 Resources 列表页（Contract §4/§5/§6.1）：
 * - 分页（page / page_size 1–100）、排序白名单（sort=hostname 实际按 hostname_key）、
 *   过滤（cluster code 精确 / type / role / status 枚举 / q hostname 模糊）AND 组合；
 * - 软删可见性开关仅对具 VIEW_DELETED 的角色显示（服务端仍鉴权，隐藏不替代）；
 * - Loading / Success / Empty / Error 显式区分：错误绝不伪装成空列表；
 * - 403（如无 VIEW_DELETED 却请求 include/only）/ 422 / 500 明确呈现并允许重试；
 * - F014：工具栏提供 CSV / .xlsx 批量导入入口（仅 IMPORT 权限显示，服务端仍
 *   鉴权；面板内预校验 → 确认导入，成功后刷新列表）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 过滤排序分页与软删
 * 参数 / 四态 / 权限门控 / 文案均保持不变）。排序仍由表头按钮切换，不用 AntD
 * 内置 sorter。
 */
export default function ResourcesPage({ user, onOpenResource, onCreate }: ResourcesPageProps) {
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");
  const canWrite = user.permissions.includes("WRITE");
  const canImport = user.permissions.includes("IMPORT");
  const [showImport, setShowImport] = useState(false);

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

  /** 点击“筛选”才应用草稿（提交时机由 AntD Form onFinish 接管）。 */
  function applyFilters() {
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

  /** 仅开启软删可见性（include / only）时追加 deleted_at 列（与原实现口径一致）。 */
  const deletedAtColumn: NonNullable<TableProps<Resource>["columns"]>[number] = {
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
  const columns: TableProps<Resource>["columns"] = [
    ...SORT_COLUMNS.map(
      ({ field, label }): NonNullable<TableProps<Resource>["columns"]>[number] => ({
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
        render: (_: unknown, resource: Resource) => SORT_CELL_RENDER[field](resource),
      }),
    ),
    {
      title: "所属集群",
      dataIndex: ["cluster", "code"],
      key: "cluster",
      render: (code: string) => <span className="font-mono">{code}</span>,
    },
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeletedColumn ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_, resource) => (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() => onOpenResource(resource)}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <>
      <Card
        title="Resources（资源）"
        extra={
          canImport || canWrite ? (
            <div className="flex gap-2">
              {canImport && (
                <Button onClick={() => setShowImport((visible) => !visible)}>
                  {showImport ? "收起批量导入" : "批量导入…"}
                </Button>
              )}
              {canWrite && (
                <Button type="primary" onClick={onCreate}>
                  新建资源
                </Button>
              )}
            </div>
          ) : undefined
        }
      >
        <Form
          onFinish={applyFilters}
          className="flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-gray-100 pb-4"
        >
          <div className="flex w-56 flex-col gap-1">
            <label htmlFor="resource-filter-q" className="text-sm text-gray-700">
              模糊搜索（hostname 子串）
            </label>
            <Input
              id="resource-filter-q"
              value={draft.q}
              onChange={(event) => setDraft({ ...draft, q: event.target.value })}
              placeholder="大小写不敏感子串匹配"
            />
          </div>
          <div className="flex w-56 flex-col gap-1">
            <label htmlFor="resource-filter-cluster" className="text-sm text-gray-700">
              集群 code 精确过滤
            </label>
            <Input
              id="resource-filter-cluster"
              value={draft.cluster}
              onChange={(event) => setDraft({ ...draft, cluster: event.target.value })}
              placeholder="按集群 code（大小写不敏感）精确匹配"
            />
          </div>
          <div className="flex w-52 flex-col gap-1">
            <label htmlFor="resource-filter-type" className="text-sm text-gray-700">
              类型
            </label>
            <Select<"" | ResourceType>
              id="resource-filter-type"
              className="w-full"
              value={draft.type}
              onChange={(value) => setDraft({ ...draft, type: value })}
              options={TYPE_FILTER_OPTIONS}
            />
          </div>
          <div className="flex w-40 flex-col gap-1">
            <label htmlFor="resource-filter-role" className="text-sm text-gray-700">
              角色
            </label>
            <Select<"" | ResourceRole>
              id="resource-filter-role"
              className="w-full"
              value={draft.role}
              onChange={(value) => setDraft({ ...draft, role: value })}
              options={ROLE_FILTER_OPTIONS}
            />
          </div>
          <div className="flex w-36 flex-col gap-1">
            <label htmlFor="resource-filter-status" className="text-sm text-gray-700">
              状态
            </label>
            <Select<"" | ResourceStatus>
              id="resource-filter-status"
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
            <label htmlFor="resource-deleted-mode" className="text-sm text-gray-700">
              软删可见性（需 VIEW_DELETED 权限）
            </label>
            <Select<DeletedMode>
              id="resource-deleted-mode"
              value={query.deleted}
              onChange={(value) => changeDeleted(value)}
              options={DELETED_MODE_OPTIONS}
            />
          </div>
        )}

        {state.kind === "loading" && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
            <Spin />
            <span>正在加载资源列表…</span>
          </div>
        )}

        {state.kind === "error" && (
          <Alert
            className="mt-4"
            type="error"
            showIcon
            message={`加载资源列表失败：${state.message}`}
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
              description="没有符合条件的资源（当前过滤 / 分页下无数据，非错误）。"
            />
          ) : (
            <>
              <Table<Resource>
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

      {showImport && (
        <div className="mt-4">
          <ResourceImportPanel onImported={() => setReloadToken((token) => token + 1)} />
        </div>
      )}
    </>
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
