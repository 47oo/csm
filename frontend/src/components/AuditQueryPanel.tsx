import { Button, Input, Select, DataTable } from "./ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { ServerPagination as Pagination, SurfaceCard } from "./ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
import {
  describeAuditQueryError,
  listAudit,
  type AuditAction,
  type AuditListResponse,
  type AuditObjectType,
  type AuditRow,
} from "../api/audit";
import type { SortOrder } from "../api/clusters";
import {
  auditQueryFieldFromPath,
  buildAuditQuery,
  emptyAuditQueryFormValues,
  parseAuditQueryFormValues,
  type AuditQueryFormErrors,
  type AuditQueryFormValues,
  type AuditQueryParsed,
} from "./auditQueryForm";

/** object_type 过滤选项（Contract §2.1：8 类资源对象 + user）。 */
const OBJECT_TYPE_OPTIONS: { value: AuditObjectType; label: string }[] = [
  { value: "cluster", label: "cluster（集群）" },
  { value: "resource", label: "resource（资源）" },
  { value: "interface", label: "interface（网络接口）" },
  { value: "network", label: "network（网络）" },
  { value: "ip_pool", label: "ip_pool（IP 池）" },
  { value: "ip_address", label: "ip_address（IP 地址）" },
  { value: "service", label: "service（服务）" },
  { value: "service_endpoint", label: "service_endpoint（服务端点）" },
  { value: "user", label: "user（用户账号）" },
];

/** action 过滤选项（Contract §2.1：CREATE/UPDATE/DELETE/RESTORE）。 */
const ACTION_OPTIONS: { value: AuditAction; label: string }[] = [
  { value: "CREATE", label: "CREATE（创建）" },
  { value: "UPDATE", label: "UPDATE（更新）" },
  { value: "DELETE", label: "DELETE（删除）" },
  { value: "RESTORE", label: "RESTORE（恢复）" },
];

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: AuditListResponse }
  | { kind: "error"; message: string; fields: Record<string, string> };

/** 已应用的查询（过滤 + 分页 + 排序；sort 恒 created_at，Contract §2.1）。 */
interface AppliedQuery {
  fields: AuditQueryParsed;
  page: number;
  pageSize: number;
  order: SortOrder;
}

const DEFAULT_QUERY: AppliedQuery = {
  fields: {
    operator: null,
    objectType: null,
    objectId: null,
    action: null,
    createdFrom: null,
    createdTo: null,
  },
  page: 1,
  pageSize: 20,
  order: "desc",
};

/** 审计快照值的紧凑呈现（嵌套对象 JSON 序列化；null / 缺失 → “—”）。 */
function compactValue(value: unknown): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

/** before/after 摘要（key=value 逐对；空快照 → “—”）。 */
function summarizeAuditData(data: Record<string, unknown> | null): string {
  if (data === null || Object.keys(data).length === 0) {
    return "—";
  }
  return Object.entries(data)
    .map(([key, value]) => `${key}=${compactValue(value)}`)
    .join("，");
}

/** 快照完整 JSON（行详情用；null → “（无）”）。 */
function formatAuditDataJson(data: Record<string, unknown> | null): string {
  if (data === null) {
    return "（无）";
  }
  return JSON.stringify(data, null, 2);
}

/**
 * 完整审计查询面板（F015，Contract §2；§22/T25/T26；DR-224）：
 * - 只读查询：GET /api/v1/audit（AUDIT_READ，仅 ADMIN）；过滤条件 AND 组合
 *   （operator 精确匹配 / object_type / object_id（须同现）/ action /
 *   created_from–created_to 闭区间，本地镜像校验见 auditQueryForm.ts）；
 * - 分页 page/page_size（20/50/100）、排序仅 created_at（asc/desc 切换，
 *   同刻 id 升序由服务端保证）；空结果 200 显式区分，绝不把错误伪装成空列表；
 * - 行详情：完整 before/after 快照 JSON（不含密码 / 令牌，I-2）；
 * - 无修改 / 删除 / 清空入口（A8/A30/T36）；Audit 持续保留、查询幂等（A5/A9）。
 */
export default function AuditQueryPanel() {
  // 筛选表单草稿与本地校验错误：点击“筛选”才解析并应用（避免每次击键发请求）
  const [draft, setDraft] = useState<AuditQueryFormValues>(emptyAuditQueryFormValues());
  const [draftErrors, setDraftErrors] = useState<AuditQueryFormErrors>({});
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [selected, setSelected] = useState<AuditRow | null>(null); // 行详情
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listAudit(
      buildAuditQuery(query.fields, query.page, query.pageSize, query.order),
    )
      .then((data) => {
        if (!cancelled) {
          setState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        // 401/403/422/500/网络层：显式呈现（422 字段映射回表单键），可重试
        const described = describeAuditQueryError(error);
        const fields: Record<string, string> = {};
        for (const [path, message] of Object.entries(described.fields)) {
          const key = auditQueryFieldFromPath(path);
          if (key !== null) {
            fields[key] = message;
          } else {
            fields[path] = message; // 分页 / 排序参数等：原样呈现，不静默丢弃
          }
        }
        setState({ kind: "error", message: described.message, fields });
      });
    return () => {
      cancelled = true;
    };
  }, [query, reloadToken]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseAuditQueryFormValues(draft);
    if (!parsed.ok) {
      // 本地镜像校验失败（operator 超长 / object_id 缺 object_type / 非 UUID /
      // 时间非法 / from>to）：不发请求，字段级呈现（服务端同样会 422）
      setDraftErrors(parsed.errors);
      return;
    }
    setDraftErrors({});
    setQuery((current) => ({ ...current, fields: parsed.fields, page: 1 }));
  }

  function resetFilters() {
    setDraft(emptyAuditQueryFormValues());
    setDraftErrors({});
    setQuery((current) => ({ ...current, fields: DEFAULT_QUERY.fields, page: 1 }));
  }

  /** 排序仅 created_at：点击表头切换 asc/desc；回到第 1 页。 */
  function toggleOrder() {
    setQuery((current) => ({
      ...current,
      order: current.order === "asc" ? "desc" : "asc",
      page: 1,
    }));
  }

  function gotoPage(page: number) {
    setQuery((current) => ({ ...current, page }));
  }

  function changePageSize(pageSize: number) {
    setQuery((current) => ({ ...current, pageSize, page: 1 }));
  }

  /** 服务端 422 字段错误（已映射键）优先于本地校验错误呈现。 */
  function fieldError(key: keyof AuditQueryFormErrors): string | undefined {
    if (state.kind === "error") {
      const fromServer = state.fields[key];
      if (fromServer !== undefined) {
        return fromServer;
      }
    }
    return draftErrors[key];
  }

  return (
    <div>
      <InfoState message="跨对象完整审计查询（只读；operator 精确匹配 operator_username，服务端 trim+小写归一；object_id 须与 object_type 同现；created_from/created_to 为闭区间、按 UTC 解释；同刻记录按 id 升序）。无修改 / 删除 / 清空入口，审计持续保留（§22）。" />

      <form className="filter-form" onSubmit={applyFilters}>
        <div className="form-field">
          <label htmlFor="audit-filter-operator">操作者（operator_username 精确匹配）</label>
          <Input
            id="audit-filter-operator"
            type="text"
            value={draft.operator}
            onChange={(event) => setDraft({ ...draft, operator: event.target.value })}
            placeholder="如 user01（trim 后 ≤64 字符）"
          />
          {fieldError("operator") && (
            <p className="field-error">{fieldError("operator")}</p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="audit-filter-object-type">object_type</label>
          <Select
            id="audit-filter-object-type"
            value={draft.objectType}
            onChange={(event) =>
              setDraft({
                ...draft,
                objectType: event.target.value as "" | AuditObjectType,
              })
            }
          >
            <option value="">全部（默认）</option>
            {OBJECT_TYPE_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div className="form-field">
          <label htmlFor="audit-filter-object-id">object_id（UUID，须与 object_type 同现）</label>
          <Input
            id="audit-filter-object-id"
            type="text"
            value={draft.objectId}
            onChange={(event) => setDraft({ ...draft, objectId: event.target.value })}
            placeholder="00000000-0000-0000-0000-000000000000"
            className="mono"
          />
          {fieldError("objectId") && (
            <p className="field-error">{fieldError("objectId")}</p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="audit-filter-action">action</label>
          <Select
            id="audit-filter-action"
            value={draft.action}
            onChange={(event) =>
              setDraft({ ...draft, action: event.target.value as "" | AuditAction })
            }
          >
            <option value="">全部（默认）</option>
            {ACTION_OPTIONS.map(({ value, label }) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </div>
        <div className="form-field">
          <label htmlFor="audit-filter-from">created_from（UTC，闭区间含边界）</label>
          <Input
            id="audit-filter-from"
            type="datetime-local"
            value={draft.createdFrom}
            onChange={(event) => setDraft({ ...draft, createdFrom: event.target.value })}
          />
          {fieldError("createdFrom") && (
            <p className="field-error">{fieldError("createdFrom")}</p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="audit-filter-to">created_to（UTC，闭区间含边界）</label>
          <Input
            id="audit-filter-to"
            type="datetime-local"
            value={draft.createdTo}
            onChange={(event) => setDraft({ ...draft, createdTo: event.target.value })}
          />
          {fieldError("createdTo") && (
            <p className="field-error">{fieldError("createdTo")}</p>
          )}
        </div>
        <div className="filter-actions">
          <Button type="submit">筛选</Button>
          <Button type="button" onClick={resetFilters}>
            重置
          </Button>
        </div>
      </form>

      {state.kind === "loading" && <LoadingState label="正在加载审计记录…" />}

      {state.kind === "error" && (
        <ErrorState
          message={
            <>
              <p>加载审计记录失败：{state.message}</p>
              {Object.keys(state.fields).length > 0 && (
                <ul>
                  {Object.entries(state.fields).map(([field, message]) => (
                    <li key={field}>{field}：{message}</li>
                  ))}
                </ul>
              )}
            </>
          }
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <EmptyState description="没有符合条件的审计记录（当前过滤 / 分页下无数据，非错误）。" />
        ) : (
          <>
            <div className="table-wrap">
              <DataTable className="data-table">
                <thead>
                  <tr>
                    <th>
                      <Button type="button" className="sort-button" onClick={toggleOrder}>
                        created_at
                        {query.order === "asc" ? " ▲" : " ▼"}
                      </Button>
                    </th>
                    <th>action</th>
                    <th>object_type</th>
                    <th>object_id</th>
                    <th>操作者</th>
                    <th>变更前（摘要）</th>
                    <th>变更后（摘要）</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {state.data.items.map((row) => (
                    <tr
                      key={row.id}
                      className={selected?.id === row.id ? "row-selected" : undefined}
                    >
                      <td className="mono">{row.created_at}</td>
                      <td className="mono">{row.action}</td>
                      <td className="mono">{row.object_type}</td>
                      <td className="mono">{row.object_id}</td>
                      <td>
                        {row.operator_username}
                        {row.operator_user_id === null && (
                          <span className="unset">（系统）</span>
                        )}
                      </td>
                      <td className="audit-snapshot">{summarizeAuditData(row.before_data)}</td>
                      <td className="audit-snapshot">{summarizeAuditData(row.after_data)}</td>
                      <td>
                        <Button
                          type="button"
                          className="link-button"
                          onClick={() =>
                            setSelected((current) => (current?.id === row.id ? null : row))
                          }
                        >
                          {selected?.id === row.id ? "收起详情" : "详情"}
                        </Button>
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

      {selected !== null && (
        <SurfaceCard className="panel detail-panel">
          <div className="table-toolbar">
            <h3>
              审计行详情 — <span className="mono">{selected.id}</span>
            </h3>
            <Button type="button" onClick={() => setSelected(null)}>
              关闭详情
            </Button>
          </div>
          <dl className="detail-grid">
            <dt>id</dt>
            <dd className="mono">{selected.id}</dd>
            <dt>action</dt>
            <dd className="mono">{selected.action}</dd>
            <dt>object_type</dt>
            <dd className="mono">{selected.object_type}</dd>
            <dt>object_id</dt>
            <dd className="mono">{selected.object_id}</dd>
            <dt>operator_user_id</dt>
            <dd className="mono">
              {selected.operator_user_id ?? <span className="unset">—（系统 / 引导写入）</span>}
            </dd>
            <dt>operator_username</dt>
            <dd>{selected.operator_username}</dd>
            <dt>created_at</dt>
            <dd className="mono">{selected.created_at}</dd>
          </dl>
          <h4 className="detail-section-title">before_data（变更前快照）</h4>
          <pre className="json-block">{formatAuditDataJson(selected.before_data)}</pre>
          <h4 className="detail-section-title">after_data（变更后快照）</h4>
          <pre className="json-block">{formatAuditDataJson(selected.after_data)}</pre>
        </SurfaceCard>
      )}
    </div>
  );
}
