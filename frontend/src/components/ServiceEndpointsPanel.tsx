import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Space,
  Spin,
  Table,
  Tag,
  type TableProps,
} from "antd";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import { listServices, type Service, type ServiceListResponse } from "../api/services";
import {
  createServiceEndpoint,
  deleteServiceEndpoint,
  describeServiceEndpointActionError,
  getServiceEndpoint,
  getServiceEndpointActivity,
  listServiceEndpoints,
  restoreServiceEndpoint,
  updateServiceEndpoint,
  type ServiceEndpoint,
  type ServiceEndpointActionError,
  type ServiceEndpointActivityResponse,
  type ServiceEndpointListResponse,
} from "../api/serviceEndpoints";
import ServiceEndpointForm from "./ServiceEndpointForm";
import {
  buildServiceEndpointCreateInput,
  buildServiceEndpointPatch,
  parseServiceEndpointFormValues,
  type ServiceEndpointFormValues,
} from "./serviceEndpointForm";

/** 端点列表加载状态（分页上限 100，Contract §4）。 */
type EndpointListState =
  | { kind: "loading" }
  | { kind: "success"; data: ServiceEndpointListResponse }
  | { kind: "error"; message: string };

/** 创建表单的 Service 候选加载状态（仅未删除服务，分页上限 100）。 */
type ServiceOptionsState =
  | { kind: "loading" }
  | { kind: "success"; services: Service[]; total: number }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单 / 编辑表单 / Activity。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "edit"; endpoint: ServiceEndpoint }
  | { kind: "activity"; endpoint: ServiceEndpoint };

/** Activity 加载状态（分页）。 */
type ActivityState =
  | { kind: "loading" }
  | { kind: "success"; data: ServiceEndpointActivityResponse }
  | { kind: "error"; message: string };

/** Table 行数据类型（取自 ServiceEndpointListResponse.items 元素）。 */
type EndpointItem = ServiceEndpointListResponse["items"][number];

/** Activity Table 行数据类型（取自 ServiceEndpointActivityResponse.items 元素）。 */
type ActivityItem = ServiceEndpointActivityResponse["items"][number];

interface ServiceEndpointsPanelProps {
  /** 所属 Service（Endpoints 管理区作用域；service 归属创建后不可改，DR-157）。 */
  service: Service;
  user: User;
  /** 返回服务列表（ServicesPage 交接）。 */
  onBack: () => void;
}

/**
 * Service Detail 的 Endpoints 管理区（F012，§16 / DR-170；Contract §4/§5/§6）：
 * - 列表：GET /api/v1/service-endpoints?service_id=<服务 id>（默认未删除；
 *   已删开关 → deleted=include，需 VIEW_DELETED，服务端仍 403 把关）；
 *   Loading / Empty / Error 显式区分，错误可重试、绝不伪装成空列表；
 * - 创建（WRITE）：ServiceEndpointForm（Service 选择器（面板服务预选，创建后
 *   不可改）/ IPAddress 选择器（同 Resource 已绑定未删 IP）/ protocol / port /
 *   description）；同 IP (protocol,port) 冲突 → 409 unique_conflict{field:"port"}；
 * - 编辑（WRITE）：protocol / port / description 可改（PATCH 仅变化字段）；
 *   409 VERSION_CONFLICT → 刷新后重改，不静默重试；
 * - 删除（DELETE_OBJECT，软删不级联；无子对象引用，删除前无引用检查）；
 * - 恢复（RESTORE）：409 not_deleted / unique_conflict / dependency_deleted
 *   （Service / IP / Interface 仍删）/ 422 field="ip_address"（归属不再成立）
 *   明确呈现；
 * - Activity（VIEW_ACTIVITY 全角色）：created_at 升序只读流水，无修改/删除入口；
 * - 所属服务已软删时隐藏新建 / 恢复入口（服务端确定性拒绝：创建 422
 *   field="service"、恢复 409 dependency_deleted）；列表 / 编辑 / 删除 / Activity
 *   照常提供（编辑 / 删除仅未删端点）。
 */
export default function ServiceEndpointsPanel({ service, user, onBack }: ServiceEndpointsPanelProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const serviceDeleted = service.deleted_at !== null;
  const [showDeleted, setShowDeleted] = useState(false);
  const [state, setState] = useState<EndpointListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [serviceOptions, setServiceOptions] = useState<ServiceOptionsState>({ kind: "loading" });
  const [serviceReloadToken, setServiceReloadToken] = useState(0);
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<ServiceEndpointActionError | null>(null);
  const [action, setAction] = useState<
    { kind: "delete" | "restore"; endpoint: ServiceEndpoint } | null
  >(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<ServiceEndpointActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Activity 视图状态
  const [activityState, setActivityState] = useState<ActivityState>({ kind: "loading" });
  const [activityPage, setActivityPage] = useState(1);
  const [activityReloadToken, setActivityReloadToken] = useState(0);

  // 端点列表（service_id 过滤；已删开关：include 需 VIEW_DELETED，服务端仍 403 把关）
  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listServiceEndpoints({
      service_id: service.id,
      deleted: showDeleted ? "include" : "exclude",
      page_size: 100,
      sort: "created_at",
      order: "desc",
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
  }, [service.id, showDeleted, reloadToken]);

  // 创建表单的 Service 候选（进入 create 模式时加载，仅未删除服务）
  useEffect(() => {
    if (mode.kind !== "create") {
      return;
    }
    let cancelled = false;
    setServiceOptions({ kind: "loading" });
    listServices({ deleted: "exclude", page_size: 100, sort: "name", order: "asc" })
      .then((data: ServiceListResponse) => {
        if (!cancelled) {
          setServiceOptions({ kind: "success", services: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setServiceOptions({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [mode.kind, serviceReloadToken]);

  // Activity 加载（已删对象需 deleted=true + VIEW_DELETED，服务端仍鉴权）
  useEffect(() => {
    if (mode.kind !== "activity") {
      return;
    }
    let cancelled = false;
    setActivityState({ kind: "loading" });
    getServiceEndpointActivity(mode.endpoint.id, {
      deleted: mode.endpoint.deleted_at !== null,
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

  function handleCreateSubmit(values: ServiceEndpointFormValues) {
    const parsed = parseServiceEndpointFormValues(values);
    if (!parsed.ok || values.service === "" || values.ipAddress === "") {
      return; // 表单本地校验已拦截；防御双保险（不发起请求）
    }
    setSubmitting(true);
    setFormError(null);
    createServiceEndpoint(
      buildServiceEndpointCreateInput(values.service, values.ipAddress, parsed.fields),
    )
      .then(() => {
        // 201：创建成功（version=1）；回列表并重载（列表按面板服务过滤）
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 422（body / service / ip_address / protocol / port）/ 409 unique_conflict
        // / 403 明确呈现
        setFormError(describeServiceEndpointActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: ServiceEndpointFormValues) {
    if (mode.kind !== "edit") {
      return;
    }
    const parsed = parseServiceEndpointFormValues(values);
    if (!parsed.ok) {
      return;
    }
    const payload = buildServiceEndpointPatch(mode.endpoint, parsed.fields);
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
    updateServiceEndpoint(mode.endpoint.id, payload)
      .then(() => {
        // 200：version+1；回列表并重载
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / unique_conflict / 422 / 403：明确呈现，不静默重试
        setFormError(describeServiceEndpointActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该端点并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.endpoint.id;
    setFormError(null);
    setSubmitting(true);
    getServiceEndpoint(id)
      .then(({ service_endpoint: fresh }) => {
        setMode({ kind: "edit", endpoint: fresh });
        setFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setFormError(describeServiceEndpointActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete(endpoint: ServiceEndpoint) {
    setActionError(null);
    setAction({ kind: "delete", endpoint });
  }

  function confirmDelete() {
    if (action === null) {
      return;
    }
    const endpoint = action.endpoint;
    setActionBusy(true);
    setActionError(null);
    deleteServiceEndpoint(endpoint.id, endpoint.version)
      .then(() => {
        // 204：软删成功（不级联；无子对象引用）；重载列表（已删开关开启时仍可见并带徽标）
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT 明确呈现（无引用检查，不产生 reference_exists）
        setActionError(describeServiceEndpointActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore(endpoint: ServiceEndpoint) {
    setActionError(null);
    setAction({ kind: "restore", endpoint });
  }

  function confirmRestore() {
    if (action === null) {
      return;
    }
    const endpoint = action.endpoint;
    setActionBusy(true);
    setActionError(null);
    restoreServiceEndpoint(endpoint.id, endpoint.version)
      .then(() => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted；
        // 422 field="ip_address"（IP 已解绑或归属不再成立）明确呈现
        setActionError(describeServiceEndpointActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  /** 端点上下文文案：protocol/port @ address（引用展示用）。 */
  function endpointLabel(endpoint: ServiceEndpoint): string {
    return `${endpoint.protocol}/${endpoint.port} @ ${endpoint.ip_address.address}`;
  }

  // 仅开启已删开关时追加 deleted_at 列（与原实现口径一致）
  const deletedAtColumn: NonNullable<TableProps<EndpointItem>["columns"]>[number] = {
    title: "deleted_at",
    dataIndex: "deleted_at",
    key: "deleted_at",
    render: (value) =>
      value != null ? (
        <span className="font-mono text-xs">{value}</span>
      ) : (
        <span className="text-gray-400">—</span>
      ),
  };

  const columns: TableProps<EndpointItem>["columns"] = [
    {
      title: "ip_address",
      dataIndex: "ip_address",
      key: "ip_address",
      render: (_, endpoint) => (
        <span>
          <span className="font-mono text-xs">{endpoint.ip_address.address}</span>
          {endpoint.deleted_at !== null && (
            <Tag color="red" className="ml-2">
              已删除
            </Tag>
          )}
        </span>
      ),
    },
    {
      title: "interface",
      key: "interface",
      render: (_, endpoint) => (
        <span className="font-mono text-xs">{endpoint.ip_address.interface.name}</span>
      ),
    },
    {
      title: "network",
      key: "network",
      render: (_, endpoint) => endpoint.ip_address.network.name,
    },
    {
      title: "protocol",
      dataIndex: "protocol",
      key: "protocol",
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: "port",
      dataIndex: "port",
      key: "port",
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: "description",
      dataIndex: "description",
      key: "description",
      render: (value) => value ?? <span className="text-gray-400">—</span>,
    },
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeleted ? [deletedAtColumn] : []),
    {
      title: "操作",
      key: "actions",
      render: (_, endpoint) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            className="px-0"
            onClick={() => {
              setActivityPage(1);
              setMode({ kind: "activity", endpoint });
            }}
          >
            Activity
          </Button>
          {canWrite && endpoint.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => {
                setFormError(null);
                setMode({ kind: "edit", endpoint });
                setFormKey((key) => key + 1);
              }}
            >
              编辑
            </Button>
          )}
          {canDelete && endpoint.deleted_at === null && (
            <Button
              type="link"
              size="small"
              className="px-0"
              danger
              onClick={() => requestDelete(endpoint)}
            >
              删除
            </Button>
          )}
          {canRestore && endpoint.deleted_at !== null && !serviceDeleted && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => requestRestore(endpoint)}
            >
              恢复
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const activityColumns: TableProps<ActivityItem>["columns"] = [
    {
      title: "created_at",
      dataIndex: "created_at",
      key: "created_at",
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: "action",
      dataIndex: "action",
      key: "action",
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    { title: "操作者", dataIndex: "operator_username", key: "operator_username" },
    {
      title: "变更前",
      key: "before_data",
      render: (_, item) => (
        <span className="font-mono text-xs">{formatAuditData(item.before_data)}</span>
      ),
    },
    {
      title: "变更后",
      key: "after_data",
      render: (_, item) => (
        <span className="font-mono text-xs">{formatAuditData(item.after_data)}</span>
      ),
    },
  ];

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-gray-900">
          Endpoints（监听端点）— <span className="font-mono text-xs">{service.name}</span>
          <span className="text-gray-400">（{service.resource.hostname}）</span>
        </h3>
        <Button onClick={onBack}>返回服务列表</Button>
      </div>

      {mode.kind === "list" && (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-gray-500">
              经 GET /api/v1/service-endpoints?service_id 过滤（{service.id}）
            </span>
            <span>
              {canWrite && !serviceDeleted && (
                <Button
                  type="primary"
                  onClick={() => {
                    setFormError(null);
                    setMode({ kind: "create" });
                  }}
                >
                  新建端点
                </Button>
              )}
            </span>
          </div>

          {serviceDeleted && (
            <Alert
              className="mb-3"
              type="warning"
              showIcon
              message="所属服务处于已删除状态：无法新建端点（服务端拒绝引用已删服务）；其端点均为已删除状态，恢复端点需先恢复所属服务。"
            />
          )}

          {canViewDeleted && (
            <div className="mb-3">
              <Checkbox
                id="service-endpoints-deleted-toggle"
                checked={showDeleted}
                onChange={(event) => setShowDeleted(event.target.checked)}
              >
                显示已删除端点（deleted=include，需 VIEW_DELETED）
              </Checkbox>
            </div>
          )}

          {state.kind === "loading" && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
              <Spin />
              <span>正在加载该服务的监听端点…</span>
            </div>
          )}

          {state.kind === "error" && (
            <Alert
              className="mb-3"
              type="error"
              showIcon
              message={`加载端点列表失败：${state.message}`}
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
                description={
                  showDeleted
                    ? "该服务暂无监听端点（含已删除）。"
                    : "该服务暂无未删除的监听端点（非错误）。"
                }
              />
            ) : (
              <>
                {state.data.total > state.data.items.length && (
                  <Alert
                    className="mb-3"
                    type="info"
                    showIcon
                    message={`端点总数 ${state.data.total} 个，仅显示前 ${state.data.items.length} 个（按 created_at 排序；列表分页上限 100）。`}
                  />
                )}
                <Table<EndpointItem>
                  rowKey="id"
                  size="middle"
                  pagination={false}
                  scroll={{ x: "max-content" }}
                  dataSource={state.data.items}
                  columns={columns}
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
                              {conflict.object_type === "service"
                                ? `所属服务（${conflict.object_id}）仍处于已删除状态或已不存在`
                                : conflict.object_type === "ip_address"
                                  ? `引用的 IP 地址（${conflict.object_id}）仍处于已删除状态或已不存在`
                                  : conflict.object_type === "interface"
                                    ? `IP 绑定的接口（${conflict.object_id}）仍处于已删除状态或已不存在`
                                    : `依赖对象 ${conflict.object_type}（${conflict.object_id}）仍处于已删除状态`}
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
                        确认软删除监听端点 {endpointLabel(action.endpoint)}？（不级联删除
                        关联对象；同 IP 的 (protocol, port) 软删后释放可复用；version 递增）
                      </span>
                    ) : (
                      <span>
                        确认恢复监听端点 {endpointLabel(action.endpoint)}？（仅恢复自身，
                        不级联、不自动恢复 Service / IP / 接口；将重检同 IP 监听唯一、
                        依赖有效性与 IP 绑定归属，失败不覆盖新对象；version 递增）
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

      {mode.kind === "create" &&
        (serviceOptions.kind === "loading" ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
            <Spin />
            <span>正在加载服务候选（创建表单的 service 选择器）…</span>
          </div>
        ) : serviceOptions.kind === "error" ? (
          <Alert
            type="error"
            showIcon
            message={`加载服务候选失败：${serviceOptions.message}`}
            action={
              <Space size="small">
                <Button
                  size="small"
                  danger
                  onClick={() => setServiceReloadToken((token) => token + 1)}
                >
                  重试
                </Button>
                <Button size="small" onClick={() => setMode({ kind: "list" })}>
                  返回列表
                </Button>
              </Space>
            }
          />
        ) : (
          <>
            {serviceOptions.total > serviceOptions.services.length && (
              <Alert
                className="mb-3"
                type="info"
                showIcon
                message={`服务总数 ${serviceOptions.total} 个，选择器仅列前 ${serviceOptions.services.length} 个（按 name 排序；列表分页上限 100）；面板服务恒可选择。`}
              />
            )}
            <ServiceEndpointForm
              mode="create"
              services={serviceOptions.services}
              ownerService={service}
              submitting={submitting}
              serverError={formError}
              onSubmit={handleCreateSubmit}
              onCancel={() => setMode({ kind: "list" })}
            />
          </>
        ))}

      {mode.kind === "edit" && (
        <ServiceEndpointForm
          key={formKey}
          mode="edit"
          services={[]}
          ownerService={service}
          endpoint={mode.endpoint}
          submitting={submitting}
          serverError={formError}
          onSubmit={handleEditSubmit}
          onCancel={() => setMode({ kind: "list" })}
          onRefresh={refreshAfterConflict}
        />
      )}

      {mode.kind === "activity" && (
        <div>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-base font-semibold text-gray-900">
              Activity — <span className="font-mono text-xs">{endpointLabel(mode.endpoint)}</span>
            </h4>
            <Button onClick={() => setMode({ kind: "list" })}>返回端点列表</Button>
          </div>
          <p className="mb-3 text-sm text-gray-500">
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
              <Empty className="py-8" description="该端点暂无操作流水。" />
            ) : (
              <>
                <Table<ActivityItem>
                  rowKey="id"
                  size="middle"
                  pagination={false}
                  scroll={{ x: "max-content" }}
                  dataSource={activityState.data.items}
                  columns={activityColumns}
                />
                <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-gray-600">
                  <span>
                    共 {activityState.data.total} 条 · 第 {activityState.data.page} /
                    {Math.max(1, Math.ceil(activityState.data.total / activityState.data.page_size))} 页
                  </span>
                  <Button
                    size="small"
                    disabled={activityState.data.page <= 1}
                    onClick={() => setActivityPage(activityState.data.page - 1)}
                  >
                    上一页
                  </Button>
                  <Button
                    size="small"
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
