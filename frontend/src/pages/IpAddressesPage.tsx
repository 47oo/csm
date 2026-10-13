import { useEffect, useState } from "react";
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
import { listClusters, type Cluster } from "../api/clusters";
import { listNetworks, type Network } from "../api/networks";
import { listIpPools, type IpPool } from "../api/ipPools";
import {
  autoAllocateIpAddress,
  createIpAddress,
  describeIpAddressActionError,
  getIpAddress,
  getIpAddressActivity,
  listIpAddresses,
  releaseIpAddress,
  restoreIpAddress,
  updateIpAddress,
  type DeletedMode,
  type IpAddress,
  type IpAddressActionError,
  type IpAddressActivityItem,
  type IpAddressActivityResponse,
  type IpAddressListResponse,
  type IpAddressSortField,
  type SortOrder,
} from "../api/ipAddresses";
import IpAddressForm from "../components/IpAddressForm";
import {
  buildAutoAllocateInput,
  buildIpAddressPatch,
  buildManualAllocateInput,
  isValidBareIpv4,
  parseIpAddressFormValues,
  type IpAddressFormValues,
} from "../components/ipAddressForm";

interface IpAddressesPageProps {
  user: User;
  /**
   * 初始 network 过滤（F013 搜索「未绑定 IP → 所属网络」定位入口）：
   * 仅初始化 query / draft，不随后续 prop 变化重置（由 HomePage 以 key 控制重挂载）。
   */
  initialNetworkId?: string;
}

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: IpAddressListResponse }
  | { kind: "error"; message: string };

/** 过滤下拉数据加载状态（网络 / 集群 / 地址池，仅未删除；分页上限 100，Contract §4）。 */
type FilterOptionsState =
  | { kind: "loading" }
  | { kind: "success"; networks: Network[]; clusters: Cluster[]; pools: IpPool[] }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 手动分配 / 自动分配 / 编辑（绑定/解绑/转移/描述）/ Activity。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create-manual" }
  | { kind: "create-auto" }
  | { kind: "edit"; ipAddress: IpAddress }
  | { kind: "activity"; ipAddress: IpAddress };

/** Activity 加载状态（分页）。 */
type ActivityState =
  | { kind: "loading" }
  | { kind: "success"; data: IpAddressActivityResponse }
  | { kind: "error"; message: string };

/** 已应用的查询（排序 / 分页 / 过滤 / 软删可见性，Contract §4/§5）。 */
interface AppliedQuery {
  q: string;
  networkId: string;
  clusterId: string;
  poolId: string;
  /** interface UUID 精确过滤（本地校验格式；服务端非 UUID → 422）。 */
  interfaceId: string;
  /** bound：空 = 全部，true = 已绑定，false = 未绑定。 */
  bound: "" | "true" | "false";
  /** address 精确匹配（本地校验裸 IPv4 格式；服务端非法 → 422）。 */
  address: string;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
  sort: IpAddressSortField;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  networkId: "",
  clusterId: "",
  poolId: "",
  interfaceId: "",
  bound: "",
  address: "",
  deleted: "exclude",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

/** interface 过滤的 UUID 格式（本地快速校验；服务端仍权威 422）。 */
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** 软删可见性选项（exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
const DELETED_MODE_OPTIONS: { value: DeletedMode; label: string }[] = [
  { value: "exclude", label: "未删除（默认）" },
  { value: "include", label: "全部（含已删除）" },
  { value: "only", label: "仅已删除" },
];

/**
 * F010 IP Addresses 地址管理页（Contract §4/§5/§6）：
 * - 列表：GET /api/v1/ip-addresses（分页 page/page_size 1–100、排序白名单
 *   address/created_at/updated_at、过滤 network_id/cluster_id/interface_id/
 *   ip_pool_id/bound/address/q AND 组合，软删可见性开关仅对具 VIEW_DELETED
 *   的角色显示，服务端仍鉴权）；Loading / Empty / Error 显式区分，错误绝不
 *   伪装成空列表；
 * - 手动分配（POST，WRITE）：IpAddressForm（network 选择器 / 裸 IPv4 address /
 *   description）；自动分配（POST /auto-allocate，WRITE）：network + 指定
 *   AUTO 池（附容量最小展示，显示归 F013）；
 * - 编辑（PATCH，WRITE）：绑定/解绑/转移（同集群资源→接口两级选择）与描述；
 *   409 unique_conflict{field:"address"} → address 字段级错误；
 *   409 allocation_not_allowed（network_inactive/auto_allocate_disabled/
 *   pool_not_auto）与 no_available_address 按条件呈现；
 *   409 reference_exists（Endpoint 引用）→ 引用列表；
 *   409 VERSION_CONFLICT → 刷新后重改，不静默重试；
 * - 释放（DELETE，RELEASE_IP）：软删不级联，被未删 Endpoint 引用拒绝；
 *   恢复（RESTORE）：409 not_deleted / unique_conflict / dependency_deleted
 *   （所属网络 / 绑定接口仍删）/ 422（cidr 变更后越界 field="address"）明确呈现；
 * - Activity（VIEW_ACTIVITY 全角色）：created_at 升序只读流水，无修改/删除入口。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用与参数 / 手动与自动
 * 分配、绑定/解绑/转移、释放/恢复、过滤排序分页与软删语义 / 四态 / 权限门控 /
 * 二次确认与冲突呈现 / 文案均保持不变）。排序仍由表头按钮切换，不用 AntD 内置
 * sorter；行内二次确认沿用迁移前交互（失败后确认区保持待确认状态，错误在上方
 * Alert 呈现）。
 */
export default function IpAddressesPage({ user, initialNetworkId }: IpAddressesPageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canRelease = user.permissions.includes("RELEASE_IP");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const [options, setOptions] = useState<FilterOptionsState>({ kind: "loading" });
  const [optionsReloadToken, setOptionsReloadToken] = useState(0);
  // F013 入口可携带初始 network 过滤（仅初始化一次；合法性与存在性由服务端校验）
  const [query, setQuery] = useState<AppliedQuery>(() => ({
    ...DEFAULT_QUERY,
    networkId: initialNetworkId ?? DEFAULT_QUERY.networkId,
  }));
  // 筛选表单草稿：点击“筛选”才应用（避免每次击键发请求）；与 query 同源初始化
  const [draft, setDraft] = useState(() => ({
    q: DEFAULT_QUERY.q,
    networkId: initialNetworkId ?? DEFAULT_QUERY.networkId,
    clusterId: DEFAULT_QUERY.clusterId,
    poolId: DEFAULT_QUERY.poolId,
    interfaceId: DEFAULT_QUERY.interfaceId,
    bound: DEFAULT_QUERY.bound,
    address: DEFAULT_QUERY.address,
  }));
  const [filterError, setFilterError] = useState<string | null>(null);
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<IpAddressActionError | null>(null);
  const [action, setAction] = useState<
    { kind: "release" | "restore"; ipAddress: IpAddress } | null
  >(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<IpAddressActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  /** 最近一次分配结果提示（自动分配地址由服务端选定，需明确告知用户）。 */
  const [notice, setNotice] = useState<string | null>(null);

  // Activity 视图状态
  const [activityState, setActivityState] = useState<ActivityState>({ kind: "loading" });
  const [activityPage, setActivityPage] = useState(1);
  const [activityReloadToken, setActivityReloadToken] = useState(0);

  // 过滤下拉数据（网络 / 集群 / 地址池，仅未删除）
  useEffect(() => {
    let cancelled = false;
    setOptions({ kind: "loading" });
    Promise.all([
      listNetworks({ page: 1, page_size: 100, sort: "name", order: "asc" }),
      listClusters({ page: 1, page_size: 100, sort: "code", order: "asc" }),
      listIpPools({ page: 1, page_size: 100, sort: "name", order: "asc" }),
    ])
      .then(([networks, clusters, pools]) => {
        if (!cancelled) {
          setOptions({ kind: "success", networks: networks.items, clusters: clusters.items, pools: pools.items });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setOptions({
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
  }, [optionsReloadToken]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listIpAddresses({
      network_id: query.networkId || undefined,
      cluster_id: query.clusterId || undefined,
      interface_id: query.interfaceId || undefined,
      ip_pool_id: query.poolId || undefined,
      address: query.address || undefined,
      bound: query.bound === "" ? undefined : query.bound === "true",
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

  // Activity 加载（已删对象需 deleted=true + VIEW_DELETED，服务端仍鉴权）
  useEffect(() => {
    if (mode.kind !== "activity") {
      return;
    }
    let cancelled = false;
    setActivityState({ kind: "loading" });
    getIpAddressActivity(mode.ipAddress.id, {
      deleted: mode.ipAddress.deleted_at !== null,
      page: activityPage,
      page_size: 20,
    })
      .then((data) => {
        if (!cancelled) {
          setActivityState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setActivityState({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [mode, activityPage, activityReloadToken]);

  // ---- 手动 / 自动分配（POST，Contract §6.2/§6.3）----

  function handleCreateSubmit(values: IpAddressFormValues) {
    if (mode.kind !== "create-manual" && mode.kind !== "create-auto") {
      return;
    }
    const formMode = mode.kind === "create-manual" ? "manual" : "auto";
    if (values.network === "" || (formMode === "auto" && values.ip_pool === "")) {
      return; // 表单本地校验已拦截；防御双保险（不发起请求）
    }
    const networkCidr =
      options.kind === "success"
        ? options.networks.find((item) => item.id === values.network)?.cidr ?? null
        : null;
    const parsed = parseIpAddressFormValues(values, formMode, networkCidr);
    if (!parsed.ok) {
      return; // 同上
    }
    setSubmitting(true);
    setFormError(null);
    const request =
      formMode === "manual"
        ? createIpAddress(buildManualAllocateInput(values.network, parsed.fields))
        : autoAllocateIpAddress(
            buildAutoAllocateInput(values.network, values.ip_pool, parsed.fields),
          );
    request
      .then(({ ip_address: created }) => {
        // 201：分配成功（version=1、interface=null；自动分配地址由服务端选定）
        setNotice(
          formMode === "manual"
            ? `已登记 IP 地址 ${created.address}（网络 ${created.network.name}）`
            : `自动分配成功：${created.address}（网络 ${created.network.name}，来源池 ${
                created.ip_pool?.name ?? "未知"
              }）`,
        );
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 unique_conflict / allocation_not_allowed / no_available_address /
        // 422 / 403 明确呈现
        setFormError(describeIpAddressActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑：绑定/解绑/转移/描述（PATCH，Contract §6.5）----

  function handleEditSubmit(values: IpAddressFormValues) {
    if (mode.kind !== "edit") {
      return;
    }
    const parsed = parseIpAddressFormValues(values, "edit");
    if (!parsed.ok) {
      return;
    }
    const payload = buildIpAddressPatch(mode.ipAddress, parsed.fields);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改绑定接口或描述后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
        dependencyConflicts: [],
        allocationCondition: null,
        noAvailable: null,
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateIpAddress(mode.ipAddress.id, payload)
      .then(() => {
        // 200：version+1；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / reference_exists（Endpoint 引用）/
        // 422（interface 跨集群等）/ 403：明确呈现，不静默重试
        setFormError(describeIpAddressActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该 IP 并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.ipAddress.id;
    setFormError(null);
    setSubmitting(true);
    getIpAddress(id)
      .then(({ ip_address: fresh }) => {
        setMode({ kind: "edit", ipAddress: fresh });
        setFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setFormError(describeIpAddressActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 释放（软删，Contract §6.6）----

  function requestRelease(ipAddress: IpAddress) {
    setActionError(null);
    setAction({ kind: "release", ipAddress });
  }

  function confirmRelease() {
    if (action === null) {
      return;
    }
    const ipAddress = action.ipAddress;
    setActionBusy(true);
    setActionError(null);
    releaseIpAddress(ipAddress.id, ipAddress.version)
      .then(() => {
        // 204：软删成功（不级联、不自动解绑其它对象）；重载列表
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / reference_exists（Endpoint 引用）明确呈现
        setActionError(describeIpAddressActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.7）----

  function requestRestore(ipAddress: IpAddress) {
    setActionError(null);
    setAction({ kind: "restore", ipAddress });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const ipAddress = action.ipAddress;
    setActionBusy(true);
    setActionError(null);
    restoreIpAddress(ipAddress.id, ipAddress.version)
      .then(() => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        // / 422（cidr 变更后越界）明确呈现
        setActionError(describeIpAddressActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  /** 点击“筛选”才应用草稿（提交时机由 AntD Form onFinish 接管）。 */
  function applyFilters() {
    // 本地格式校验（快速反馈；避免把必然 422 的查询发给服务端）
    const interfaceId = draft.interfaceId.trim();
    const address = draft.address.trim();
    const errors: string[] = [];
    if (interfaceId !== "" && !UUID_PATTERN.test(interfaceId)) {
      errors.push("interface 过滤必须为合法 UUID（精确匹配，可从接口详情复制）");
    }
    if (address !== "" && !isValidBareIpv4(address)) {
      errors.push("address 过滤必须为合法裸 IPv4 主机地址（精确匹配，如 10.0.0.5）");
    }
    if (errors.length > 0) {
      setFilterError(errors.join("；"));
      return;
    }
    setFilterError(null);
    setNotice(null);
    setQuery((current) => ({
      ...current,
      q: draft.q,
      networkId: draft.networkId,
      clusterId: draft.clusterId,
      poolId: draft.poolId,
      interfaceId,
      bound: draft.bound,
      address,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({
      q: "",
      networkId: "",
      clusterId: "",
      poolId: "",
      interfaceId: "",
      bound: "",
      address: "",
    });
    setFilterError(null);
    setQuery((current) => ({
      ...current,
      q: "",
      networkId: "",
      clusterId: "",
      poolId: "",
      interfaceId: "",
      bound: "",
      address: "",
      page: 1,
    }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: IpAddressSortField) {
    setQuery((current) => ({
      ...current,
      sort: field,
      order: current.sort === field && current.order === "asc" ? "desc" : "asc",
      page: 1,
    }));
  }

  /** 排序表头按钮（当前排序字段附 ▲/▼ 指示；不用 AntD 内置 sorter）。 */
  function renderSortHeader(field: IpAddressSortField, label: string) {
    return (
      <Button
        type="link"
        size="small"
        className="px-0 font-semibold"
        onClick={() => toggleSort(field)}
      >
        {label}
        {query.sort === field ? (query.order === "asc" ? " ▲" : " ▼") : ""}
      </Button>
    );
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

  const networks = options.kind === "success" ? options.networks : [];
  const clusters = options.kind === "success" ? options.clusters : [];
  const pools = options.kind === "success" ? options.pools : [];
  const showDeletedColumn = query.deleted !== "exclude";

  /** 仅开启软删可见性（include / only）时追加 deleted_at 列（与原实现口径一致）。 */
  const deletedAtColumn: NonNullable<TableProps<IpAddress>["columns"]>[number] = {
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
  const columns: TableProps<IpAddress>["columns"] = [
    {
      title: renderSortHeader("address", "address"),
      key: "address",
      render: (_, ipAddress) => (
        <span>
          <span className="font-mono">{ipAddress.address}</span>
          {ipAddress.deleted_at !== null && (
            <Tag color="red" className="ml-2">
              已删除
            </Tag>
          )}
        </span>
      ),
    },
    {
      title: "network",
      key: "network",
      render: (_, ipAddress) => (
        <span>
          <span className="font-mono">{ipAddress.network.name}</span>
          <span className="text-gray-400">（{ipAddress.network.cidr}）</span>
        </span>
      ),
    },
    {
      title: "cluster",
      key: "cluster",
      render: (_, ipAddress) => <span className="font-mono">{ipAddress.cluster.code}</span>,
    },
    {
      title: "interface",
      key: "interface",
      render: (_, ipAddress) =>
        ipAddress.interface !== null ? (
          <span>
            {ipAddress.interface.name}
            <span className="text-gray-400">（{ipAddress.interface.resource.hostname}）</span>
          </span>
        ) : (
          <span className="text-gray-400">未绑定</span>
        ),
    },
    {
      title: "ip_pool（来源）",
      key: "ip_pool",
      render: (_, ipAddress) =>
        ipAddress.ip_pool !== null ? (
          ipAddress.ip_pool.name
        ) : (
          <span className="text-gray-400">池外（手动）</span>
        ),
    },
    {
      title: "description",
      dataIndex: "description",
      key: "description",
      render: (value: string | null) => (value ?? <span className="text-gray-400">—</span>),
    },
    {
      title: renderSortHeader("created_at", "创建时间"),
      key: "created_at",
      render: (_, ipAddress) => <span className="font-mono">{ipAddress.created_at}</span>,
    },
    {
      title: renderSortHeader("updated_at", "更新时间"),
      key: "updated_at",
      render: (_, ipAddress) => <span className="font-mono">{ipAddress.updated_at}</span>,
    },
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeletedColumn ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_, ipAddress) => (
        <>
          <Button
            type="link"
            size="small"
            className="px-0"
            onClick={() => {
              setActivityPage(1);
              setMode({ kind: "activity", ipAddress });
            }}
          >
            Activity
          </Button>
          {canWrite && ipAddress.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => {
                setFormError(null);
                setMode({ kind: "edit", ipAddress });
                setFormKey((key) => key + 1);
              }}
            >
              编辑
            </Button>
          )}
          {canRelease && ipAddress.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRelease(ipAddress)}
            >
              释放
            </Button>
          )}
          {canRestore && ipAddress.deleted_at !== null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRestore(ipAddress)}
            >
              恢复
            </Button>
          )}
        </>
      ),
    },
  ];

  /** Activity 列定义（只读流水；created_at 升序由服务端保证）。 */
  const activityColumns: TableProps<IpAddressActivityItem>["columns"] = [
    {
      title: "created_at",
      dataIndex: "created_at",
      key: "created_at",
      render: (value: string) => <span className="font-mono">{value}</span>,
    },
    {
      title: "action",
      dataIndex: "action",
      key: "action",
      render: (value: IpAddressActivityItem["action"]) => (
        <span className="font-mono">{value}</span>
      ),
    },
    { title: "操作者", dataIndex: "operator_username", key: "operator_username" },
    {
      title: "变更前",
      dataIndex: "before_data",
      key: "before_data",
      render: (value: Record<string, unknown> | null) => (
        <span className="font-mono">{formatAuditData(value)}</span>
      ),
    },
    {
      title: "变更后",
      dataIndex: "after_data",
      key: "after_data",
      render: (value: Record<string, unknown> | null) => (
        <span className="font-mono">{formatAuditData(value)}</span>
      ),
    },
  ];

  return (
    <Card
      title="IP Addresses（IP 地址）"
      extra={
        canWrite && mode.kind === "list" ? (
          <div className="flex gap-2">
            <Button
              onClick={() => {
                setFormError(null);
                setNotice(null);
                setMode({ kind: "create-manual" });
              }}
            >
              手动分配 IP
            </Button>
            <Button
              onClick={() => {
                setFormError(null);
                setNotice(null);
                setMode({ kind: "create-auto" });
              }}
            >
              自动分配 IP
            </Button>
          </div>
        ) : undefined
      }
    >
      {mode.kind === "list" && (
        <>
          {options.kind === "error" && (
            <Alert
              className="mb-4"
              type="error"
              showIcon
              message={`加载过滤选项失败：${options.message}`}
              action={
                <Button
                  size="small"
                  danger
                  onClick={() => setOptionsReloadToken((token) => token + 1)}
                >
                  重试
                </Button>
              }
            />
          )}

          {notice && (
            <Alert className="mb-4" type="success" showIcon message={notice} />
          )}

          <Form
            onFinish={applyFilters}
            className="flex flex-wrap items-end gap-x-4 gap-y-3 border-b border-gray-100 pb-4"
          >
            <div className="flex w-56 flex-col gap-1">
              <label htmlFor="ip-address-filter-q" className="text-sm text-gray-700">
                模糊搜索（address 子串，大小写不敏感）
              </label>
              <Input
                id="ip-address-filter-q"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="flex w-56 flex-col gap-1">
              <label htmlFor="ip-address-filter-address" className="text-sm text-gray-700">
                address（精确匹配）
              </label>
              <Input
                id="ip-address-filter-address"
                value={draft.address}
                onChange={(event) => setDraft({ ...draft, address: event.target.value })}
                placeholder="如 10.0.0.5（精确匹配）"
              />
            </div>
            <div className="flex w-60 flex-col gap-1">
              <label htmlFor="ip-address-filter-network" className="text-sm text-gray-700">
                所属网络
              </label>
              <Select<string>
                id="ip-address-filter-network"
                className="w-full"
                value={draft.networkId}
                onChange={(value) => setDraft({ ...draft, networkId: value })}
                disabled={options.kind !== "success"}
                options={[
                  { value: "", label: "全部（默认）" },
                  ...networks.map((network) => ({
                    value: network.id,
                    label: `${network.name}（${network.cidr}）`,
                  })),
                ]}
              />
            </div>
            <div className="flex w-60 flex-col gap-1">
              <label htmlFor="ip-address-filter-cluster" className="text-sm text-gray-700">
                集群（地址唯一作用域）
              </label>
              <Select<string>
                id="ip-address-filter-cluster"
                className="w-full"
                value={draft.clusterId}
                onChange={(value) => setDraft({ ...draft, clusterId: value })}
                disabled={options.kind !== "success"}
                options={[
                  { value: "", label: "全部（默认）" },
                  ...clusters.map((cluster) => ({
                    value: cluster.id,
                    label: `${cluster.code}（${cluster.name}）`,
                  })),
                ]}
              />
            </div>
            <div className="flex w-64 flex-col gap-1">
              <label htmlFor="ip-address-filter-pool" className="text-sm text-gray-700">
                分配来源地址池
              </label>
              <Select<string>
                id="ip-address-filter-pool"
                className="w-full"
                value={draft.poolId}
                onChange={(value) => setDraft({ ...draft, poolId: value })}
                disabled={options.kind !== "success"}
                options={[
                  { value: "", label: "全部（默认）" },
                  ...pools.map((pool) => ({
                    value: pool.id,
                    label: `${pool.name} · ${pool.network.name}`,
                  })),
                ]}
              />
            </div>
            <div className="flex w-72 flex-col gap-1">
              <label htmlFor="ip-address-filter-interface" className="text-sm text-gray-700">
                interface UUID（精确匹配）
              </label>
              <Input
                id="ip-address-filter-interface"
                value={draft.interfaceId}
                onChange={(event) => setDraft({ ...draft, interfaceId: event.target.value })}
                placeholder="接口 UUID，如 0b9f4c6b-…（精确匹配）"
              />
            </div>
            <div className="flex w-52 flex-col gap-1">
              <label htmlFor="ip-address-filter-bound" className="text-sm text-gray-700">
                绑定状态
              </label>
              <Select<"" | "true" | "false">
                id="ip-address-filter-bound"
                className="w-full"
                value={draft.bound}
                onChange={(value) => setDraft({ ...draft, bound: value })}
                options={[
                  { value: "", label: "全部（默认）" },
                  { value: "true", label: "已绑定（interface 非空）" },
                  { value: "false", label: "未绑定" },
                ]}
              />
            </div>
            <div className="flex gap-2">
              <Button type="primary" htmlType="submit">
                筛选
              </Button>
              <Button onClick={resetFilters}>重置</Button>
            </div>
          </Form>

          {filterError && (
            <Alert className="mt-4" type="error" showIcon message={filterError} />
          )}

          {canViewDeleted && (
            <div className="mt-4 flex w-56 flex-col gap-1">
              <label htmlFor="ip-address-deleted-mode" className="text-sm text-gray-700">
                软删可见性（需 VIEW_DELETED 权限）
              </label>
              <Select<DeletedMode>
                id="ip-address-deleted-mode"
                value={query.deleted}
                onChange={(value) => changeDeleted(value)}
                options={DELETED_MODE_OPTIONS}
              />
            </div>
          )}

          {state.kind === "loading" && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
              <Spin />
              <span>正在加载 IP 地址列表…</span>
            </div>
          )}

          {state.kind === "error" && (
            <Alert
              className="mt-4"
              type="error"
              showIcon
              message={`加载 IP 地址列表失败：${state.message}`}
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
                description="没有符合条件的 IP 地址（当前过滤 / 分页下无数据，非错误）。"
              />
            ) : (
              <>
                <Table<IpAddress>
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
                      {Object.keys(actionError.fields).length > 0 && (
                        <ul className="list-disc pl-5">
                          {Object.entries(actionError.fields).map(([field, message]) => (
                            <li key={field}>
                              {field}：{message}
                            </li>
                          ))}
                        </ul>
                      )}
                      {actionError.references.length > 0 && (
                        <ul className="list-disc pl-5">
                          {actionError.references.map((item) => (
                            <li key={`${item.object_type}-${item.object_id}`}>
                              引用对象：{item.label ?? item.object_id}（{item.object_type}）
                            </li>
                          ))}
                        </ul>
                      )}
                      {actionError.dependencyConflicts.length > 0 && (
                        <ul className="list-disc pl-5">
                          {actionError.dependencyConflicts.map((conflict) => (
                            <li key={`${conflict.object_type}-${conflict.object_id}`}>
                              {dependencyConflictText(conflict.object_type, conflict.object_id)}
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
                    {action.kind === "release" ? (
                      <span>
                        确认释放 IP 地址 {action.ipAddress.address}？（软删除释放，不级联；被未删除
                        Endpoint 引用时将被拒绝；不自动解绑其它对象；同集群内该地址软删后可复用）
                      </span>
                    ) : (
                      <span>
                        确认恢复 IP 地址 {action.ipAddress.address}？（仅恢复自身，不级联；将重检同集群
                        地址唯一、所属网络与绑定接口有效性、地址仍属网络 CIDR，失败不覆盖新对象；
                        version 递增）
                      </span>
                    )}
                  </span>
                  <Button
                    type="primary"
                    danger={action.kind === "release"}
                    onClick={action.kind === "release" ? confirmRelease : confirmRestore}
                    disabled={actionBusy}
                  >
                    {actionBusy
                      ? action.kind === "release"
                        ? "正在释放…"
                        : "正在恢复…"
                      : action.kind === "release"
                        ? "确认释放"
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

      {(mode.kind === "create-manual" || mode.kind === "create-auto") && (
        <IpAddressForm
          mode={mode.kind === "create-manual" ? "manual" : "auto"}
          networks={networks}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleCreateSubmit}
          onCancel={() => setMode({ kind: "list" })}
        />
      )}

      {mode.kind === "edit" && (
        <IpAddressForm
          key={formKey}
          mode="edit"
          networks={networks}
          ipAddress={mode.ipAddress}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleEditSubmit}
          onCancel={() => setMode({ kind: "list" })}
          onRefresh={refreshAfterConflict}
        />
      )}

      {mode.kind === "activity" && (
        <div>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="m-0 text-base font-semibold">
              Activity — <span className="font-mono">{mode.ipAddress.address}</span>
              <span className="text-gray-400">（{mode.ipAddress.network.name}）</span>
            </h3>
            <Button onClick={() => setMode({ kind: "list" })}>返回列表</Button>
          </div>
          <p className="mb-4 text-sm text-gray-500">
            操作流水（created_at 升序、同刻 id 升序；只读，无修改 / 删除入口；已删对象需
            VIEW_DELETED 才可查看）
          </p>
          {activityState.kind === "loading" && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
              <Spin />
              <span>正在加载 Activity…</span>
            </div>
          )}
          {activityState.kind === "error" && (
            <Alert
              type="error"
              showIcon
              message={`加载 Activity 失败：${activityState.message}`}
              action={
                <Button
                  size="small"
                  danger
                  onClick={() => setActivityReloadToken((token) => token + 1)}
                >
                  重试
                </Button>
              }
            />
          )}
          {activityState.kind === "success" &&
            (activityState.data.items.length === 0 ? (
              <Empty className="py-8" description="该 IP 地址暂无操作流水。" />
            ) : (
              <>
                <Table<IpAddressActivityItem>
                  rowKey="id"
                  size="middle"
                  pagination={false}
                  scroll={{ x: "max-content" }}
                  dataSource={activityState.data.items}
                  columns={activityColumns}
                />
                <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span>
                    共 {activityState.data.total} 条 · 第 {activityState.data.page} /
                    {Math.max(
                      1,
                      Math.ceil(activityState.data.total / activityState.data.page_size),
                    )}{" "}
                    页
                  </span>
                  <Button
                    disabled={activityState.data.page <= 1}
                    onClick={() => setActivityPage(activityState.data.page - 1)}
                  >
                    上一页
                  </Button>
                  <Button
                    disabled={
                      activityState.data.page >=
                      Math.max(
                        1,
                        Math.ceil(activityState.data.total / activityState.data.page_size),
                      )
                    }
                    onClick={() => setActivityPage(activityState.data.page + 1)}
                  >
                    下一页
                  </Button>
                </div>
              </>
            ))}
        </div>
      )}
    </Card>
  );
}

/** dependency_deleted 冲突条目文案（object_type 区分所属网络 / 绑定接口）。 */
function dependencyConflictText(objectType: string, objectId: string): string {
  if (objectType === "network") {
    return `所属网络仍处于已删除状态或已不存在（${objectId}）`;
  }
  if (objectType === "interface") {
    return `绑定的接口仍处于已删除状态或已不存在（${objectId}）`;
  }
  return `${objectType} 仍处于已删除状态或已不存在（${objectId}）`;
}

/** 审计快照白名单字段的紧凑呈现（Contract §8；null / 缺失 → “—”）。 */
function formatAuditData(data: Record<string, unknown> | null): string {
  if (data === null || Object.keys(data).length === 0) {
    return "—";
  }
  return Object.entries(data)
    .map(([key, value]) => `${key}=${value === null ? "null" : String(value)}`)
    .join("，");
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
