import { useEffect, useState, type ReactNode } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import type { Resource } from "../api/resources";
import { listServices, type ServiceListResponse } from "../api/services";

/** 服务列表加载状态（分页上限 100，Contract §4）。 */
type ServiceListState =
  | { kind: "loading" }
  | { kind: "success"; data: ServiceListResponse }
  | { kind: "error"; message: string };

interface ServicesPanelProps {
  /** 所属 Resource（Services 归属创建后不可改；本区域只读，管理入口在 Services 页面）。 */
  resource: Resource;
  user: User;
}

/** status 徽标样式（与 ServicesPage 共用口径：UNKNOWN 复用 badge-unknown）。 */
function statusBadge(status: string): ReactNode {
  const cls =
    status === "RUNNING"
      ? "badge badge-active"
      : status === "STOPPED"
        ? "badge badge-inactive"
        : "badge badge-unknown";
  return <span className={cls}>{status}</span>;
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

  return (
    <>
      <h3 className="detail-section-title">Services（运行服务）</h3>

      <div className="table-toolbar">
        <span className="permissions-note">
          经 GET /api/v1/services?resource_id 过滤（{resource.hostname}）；登记 / 编辑 /
          删除 / 恢复 / Activity 请前往 Services 页面
        </span>
      </div>

      {resourceDeleted && (
        <p className="status status-empty">
          所属资源处于已删除状态：服务的创建与恢复需先恢复所属资源（服务端重检依赖）。
        </p>
      )}

      {canViewDeleted && (
        <div className="form-field checkbox-field deleted-toggle">
          <label htmlFor="services-deleted-toggle">
            <input
              id="services-deleted-toggle"
              type="checkbox"
              checked={showDeleted}
              onChange={(event) => setShowDeleted(event.target.checked)}
            />
            显示已删除服务（deleted=include，需 VIEW_DELETED）
          </label>
        </div>
      )}

      {state.kind === "loading" && (
        <p className="status status-loading">正在加载该资源的服务登记…</p>
      )}

      {state.kind === "error" && (
        <div className="status status-error" role="alert">
          <p>加载服务列表失败：{state.message}</p>
          <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
            重试
          </button>
        </div>
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <p className="status status-empty">
            {showDeleted
              ? "该资源暂无服务登记（含已删除）。"
              : "该资源暂无未删除的服务登记（非错误）。"}
          </p>
        ) : (
          <>
            {state.data.total > state.data.items.length && (
              <p className="status status-empty">
                服务总数 {state.data.total} 条，仅显示前 {state.data.items.length} 条
                （按 name 排序；列表分页上限 100）。
              </p>
            )}
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>name</th>
                    <th>status</th>
                    <th>description</th>
                    <th>created_at</th>
                    <th>updated_at</th>
                    <th>version</th>
                    {showDeleted && <th>deleted_at</th>}
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((service) => (
                    <tr key={service.id}>
                      <td>
                        {service.name}
                        {service.deleted_at !== null && (
                          <span className="badge badge-deleted">已删除</span>
                        )}
                      </td>
                      <td>{statusBadge(service.status)}</td>
                      <td>{service.description ?? <span className="unset">—</span>}</td>
                      <td className="mono">{service.created_at}</td>
                      <td className="mono">{service.updated_at}</td>
                      <td>{service.version}</td>
                      {showDeleted && (
                        <td className="mono">
                          {service.deleted_at ?? <span className="unset">—</span>}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ))}
    </>
  );
}
