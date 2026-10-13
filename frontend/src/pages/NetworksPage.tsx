import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Spin,
  Table,
  Tag,
  type TableProps,
} from "antd";
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

/** 排序列单元格渲染（cidr / 时间列等宽字体；status 徽标化，name 附“已删除”标记）。 */
const SORT_CELL_RENDER: { [F in NetworkSortField]: (network: Network) => ReactNode } = {
  name: (network) => (
    <span>
      {network.name}
      {network.deleted_at !== null && (
        <Tag color="red" className="ml-2">
          已删除
        </Tag>
      )}
    </span>
  ),
  cidr: (network) => <span className="font-mono">{network.cidr}</span>,
  status: (network) => (
    <Tag color={network.status === "ACTIVE" ? "success" : "default"}>{network.status}</Tag>
  ),
  created_at: (network) => <span className="font-mono">{network.created_at}</span>,
  updated_at: (network) => <span className="font-mono">{network.updated_at}</span>,
};

/** 状态过滤下拉选项（“全部（默认）” + 两种状态；文案与迁移前一致）。 */
const STATUS_FILTER_OPTIONS: { value: "" | NetworkStatus; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "ACTIVE", label: "ACTIVE" },
  { value: "INACTIVE", label: "INACTIVE" },
];

/** auto_allocate 过滤下拉选项（空 = 全部，true / false 精确过滤）。 */
const AUTO_ALLOCATE_FILTER_OPTIONS: { value: "" | "true" | "false"; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "true", label: "true（允许自动分配）" },
  { value: "false", label: "false（不允许）" },
];

/** 软删可见性选项（exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
const DELETED_MODE_OPTIONS: { value: DeletedMode; label: string }[] = [
  { value: "exclude", label: "未删除（默认）" },
  { value: "include", label: "全部（含已删除）" },
  { value: "only", label: "仅已删除" },
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
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 组合过滤与排序分页
 * 参数 / 四态 / 权限门控 / 软删开关 / 增删改与二次确认 / 全部文案保持不变）。
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

  /** 点击“筛选”才应用草稿（提交时机由 AntD Form onFinish 接管）。 */
  function applyFilters() {
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

  /** 集群过滤下拉选项（“全部（默认）” + 未删除集群，文案同迁移前）。 */
  const clusterFilterOptions = [
    { value: "", label: "全部（默认）" },
    ...clusters.map((cluster) => ({
      value: cluster.id,
      label: `${cluster.code} — ${cluster.name}`,
    })),
  ];

  /** 仅开启软删可见性（include / only）时追加 deleted_at 列（与原实现口径一致）。 */
  const deletedAtColumn: NonNullable<TableProps<Network>["columns"]>[number] = {
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
  const columns: TableProps<Network>["columns"] = [
    {
      title: "cluster",
      key: "cluster",
      render: (_: unknown, network: Network) => (
        <span>
          <span className="font-mono">{network.cluster.code}</span>
          <span className="text-gray-400">（{network.cluster.name}）</span>
        </span>
      ),
    },
    ...SORT_COLUMNS.map(
      ({ field, label }): NonNullable<TableProps<Network>["columns"]>[number] => ({
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
        render: (_: unknown, network: Network) => SORT_CELL_RENDER[field](network),
      }),
    ),
    {
      title: "gateway",
      dataIndex: "gateway",
      key: "gateway",
      render: (value: string | null) =>
        value !== null ? (
          <span className="font-mono">{value}</span>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
    {
      title: "auto_allocate",
      dataIndex: "auto_allocate",
      key: "auto_allocate",
      render: (value: boolean) => (value ? "true" : "false"),
    },
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeletedColumn ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, network: Network) => (
        <>
          {canWrite && network.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
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
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestDelete(network)}
            >
              删除
            </Button>
          )}
          {canRestore && network.deleted_at !== null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRestore(network)}
            >
              恢复
            </Button>
          )}
        </>
      ),
    },
  ];

  // 操作错误提示（AntD Alert 自带 role="alert"）：确认框开启期间渲染在 Modal 内，
  // 取消确认后保留在列表区展示（同迁移前的呈现位置与文案）
  const actionErrorAlert = actionError ? (
    <Alert
      type="error"
      message={actionError.message}
      description={
        actionError.references.length > 0 ||
        actionError.rangeConflicts.length > 0 ||
        actionError.dependencyConflicts.length > 0 ||
        actionError.versionConflict ? (
          <>
            {actionError.references.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.references.map((reference) => (
                  <li key={`${reference.object_type}-${reference.object_id}`}>
                    {conflictItemText(reference)}（{reference.object_id}）
                  </li>
                ))}
              </ul>
            )}
            {actionError.rangeConflicts.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.rangeConflicts.map((conflict) => (
                  <li key={`${conflict.object_type}-${conflict.object_id}`}>
                    {conflictItemText(conflict)}（{conflict.object_id}）
                  </li>
                ))}
              </ul>
            )}
            {actionError.dependencyConflicts.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.dependencyConflicts.map((conflict) => (
                  <li key={`${conflict.object_type}-${conflict.object_id}`}>
                    {conflictItemText(conflict)}（{conflict.object_id}）
                  </li>
                ))}
              </ul>
            )}
            {actionError.versionConflict && (
              <Button
                className="mt-2"
                onClick={() => {
                  setActionError(null);
                  setAction(null);
                  setReloadToken((token) => token + 1);
                }}
                disabled={actionBusy}
              >
                刷新最新数据
              </Button>
            )}
          </>
        ) : undefined
      }
    />
  ) : null;

  // 二次确认框的可见口径同迁移前的行内确认块：仅列表模式渲染
  const confirmVisible = mode.kind === "list";

  return (
    <>
      <Card
        className="mt-6"
        title="Networks（网络）"
        extra={
          canWrite && mode.kind === "list" ? (
            <Button
              type="primary"
              onClick={() => {
                setFormError(null);
                setMode({ kind: "create" });
              }}
            >
              新建网络
            </Button>
          ) : undefined
        }
      >
        {mode.kind === "list" && (
          <>
            {clusterOptions.kind === "error" && (
              <Alert
                className="mb-4"
                type="error"
                showIcon
                message={`加载集群下拉失败：${clusterOptions.message}`}
                action={
                  <Button
                    size="small"
                    danger
                    onClick={() => setClusterReloadToken((token) => token + 1)}
                  >
                    重试
                  </Button>
                }
              />
            )}

            <Form
              onFinish={applyFilters}
              className="flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-gray-100 pb-4"
            >
              <div className="flex w-56 flex-col gap-1">
                <label htmlFor="network-filter-q" className="text-sm text-gray-700">
                  模糊搜索（name 子串，大小写不敏感）
                </label>
                <Input
                  id="network-filter-q"
                  value={draft.q}
                  onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                  placeholder="大小写不敏感子串匹配"
                />
              </div>
              <div className="flex w-64 flex-col gap-1">
                <label htmlFor="network-filter-cluster" className="text-sm text-gray-700">
                  所属集群
                </label>
                <Select<string>
                  id="network-filter-cluster"
                  className="w-full"
                  value={draft.clusterId}
                  onChange={(value) => setDraft({ ...draft, clusterId: value })}
                  disabled={clusterOptions.kind !== "success"}
                  options={clusterFilterOptions}
                />
              </div>
              <div className="flex w-40 flex-col gap-1">
                <label htmlFor="network-filter-status" className="text-sm text-gray-700">
                  状态
                </label>
                <Select<"" | NetworkStatus>
                  id="network-filter-status"
                  className="w-full"
                  value={draft.status}
                  onChange={(value) => setDraft({ ...draft, status: value })}
                  options={STATUS_FILTER_OPTIONS}
                />
              </div>
              <div className="flex w-56 flex-col gap-1">
                <label htmlFor="network-filter-auto" className="text-sm text-gray-700">
                  auto_allocate
                </label>
                <Select<"" | "true" | "false">
                  id="network-filter-auto"
                  className="w-full"
                  value={draft.autoAllocate}
                  onChange={(value) => setDraft({ ...draft, autoAllocate: value })}
                  options={AUTO_ALLOCATE_FILTER_OPTIONS}
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
                <label htmlFor="network-deleted-mode" className="text-sm text-gray-700">
                  软删可见性（需 VIEW_DELETED 权限）
                </label>
                <Select<DeletedMode>
                  id="network-deleted-mode"
                  value={query.deleted}
                  onChange={(value) => changeDeleted(value)}
                  options={DELETED_MODE_OPTIONS}
                />
              </div>
            )}

            {state.kind === "loading" && (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
                <Spin />
                <span>正在加载网络列表…</span>
              </div>
            )}

            {state.kind === "error" && (
              <Alert
                className="mt-4"
                type="error"
                showIcon
                message={`加载网络列表失败：${state.message}`}
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
                  description="没有符合条件的网络（当前过滤 / 分页下无数据，非错误）。"
                />
              ) : (
                <>
                  <Table<Network>
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

            {action === null && actionErrorAlert && (
              <div className="mt-4">{actionErrorAlert}</div>
            )}
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
      </Card>

      {/* 删除二次确认（软删，Contract §6.5）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action !== null && action.kind === "delete" && confirmVisible}
        title={
          action !== null && action.kind === "delete"
            ? `确认软删除网络 ${action.network.name}？（不级联删除关联对象；同集群内名称软删后可复用；若仍有未删除的地址池或 IP 引用，将被拒绝并显示引用列表）`
            : ""
        }
        okText={actionBusy ? "正在删除…" : "确认删除"}
        okButtonProps={{ danger: true }}
        cancelText="取消"
        cancelButtonProps={{ disabled: actionBusy }}
        confirmLoading={actionBusy}
        maskClosable={false}
        keyboard={false}
        onOk={confirmDelete}
        onCancel={() => {
          if (!actionBusy) {
            setAction(null);
          }
        }}
      >
        {actionErrorAlert}
      </Modal>

      {/* 恢复二次确认（RESTORE，Contract §6.6）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action !== null && action.kind === "restore" && confirmVisible}
        title={
          action !== null && action.kind === "restore"
            ? `确认恢复网络 ${action.network.name}？（仅恢复自身，不级联；将重检同集群名称唯一性、所属集群有效性与 CIDR 不重叠，失败不覆盖新对象；version 递增）`
            : ""
        }
        okText={actionBusy ? "正在恢复…" : "确认恢复"}
        cancelText="取消"
        cancelButtonProps={{ disabled: actionBusy }}
        confirmLoading={actionBusy}
        maskClosable={false}
        keyboard={false}
        onOk={confirmRestore}
        onCancel={() => {
          if (!actionBusy) {
            setAction(null);
          }
        }}
      >
        {actionErrorAlert}
      </Modal>
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
