import { Button, Input, Select, DataTable } from "../components/ui/controls";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { EmptyState, ErrorState, InfoState, LoadingState, WarningState } from "../components/ui/feedback";
import { ServerPagination as Pagination, StatusTag, SurfaceCard, statusTone } from "../components/ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
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

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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

  return (
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>Services（服务登记）</h2>
        {canWrite && mode.kind === "list" && (
          <Button
            type="button"
            onClick={() => {
              setFormError(null);
              setMode({ kind: "create" });
            }}
          >
            新建服务
          </Button>
        )}
      </div>

      {mode.kind === "list" && (
        <>
          {resourceOptions.kind === "error" && (
            <ErrorState
              message={`加载资源下拉失败：${resourceOptions.message}`}
              action={
                <Button type="button" onClick={() => setResourceReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          <form className="filter-form" onSubmit={applyFilters}>
            <div className="form-field">
              <label htmlFor="service-filter-q">模糊搜索（name 子串，大小写不敏感）</label>
              <Input
                id="service-filter-q"
                type="text"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="form-field">
              <label htmlFor="service-filter-resource">所属资源</label>
              <Select
                id="service-filter-resource"
                value={draft.resourceId}
                onChange={(event) => setDraft({ ...draft, resourceId: event.target.value })}
                disabled={resourceOptions.kind !== "success"}
              >
                <option value="">全部（默认）</option>
                {resources.map((resource) => (
                  <option key={resource.id} value={resource.id}>
                    {resource.hostname}（{resource.cluster.code}）
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-field">
              <label htmlFor="service-filter-status">status</label>
              <Select
                id="service-filter-status"
                value={draft.status}
                onChange={(event) =>
                  setDraft({ ...draft, status: event.target.value as "" | ServiceStatus })
                }
              >
                <option value="">全部（默认）</option>
                <option value="RUNNING">RUNNING（运行中）</option>
                <option value="STOPPED">STOPPED（已停止）</option>
                <option value="UNKNOWN">UNKNOWN（状态未知）</option>
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
              <label htmlFor="service-deleted-mode">软删可见性（需 VIEW_DELETED 权限）</label>
              <Select
                id="service-deleted-mode"
                value={query.deleted}
                onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
              >
                <option value="exclude">未删除（默认）</option>
                <option value="include">全部（含已删除）</option>
                <option value="only">仅已删除</option>
              </Select>
            </div>
          )}

          {state.kind === "loading" && <LoadingState label="正在加载服务列表…" />}

          {state.kind === "error" && (
            <ErrorState
              message={`加载服务列表失败：${state.message}`}
              action={
                <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          {state.kind === "success" &&
            (state.data.items.length === 0 ? (
              <EmptyState description="没有符合条件的服务（当前过滤 / 分页下无数据，非错误）。" />
            ) : (
              <>
                <div className="table-wrap">
                  <DataTable className="data-table">
                    <thead>
                      <tr>
                        <th>resource</th>
                        {SORT_COLUMNS.map(({ field, label }) => (
                          <th key={field}>
                            <Button
                              type="button"
                              className="sort-button"
                              onClick={() => toggleSort(field)}
                            >
                              {label}
                              {query.sort === field ? (query.order === "asc" ? " ▲" : " ▼") : ""}
                            </Button>
                          </th>
                        ))}
                        <th>description</th>
                        <th>version</th>
                        {showDeletedColumn && <th>deleted_at</th>}
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.items.map((service) => (
                        <tr key={service.id}>
                          <td className="mono">{service.resource.hostname}</td>
                          <td>
                            {service.name}
                            {service.deleted_at !== null && (
                              <StatusTag tone="error">已删除</StatusTag>
                            )}
                          </td>
                          <td>
                            <StatusTag tone={statusTone(service.status)}>{service.status}</StatusTag>
                          </td>
                          <td className="mono">{service.created_at}</td>
                          <td className="mono">{service.updated_at}</td>
                          <td>{service.description ?? <span className="unset">—</span>}</td>
                          <td>{service.version}</td>
                          {showDeletedColumn && (
                            <td className="mono">
                              {service.deleted_at ?? <span className="unset">—</span>}
                            </td>
                          )}
                          <td>
                            <Button
                              type="button"
                              className="link-button"
                              onClick={() => {
                                setActivityPage(1);
                                setMode({ kind: "activity", service });
                              }}
                            >
                              Activity
                            </Button>
                            <Button
                              type="button"
                              className="link-button"
                              onClick={() => {
                                setFormError(null);
                                setMode({ kind: "endpoints", service });
                              }}
                            >
                              Endpoints
                            </Button>
                            {canWrite && service.deleted_at === null && (
                              <Button
                                type="button"
                                className="link-button"
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
                                type="button"
                                danger
                                className="link-button"
                                onClick={() => requestDelete(service)}
                              >
                                删除
                              </Button>
                            )}
                            {canRestore && service.deleted_at !== null && (
                              <Button
                                type="button"
                                className="link-button"
                                onClick={() => requestRestore(service)}
                              >
                                恢复
                              </Button>
                            )}
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

          {/* F020：删除 / 恢复二次确认模态（替代原内联确认；请求语义不变，错误块随正文呈现） */}
          <ConfirmDialog
            open={action !== null}
            title={action?.kind === "delete" ? "删除服务" : "恢复服务"}
            okText={action?.kind === "delete" ? "确认删除" : "确认恢复"}
            danger={action?.kind === "delete"}
            confirmLoading={actionBusy}
            onConfirm={action?.kind === "delete" ? confirmDelete : confirmRestore}
            onCancel={() => {
              setAction(null);
              setActionError(null);
            }}
          >
            {action !== null && (
              <div className="detail-actions">
                <WarningState
                  message={
                    action.kind === "delete" ? (
                      <span>
                        确认软删除服务 {action.service.name}？（不级联删除关联对象；同资源内名称
                        软删后可复用；若仍有未删除的服务端点（ServiceEndpoint）引用，将被拒绝
                        并显示引用列表）
                      </span>
                    ) : (
                      <span>
                        确认恢复服务 {action.service.name}？（仅恢复自身，不级联、不自动恢复
                        服务端点；将重检同资源名称唯一性与所属资源有效性，失败不覆盖新对象；
                        version 递增）
                      </span>
                    )
                  }
                />
                {actionError && (
                  <ErrorState message={<div className="form-error">
                    <p>{actionError.message}</p>
                    {Object.keys(actionError.fields).length > 0 && (
                      <ul>
                        {Object.entries(actionError.fields).map(([field, message]) => (
                          <li key={field}>
                            {field}：{message}
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.references.length > 0 && (
                      <ul>
                        {actionError.references.map((item) => (
                          <li key={`${item.object_type}-${item.object_id}`}>
                            引用端点：{item.label ?? item.object_id}（{item.object_type}）
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.dependencyConflicts.length > 0 && (
                      <ul>
                        {actionError.dependencyConflicts.map((conflict) => (
                          <li key={`${conflict.object_type}-${conflict.object_id}`}>
                            所属资源（{conflict.object_id}）仍处于已删除状态或已不存在
                          </li>
                        ))}
                      </ul>
                    )}
                    {actionError.versionConflict && (
                      <p>
                        <Button
                          type="button"
                          onClick={() => {
                            setActionError(null);
                            setAction(null);
                            setReloadToken((token) => token + 1);
                          }}
                          disabled={actionBusy}
                        >
                          刷新最新数据
                        </Button>
                      </p>
                    )}
                  </div>} />
                )}
              </div>
            )}
          </ConfirmDialog>
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
          <div className="table-toolbar">
            <h3>
              Activity — <span className="mono">{mode.service.name}</span>
              <span className="unset">（{mode.service.resource.hostname}）</span>
            </h3>
            <Button type="button" onClick={() => setMode({ kind: "list" })}>
              返回列表
            </Button>
          </div>
          <InfoState message="操作流水（created_at 升序、同刻 id 升序；只读，无修改 / 删除入口；已删对象需 VIEW_DELETED 才可查看）" />
          {activityState.kind === "loading" && (
            <LoadingState label="正在加载 Activity…" />
          )}
          {activityState.kind === "error" && (
            <ErrorState
              message={`加载 Activity 失败：${activityState.message}`}
              action={
                <Button type="button" onClick={() => setActivityReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}
          {activityState.kind === "success" &&
            (activityState.data.items.length === 0 ? (
              <EmptyState description="该服务暂无操作流水。" />
            ) : (
              <>
                <div className="table-wrap">
                  <DataTable className="data-table">
                    <thead>
                      <tr>
                        <th>created_at</th>
                        <th>action</th>
                        <th>操作者</th>
                        <th>变更前</th>
                        <th>变更后</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activityState.data.items.map((item) => (
                        <tr key={item.id}>
                          <td className="mono">{item.created_at}</td>
                          <td className="mono">{item.action}</td>
                          <td>{item.operator_username}</td>
                          <td className="mono">{formatAuditData(item.before_data)}</td>
                          <td className="mono">{formatAuditData(item.after_data)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </DataTable>
                </div>
                <div className="pagination">
                  <span>
                    共 {activityState.data.total} 条 · 第 {activityState.data.page} /
                    {Math.max(1, Math.ceil(activityState.data.total / activityState.data.page_size))} 页
                  </span>
                  <Button
                    type="button"
                    disabled={activityState.data.page <= 1}
                    onClick={() => setActivityPage(activityState.data.page - 1)}
                  >
                    上一页
                  </Button>
                  <Button
                    type="button"
                    disabled={
                      activityState.data.page >=
                      Math.max(1, Math.ceil(activityState.data.total / activityState.data.page_size))
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
    </SurfaceCard>
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
