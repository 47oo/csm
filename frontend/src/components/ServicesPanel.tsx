import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Spin,
  Table,
  Tag,
  type TableProps,
} from "antd";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import type { Resource } from "../api/resources";
import { listServices, type ServiceListResponse } from "../api/services";

/** 服务列表加载状态（分页上限 100，Contract §4）。 */
type ServiceListState =
  | { kind: "loading" }
  | { kind: "success"; data: ServiceListResponse }
  | { kind: "error"; message: string };

/** Table 行数据类型（取自 ServiceListResponse.items 元素）。 */
type ServiceItem = ServiceListResponse["items"][number];

interface ServicesPanelProps {
  /** 所属 Resource（Services 归属创建后不可改；本区域只读，管理入口在 Services 页面）。 */
  resource: Resource;
  user: User;
}

/** status 徽标（与 ServicesPage 共用口径：UNKNOWN 复用 badge-unknown）。 */
function statusBadge(status: string): ReactNode {
  if (status === "RUNNING") {
    return <Tag color="success">{status}</Tag>;
  }
  if (status === "STOPPED") {
    return <Tag color="default">{status}</Tag>;
  }
  return <Tag color="warning">{status}</Tag>;
}

/**
 * Resource Detail 的 Services 区域（F011，§18 / DR-152；Contract §4/§5）：
 * - 列表：GET /api/v1/services?resource_id=<资源 id>（默认未删除；已删开关 →
 *   deleted=include，需 VIEW_DELETED，服务端仍 403 把关）；Loading / Empty /
 *   Error 显式区分，错误可重试、绝不伪装成空列表；
 * - 只读展示（§18 数据获得即可）：name / status（人工维护登记状态）/ description
 *   / created_at / updated_at / version；登记、编辑、软删、恢复与 Activity 的
 *   完整入口在 Services 页面（F011 §28）；
 * - Service 经 Resource 间接归属 Cluster；本区域不做聚合展示（归 F013）。
 */
export default function ServicesPanel({ resource, user }: ServicesPanelProps) {
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");
  const resourceDeleted = resource.deleted_at !== null;
  const [showDeleted, setShowDeleted] = useState(false);
  const [state, setState] = useState<ServiceListState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    // 已删开关：include 需 VIEW_DELETED（开关仅在具备权限时渲染；服务端仍 403 把关）
    listServices({
      resource_id: resource.id,
      deleted: showDeleted ? "include" : "exclude",
      page_size: 100,
      sort: "name",
      order: "asc",
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
  }, [resource.id, showDeleted, reloadToken]);

  // 仅开启已删开关时追加 deleted_at 列（与原实现口径一致）
  const deletedAtColumn: NonNullable<TableProps<ServiceItem>["columns"]>[number] = {
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

  const columns: TableProps<ServiceItem>["columns"] = [
    {
      title: "name",
      dataIndex: "name",
      key: "name",
      render: (_, service) => (
        <span>
          {service.name}
          {service.deleted_at !== null && (
            <Tag color="red" className="ml-2">
              已删除
            </Tag>
          )}
        </span>
      ),
    },
    {
      title: "status",
      dataIndex: "status",
      key: "status",
      render: (value) => statusBadge(value),
    },
    {
      title: "description",
      dataIndex: "description",
      key: "description",
      render: (value) => value ?? <span className="text-gray-400">—</span>,
    },
    {
      title: "created_at",
      dataIndex: "created_at",
      key: "created_at",
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    {
      title: "updated_at",
      dataIndex: "updated_at",
      key: "updated_at",
      render: (value) => <span className="font-mono text-xs">{value}</span>,
    },
    { title: "version", dataIndex: "version", key: "version" },
    ...(showDeleted ? [deletedAtColumn] : []),
  ];

  return (
    <>
      <h3 className="mb-1 text-base font-semibold text-gray-900">Services（运行服务）</h3>

      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-gray-500">
          经 GET /api/v1/services?resource_id 过滤（{resource.hostname}）；登记 / 编辑 / 删除 /
          恢复 / Activity 请前往 Services 页面
        </span>
      </div>

      {resourceDeleted && (
        <Alert
          className="mb-3"
          type="warning"
          showIcon
          message="所属资源处于已删除状态：服务的创建与恢复需先恢复所属资源（服务端重检依赖）。"
        />
      )}

      {canViewDeleted && (
        <div className="mb-3">
          <Checkbox
            id="services-deleted-toggle"
            checked={showDeleted}
            onChange={(event) => setShowDeleted(event.target.checked)}
          >
            显示已删除服务（deleted=include，需 VIEW_DELETED）
          </Checkbox>
        </div>
      )}

      {state.kind === "loading" && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
          <Spin />
          <span>正在加载该资源的服务登记…</span>
        </div>
      )}

      {state.kind === "error" && (
        <Alert
          className="mb-3"
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
            description={
              showDeleted
                ? "该资源暂无服务登记（含已删除）。"
                : "该资源暂无未删除的服务登记（非错误）。"
            }
          />
        ) : (
          <>
            {state.data.total > state.data.items.length && (
              <Alert
                className="mb-3"
                type="info"
                showIcon
                message={`服务总数 ${state.data.total} 条，仅显示前 ${state.data.items.length} 条（按 name 排序；列表分页上限 100）。`}
              />
            )}
            <Table<ServiceItem>
              rowKey="id"
              size="middle"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={state.data.items}
              columns={columns}
            />
          </>
        ))}
    </>
  );
}
