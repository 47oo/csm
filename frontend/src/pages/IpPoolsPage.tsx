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

/** 分配模式徽标配色（沿用旧版 badge-manual/auto/reserved 的灰/蓝/红）。 */
const ALLOCATION_MODE_TAG_COLOR: Record<IpPoolAllocationMode, string> = {
  MANUAL: "default",
  AUTO: "processing",
  RESERVED: "error",
};

/** 排序列单元格渲染（地址 / 时间等宽字体；name 附“已删除”标记；模式徽标化）。 */
const SORT_CELL_RENDER: { [F in IpPoolSortField]: (ipPool: IpPool) => ReactNode } = {
  name: (ipPool) => (
    <span>
      {ipPool.name}
      {ipPool.deleted_at !== null && (
        <Tag color="red" className="ml-2">
          已删除
        </Tag>
      )}
    </span>
  ),
  start_address: (ipPool) => <span className="font-mono">{ipPool.start_address}</span>,
  end_address: (ipPool) => <span className="font-mono">{ipPool.end_address}</span>,
  allocation_mode: (ipPool) => (
    <Tag color={ALLOCATION_MODE_TAG_COLOR[ipPool.allocation_mode]}>
      {ipPool.allocation_mode}
    </Tag>
  ),
  created_at: (ipPool) => <span className="font-mono">{ipPool.created_at}</span>,
  updated_at: (ipPool) => <span className="font-mono">{ipPool.updated_at}</span>,
};

/** allocation_mode 过滤下拉选项（文案与迁移前一致）。 */
const ALLOCATION_MODE_FILTER_OPTIONS: { value: "" | IpPoolAllocationMode; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "MANUAL", label: "MANUAL（仅手动）" },
  { value: "AUTO", label: "AUTO（自动与手动）" },
  { value: "RESERVED", label: "RESERVED（保留）" },
];

/** 软删可见性选项（exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
const DELETED_MODE_OPTIONS: { value: DeletedMode; label: string }[] = [
  { value: "exclude", label: "未删除（默认）" },
  { value: "include", label: "全部（含已删除）" },
  { value: "only", label: "仅已删除" },
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
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用与参数 / 过滤排序
 * 分页与软删语义 / 四态 / 权限门控 / 删除恢复确认与冲突呈现 / 文案均保持
 * 不变）。排序仍由表头按钮切换，不用 AntD 内置 sorter；行内二次确认沿用
 * 迁移前交互（失败后确认区保持待确认状态，错误在上方 Alert 呈现）。
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

  /** 点击“筛选”才应用草稿（提交时机由 AntD Form onFinish 接管）。 */
  function applyFilters() {
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

  /** 仅开启软删可见性（include / only）时追加 deleted_at 列（与原实现口径一致）。 */
  const deletedAtColumn: NonNullable<TableProps<IpPool>["columns"]>[number] = {
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
  const columns: TableProps<IpPool>["columns"] = [
    {
      title: "network",
      key: "network",
      render: (_, ipPool) => (
        <span>
          <span className="font-mono">{ipPool.network.name}</span>
          <span className="text-gray-400">（{ipPool.network.cidr}）</span>
        </span>
      ),
    },
    ...SORT_COLUMNS.map(
      ({ field, label }): NonNullable<TableProps<IpPool>["columns"]>[number] => ({
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
        render: (_: unknown, ipPool: IpPool) => SORT_CELL_RENDER[field](ipPool),
      }),
    ),
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeletedColumn ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_, ipPool) => (
        <>
          {canWrite && ipPool.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
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
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestDelete(ipPool)}
            >
              删除
            </Button>
          )}
          {canRestore && ipPool.deleted_at !== null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRestore(ipPool)}
            >
              恢复
            </Button>
          )}
        </>
      ),
    },
  ];

  return (
    <Card
      title="IP Pools（地址池）"
      extra={
        canWrite && mode.kind === "list" ? (
          <Button
            type="primary"
            onClick={() => {
              setFormError(null);
              setMode({ kind: "create" });
            }}
          >
            新建地址池
          </Button>
        ) : undefined
      }
    >
      {mode.kind === "list" && (
        <>
          {networkOptions.kind === "error" && (
            <Alert
              className="mb-4"
              type="error"
              showIcon
              message={`加载网络下拉失败：${networkOptions.message}`}
              action={
                <Button
                  size="small"
                  danger
                  onClick={() => setNetworkReloadToken((token) => token + 1)}
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
              <label htmlFor="ip-pool-filter-q" className="text-sm text-gray-700">
                模糊搜索（name 子串，大小写不敏感）
              </label>
              <Input
                id="ip-pool-filter-q"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="flex w-56 flex-col gap-1">
              <label htmlFor="ip-pool-filter-network" className="text-sm text-gray-700">
                所属网络
              </label>
              <Select<string>
                id="ip-pool-filter-network"
                className="w-full"
                value={draft.networkId}
                onChange={(value) => setDraft({ ...draft, networkId: value })}
                disabled={networkOptions.kind !== "success"}
                options={[
                  { value: "", label: "全部（默认）" },
                  ...networks.map((network) => ({
                    value: network.id,
                    label: `${network.name}（${network.cidr}）`,
                  })),
                ]}
              />
            </div>
            <div className="flex w-52 flex-col gap-1">
              <label htmlFor="ip-pool-filter-mode" className="text-sm text-gray-700">
                allocation_mode
              </label>
              <Select<"" | IpPoolAllocationMode>
                id="ip-pool-filter-mode"
                className="w-full"
                value={draft.allocationMode}
                onChange={(value) => setDraft({ ...draft, allocationMode: value })}
                options={ALLOCATION_MODE_FILTER_OPTIONS}
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
              <label htmlFor="ip-pool-deleted-mode" className="text-sm text-gray-700">
                软删可见性（需 VIEW_DELETED 权限）
              </label>
              <Select<DeletedMode>
                id="ip-pool-deleted-mode"
                value={query.deleted}
                onChange={(value) => changeDeleted(value)}
                options={DELETED_MODE_OPTIONS}
              />
            </div>
          )}

          {state.kind === "loading" && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
              <Spin />
              <span>正在加载地址池列表…</span>
            </div>
          )}

          {state.kind === "error" && (
            <Alert
              className="mt-4"
              type="error"
              showIcon
              message={`加载地址池列表失败：${state.message}`}
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
                description="没有符合条件的地址池（当前过滤 / 分页下无数据，非错误）。"
              />
            ) : (
              <>
                <Table<IpPool>
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

          {(actionError !== null || action !== null) && (
            <div className="mt-5 flex flex-col gap-3">
              {actionError && (
                <Alert
                  type="error"
                  showIcon
                  message={actionError.message}
                  description={
                    <>
                      {actionError.rangeConflicts.length > 0 && (
                        <ul className="list-disc pl-5">
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
                            <ul className="list-disc pl-5">
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
                        <ul className="list-disc pl-5">
                          {actionError.dependencyConflicts.map((conflict) => (
                            <li key={`${conflict.object_type}-${conflict.object_id}`}>
                              所属网络仍处于已删除状态或已不存在（{conflict.object_id}）
                            </li>
                          ))}
                        </ul>
                      )}
                      {actionError.versionConflict && (
                        <Button
                          size="small"
                          danger
                          className="mt-2"
                          disabled={actionBusy}
                          onClick={() => {
                            setActionError(null);
                            setAction(null);
                            setReloadToken((token) => token + 1);
                          }}
                        >
                          刷新最新数据
                        </Button>
                      )}
                    </>
                  }
                />
              )}

              {action !== null && (
                <div className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <span>
                    {action.kind === "delete" ? (
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
                    )}
                  </span>
                  <Button
                    type="primary"
                    danger={action.kind === "delete"}
                    onClick={action.kind === "delete" ? confirmDelete : confirmRestore}
                    disabled={actionBusy}
                  >
                    {actionBusy
                      ? action.kind === "delete"
                        ? "正在删除…"
                        : "正在恢复…"
                      : action.kind === "delete"
                        ? "确认删除"
                        : "确认恢复"}
                  </Button>
                  <Button onClick={() => setAction(null)} disabled={actionBusy}>
                    取消
                  </Button>
                </div>
              )}
            </div>
          )}
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
    </Card>
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
