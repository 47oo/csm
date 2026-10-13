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
import { listResources, type Resource } from "../api/resources";
import {
  createService,
  deleteService,
  describeServiceActionError,
  getService,
  getServiceActivity,
  listServices,
  restoreService,
  updateService,
  type DeletedMode,
  type Service,
  type ServiceActionError,
  type ServiceActivityItem,
  type ServiceActivityResponse,
  type ServiceListResponse,
  type ServiceSortField,
  type ServiceStatus,
  type SortOrder,
} from "../api/services";
import ServiceForm from "../components/ServiceForm";
import ServiceEndpointsPanel from "../components/ServiceEndpointsPanel";
import { parseMetadataText } from "../components/ClusterForm";
import {
  buildServiceCreateInput,
  buildServicePatch,
  parseServiceFormValues,
  type ServiceFormValues,
} from "../components/serviceForm";

interface ServicesPageProps {
  user: User;
}

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: ServiceListResponse }
  | { kind: "error"; message: string };

/** 资源下拉数据加载状态（仅未删除资源；分页上限 100，Contract §4）。 */
type ResourceOptionsState =
  | { kind: "loading" }
  | { kind: "success"; resources: Resource[]; total: number }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单 / 编辑表单 / Activity / Endpoints 管理区。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "edit"; service: Service }
  | { kind: "activity"; service: Service }
  | { kind: "endpoints"; service: Service };

/** Activity 加载状态（分页）。 */
type ActivityState =
  | { kind: "loading" }
  | { kind: "success"; data: ServiceActivityResponse }
  | { kind: "error"; message: string };

/** 已应用的查询（排序 / 分页 / 过滤 / 软删可见性，Contract §4/§5）。 */
interface AppliedQuery {
  q: string;
  resourceId: string;
  status: "" | ServiceStatus;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
  sort: ServiceSortField;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  resourceId: "",
  status: "",
  deleted: "exclude",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

const SORT_COLUMNS: { field: ServiceSortField; label: string }[] = [
  { field: "name", label: "name" },
  { field: "status", label: "status" },
  { field: "created_at", label: "创建时间" },
  { field: "updated_at", label: "更新时间" },
];

/** 服务状态徽标配色（沿用旧版 badge-active / badge-inactive / badge-unknown 的绿/灰/灰）。 */
const STATUS_TAG_COLOR: Record<ServiceStatus, string> = {
  RUNNING: "success",
  STOPPED: "default",
  UNKNOWN: "default",
};

/** 排序列单元格渲染（name 附“已删除”标记；status 徽标化；时间等宽字体）。 */
const SORT_CELL_RENDER: { [F in ServiceSortField]: (service: Service) => ReactNode } = {
  name: (service) => (
    <span>
      {service.name}
      {service.deleted_at !== null && (
        <Tag color="red" className="ml-2">
          已删除
        </Tag>
      )}
    </span>
  ),
  status: (service) => <Tag color={STATUS_TAG_COLOR[service.status]}>{service.status}</Tag>,
  created_at: (service) => <span className="font-mono">{service.created_at}</span>,
  updated_at: (service) => <span className="font-mono">{service.updated_at}</span>,
};

/** 状态过滤下拉选项（“全部（默认）” + 三种状态；文案与迁移前一致）。 */
const STATUS_FILTER_OPTIONS: { value: "" | ServiceStatus; label: string }[] = [
  { value: "", label: "全部（默认）" },
  { value: "RUNNING", label: "RUNNING（运行中）" },
  { value: "STOPPED", label: "STOPPED（已停止）" },
  { value: "UNKNOWN", label: "UNKNOWN（状态未知）" },
];

/** 软删可见性选项（exclude 默认 | include | only；后两者需 VIEW_DELETED）。 */
const DELETED_MODE_OPTIONS: { value: DeletedMode; label: string }[] = [
  { value: "exclude", label: "未删除（默认）" },
  { value: "include", label: "全部（含已删除）" },
  { value: "only", label: "仅已删除" },
];

/** 表单原始值 → 解析 + metadata 解析（复用 ClusterForm.parseMetadataText）。 */
function parseSubmission(values: ServiceFormValues) {
  const parsed = parseServiceFormValues(values);
  if (!parsed.ok) {
    return null;
  }
  const metadata = parseMetadataText(values.metadata);
  if (!metadata.ok) {
    return null; // 表单本地校验已拦截；防御双保险（不发起请求）
  }
  return { fields: parsed.fields, metadata: metadata.value };
}

/**
 * F011 Services 服务登记页（Contract §4/§5/§6，§28 列表基线）：
 * - 列表：GET /api/v1/services（分页 page/page_size 1–100、排序白名单
 *   name/status/created_at/updated_at、过滤 resource_id/status/q AND 组合，
 *   软删可见性开关仅对具 VIEW_DELETED 的角色显示，服务端仍鉴权）；
 *   Loading / Empty / Error 显式区分，错误绝不伪装成空列表；
 * - 创建 / 编辑（WRITE）：ServiceForm（Resource 选择器（创建后不可改，DR-144）/
 *   name / status / description / metadata）；提交带 version（编辑）；
 *   409 unique_conflict{field:"name"} → name 字段级错误；
 *   409 VERSION_CONFLICT → 刷新后重改，不静默重试；
 * - 删除（DELETE_OBJECT，软删不级联）：被未删 ServiceEndpoint 引用 → 409
 *   reference_exists 展示引用列表（F011 默认空集，F012 起真实，DR-146）；
 * - 恢复（RESTORE）：409 not_deleted / unique_conflict / dependency_deleted
 *   （所属 Resource 仍删 / 缺失，DR-148）明确呈现；
 * - Activity（VIEW_ACTIVITY 全角色）：created_at 升序只读流水，无修改/删除入口；
 * - Endpoints 管理区（F012，DR-170）：Service Detail 的监听端点列表 / 新建 /
 *   编辑 / 删除 / 恢复 / Activity（ServiceEndpointsPanel，按 service_id 过滤）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 组合过滤与排序分页
 * 参数 / 四态 / 权限门控 / 软删开关 / 增删改恢复与二次确认 / Activity /
 * Endpoints 入口 / 全部文案保持不变）。
 */
export default function ServicesPage({ user }: ServicesPageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const [resourceOptions, setResourceOptions] = useState<ResourceOptionsState>({ kind: "loading" });
  const [resourceReloadToken, setResourceReloadToken] = useState(0);
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  // 筛选表单草稿：点击“筛选”才应用（避免每次击键发请求）
  const [draft, setDraft] = useState({
    q: DEFAULT_QUERY.q,
    resourceId: DEFAULT_QUERY.resourceId,
    status: DEFAULT_QUERY.status,
  });
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<ServiceActionError | null>(null);
  const [action, setAction] = useState<{ kind: "delete" | "restore"; service: Service } | null>(
    null,
  ); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<ServiceActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Activity 视图状态
  const [activityState, setActivityState] = useState<ActivityState>({ kind: "loading" });
  const [activityPage, setActivityPage] = useState(1);
  const [activityReloadToken, setActivityReloadToken] = useState(0);

  // 资源下拉（表单 resource 选择器 + 过滤），仅未删除资源
  useEffect(() => {
    let cancelled = false;
    setResourceOptions({ kind: "loading" });
    listResources({ page: 1, page_size: 100, sort: "hostname", order: "asc" })
      .then((data) => {
        if (!cancelled) {
          setResourceOptions({ kind: "success", resources: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setResourceOptions({
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
  }, [resourceReloadToken]);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listServices({
      resource_id: query.resourceId || undefined,
      status: query.status || undefined,
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
    getServiceActivity(mode.service.id, {
      deleted: mode.service.deleted_at !== null,
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

  // ---- 创建（POST，Contract §6.2）----

  function handleCreateSubmit(values: ServiceFormValues) {
    const parsed = parseSubmission(values);
    if (parsed === null) {
      return; // 表单本地校验已拦截；防御双保险（不发起请求）
    }
    if (values.resource === "") {
      return; // 同上：创建必须选择资源
    }
    setSubmitting(true);
    setFormError(null);
    createService(buildServiceCreateInput(values.resource, parsed.fields, parsed.metadata))
      .then(() => {
        // 201：创建成功（version=1）；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 unique_conflict / 422（body、resource、name、status、metadata）/ 403 明确呈现
        setFormError(describeServiceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: ServiceFormValues) {
    if (mode.kind !== "edit") {
      return;
    }
    const parsed = parseSubmission(values);
    if (parsed === null) {
      return;
    }
    const payload = buildServicePatch(mode.service, parsed.fields, parsed.metadata);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改至少一个字段后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
        dependencyConflicts: [],
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateService(mode.service.id, payload)
      .then(() => {
        // 200：version+1；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / unique_conflict / 422 / 403：明确呈现，不静默重试
        setFormError(describeServiceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该服务并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.service.id;
    setFormError(null);
    setSubmitting(true);
    getService(id)
      .then(({ service: fresh }) => {
        setMode({ kind: "edit", service: fresh });
        setFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setFormError(describeServiceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete(service: Service) {
    setActionError(null);
    setAction({ kind: "delete", service });
  }

  function confirmDelete() {
    if (action === null) {
      return;
    }
    const service = action.service;
    setActionBusy(true);
    setActionError(null);
    deleteService(service.id, service.version)
      .then(() => {
        // 204：软删成功（不级联；F011 引用检查默认空集，F012 起真实）；重载列表
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / reference_exists（ServiceEndpoint 引用）明确呈现
        setActionError(describeServiceActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore(service: Service) {
    setActionError(null);
    setAction({ kind: "restore", service });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const service = action.service;
    setActionBusy(true);
    setActionError(null);
    restoreService(service.id, service.version)
      .then(() => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        // 明确呈现
        setActionError(describeServiceActionError(error));
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
      resourceId: draft.resourceId,
      status: draft.status,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", resourceId: "", status: "" });
    setQuery((current) => ({
      ...current,
      q: "",
      resourceId: "",
      status: "",
      page: 1,
    }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: ServiceSortField) {
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

  const resources = resourceOptions.kind === "success" ? resourceOptions.resources : [];
  const showDeletedColumn = query.deleted !== "exclude";

  /** 资源过滤下拉选项（“全部（默认）” + 未删除资源，文案同迁移前）。 */
  const resourceFilterOptions = [
    { value: "", label: "全部（默认）" },
    ...resources.map((resource) => ({
      value: resource.id,
      label: `${resource.hostname}（${resource.cluster.code}）`,
    })),
  ];

  /** 仅开启软删可见性（include / only）时追加 deleted_at 列（与原实现口径一致）。 */
  const deletedAtColumn: NonNullable<TableProps<Service>["columns"]>[number] = {
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
  const columns: TableProps<Service>["columns"] = [
    {
      title: "resource",
      key: "resource",
      render: (_: unknown, service: Service) => (
        <span className="font-mono">{service.resource.hostname}</span>
      ),
    },
    ...SORT_COLUMNS.map(
      ({ field, label }): NonNullable<TableProps<Service>["columns"]>[number] => ({
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
        render: (_: unknown, service: Service) => SORT_CELL_RENDER[field](service),
      }),
    ),
    {
      title: "description",
      dataIndex: "description",
      key: "description",
      render: (value: string | null) => (value ?? <span className="text-gray-400">—</span>),
    },
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeletedColumn ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, service: Service) => (
        <>
          <Button
            type="link"
            size="small"
            className="px-0"
            onClick={() => {
              setActivityPage(1);
              setMode({ kind: "activity", service });
            }}
          >
            Activity
          </Button>
          <Button
            type="link"
            size="small"
            className="px-0"
            onClick={() => {
              setFormError(null);
              setMode({ kind: "endpoints", service });
            }}
          >
            Endpoints
          </Button>
          {canWrite && service.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => {
                setFormError(null);
                setMode({ kind: "edit", service });
                setFormKey((key) => key + 1);
              }}
            >
              编辑
            </Button>
          )}
          {canDelete && service.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestDelete(service)}
            >
              删除
            </Button>
          )}
          {canRestore && service.deleted_at !== null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRestore(service)}
            >
              恢复
            </Button>
          )}
        </>
      ),
    },
  ];

  /** Activity 列定义（只读流水；created_at 升序由服务端保证）。 */
  const activityColumns: TableProps<ServiceActivityItem>["columns"] = [
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
      render: (value: ServiceActivityItem["action"]) => (
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

  // 操作错误提示（AntD Alert 自带 role="alert"）：确认框开启期间渲染在 Modal 内，
  // 取消确认后保留在列表区展示（同迁移前的呈现位置与文案）
  const actionErrorAlert = actionError ? (
    <Alert
      type="error"
      message={actionError.message}
      description={
        Object.keys(actionError.fields).length > 0 ||
        actionError.references.length > 0 ||
        actionError.dependencyConflicts.length > 0 ||
        actionError.versionConflict ? (
          <>
            {Object.keys(actionError.fields).length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {Object.entries(actionError.fields).map(([field, message]) => (
                  <li key={field}>
                    {field}：{message}
                  </li>
                ))}
              </ul>
            )}
            {actionError.references.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.references.map((item) => (
                  <li key={`${item.object_type}-${item.object_id}`}>
                    引用端点：{item.label ?? item.object_id}（{item.object_type}）
                  </li>
                ))}
              </ul>
            )}
            {actionError.dependencyConflicts.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.dependencyConflicts.map((conflict) => (
                  <li key={`${conflict.object_type}-${conflict.object_id}`}>
                    所属资源（{conflict.object_id}）仍处于已删除状态或已不存在
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
        title="Services（服务登记）"
        extra={
          canWrite && mode.kind === "list" ? (
            <Button
              type="primary"
              onClick={() => {
                setFormError(null);
                setMode({ kind: "create" });
              }}
            >
              新建服务
            </Button>
          ) : undefined
        }
      >
        {mode.kind === "list" && (
          <>
            {resourceOptions.kind === "error" && (
              <Alert
                className="mb-4"
                type="error"
                showIcon
                message={`加载资源下拉失败：${resourceOptions.message}`}
                action={
                  <Button
                    size="small"
                    danger
                    onClick={() => setResourceReloadToken((token) => token + 1)}
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
                <label htmlFor="service-filter-q" className="text-sm text-gray-700">
                  模糊搜索（name 子串，大小写不敏感）
                </label>
                <Input
                  id="service-filter-q"
                  value={draft.q}
                  onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                  placeholder="大小写不敏感子串匹配"
                />
              </div>
              <div className="flex w-64 flex-col gap-1">
                <label htmlFor="service-filter-resource" className="text-sm text-gray-700">
                  所属资源
                </label>
                <Select<string>
                  id="service-filter-resource"
                  className="w-full"
                  value={draft.resourceId}
                  onChange={(value) => setDraft({ ...draft, resourceId: value })}
                  disabled={resourceOptions.kind !== "success"}
                  options={resourceFilterOptions}
                />
              </div>
              <div className="flex w-56 flex-col gap-1">
                <label htmlFor="service-filter-status" className="text-sm text-gray-700">
                  status
                </label>
                <Select<"" | ServiceStatus>
                  id="service-filter-status"
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
                <label htmlFor="service-deleted-mode" className="text-sm text-gray-700">
                  软删可见性（需 VIEW_DELETED 权限）
                </label>
                <Select<DeletedMode>
                  id="service-deleted-mode"
                  value={query.deleted}
                  onChange={(value) => changeDeleted(value)}
                  options={DELETED_MODE_OPTIONS}
                />
              </div>
            )}

            {state.kind === "loading" && (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
                <Spin />
                <span>正在加载服务列表…</span>
              </div>
            )}

            {state.kind === "error" && (
              <Alert
                className="mt-4"
                type="error"
                showIcon
                message={`加载服务列表失败：${state.message}`}
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
                  description="没有符合条件的服务（当前过滤 / 分页下无数据，非错误）。"
                />
              ) : (
                <>
                  <Table<Service>
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

            {action === null && actionErrorAlert && <div className="mt-4">{actionErrorAlert}</div>}
          </>
        )}

        {mode.kind === "create" && (
          <ServiceForm
            mode="create"
            resources={resources}
            submitting={submitting}
            serverError={formError}
            onSubmit={handleCreateSubmit}
            onCancel={() => setMode({ kind: "list" })}
          />
        )}

        {mode.kind === "edit" && (
          <ServiceForm
            key={formKey}
            mode="edit"
            resources={resources}
            service={mode.service}
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
                Activity — <span className="font-mono">{mode.service.name}</span>
                <span className="text-gray-400">（{mode.service.resource.hostname}）</span>
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
                <Empty className="py-8" description="该服务暂无操作流水。" />
              ) : (
                <>
                  <Table<ServiceActivityItem>
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
        {mode.kind === "endpoints" && (
          <ServiceEndpointsPanel
            service={mode.service}
            user={user}
            onBack={() => setMode({ kind: "list" })}
          />
        )}
      </Card>

      {/* 删除二次确认（软删，Contract §6.5）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action !== null && action.kind === "delete" && confirmVisible}
        title={
          action !== null && action.kind === "delete"
            ? `确认软删除服务 ${action.service.name}？（不级联删除关联对象；同资源内名称软删后可复用；若仍有未删除的服务端点（ServiceEndpoint）引用，将被拒绝并显示引用列表）`
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
            ? `确认恢复服务 ${action.service.name}？（仅恢复自身，不级联、不自动恢复服务端点；将重检同资源名称唯一性与所属资源有效性，失败不覆盖新对象；version 递增）`
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
