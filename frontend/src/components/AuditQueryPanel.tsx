import { useEffect, useState } from "react";
import { Alert, Button, Empty, Form, Input, Select, Spin, Table } from "antd";
import type { TableProps } from "antd";
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
 * 完整审计查询面板（F015，Contract §2；§22/T25/T26；DR-22）：
 * - 只读查询：GET /api/v1/audit（AUDIT_READ，仅 ADMIN）；过滤条件 AND 组合
 *   （operator 精确匹配 / object_type / object_id（须同现）/ action /
 *   created_from–created_to 闭区间，本地镜像校验见 auditQueryForm.ts）；
 * - 分页 page/page_size（20/50/100）、排序仅 created_at（asc/desc 切换，
 *   同刻 id 升序由服务端保证）；空结果 200 显式区分，绝不把错误伪装成空列表；
 * - 行详情：完整 before/after 快照 JSON（不含密码 / 令牌，I-2）；
 * - 无修改 / 删除 / 清空入口（A8/A30/T36）；Audit 持续保留、查询幂等（A5/A9）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 过滤与分页参数 /
 * 四态 / 权限 / 行详情 / 文案均保持不变）。
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

  /** 点击“筛选”才解析并应用草稿（提交时机由 AntD Form onFinish 接管）。 */
  function applyFilters() {
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

  /** 列定义（文案与数据口径同旧版；排序仅 created_at，由表头按钮切换）。 */
  const columns: TableProps<AuditRow>["columns"] = [
    {
      title: (
        <Button type="link" size="small" className="px-0 font-semibold" onClick={toggleOrder}>
          created_at
          {query.order === "asc" ? " ▲" : " ▼"}
        </Button>
      ),
      dataIndex: "created_at",
      key: "created_at",
      width: 180,
      render: (value: string) => <span className="font-mono">{value}</span>,
    },
    {
      title: "action",
      dataIndex: "action",
      key: "action",
      render: (value: string) => <span className="font-mono">{value}</span>,
    },
    {
      title: "object_type",
      dataIndex: "object_type",
      key: "object_type",
      render: (value: string) => <span className="font-mono">{value}</span>,
    },
    {
      title: "object_id",
      dataIndex: "object_id",
      key: "object_id",
      render: (value: string) => <span className="font-mono">{value}</span>,
    },
    {
      title: "操作者",
      key: "operator",
      render: (_, row) => (
        <span>
          {row.operator_username}
          {row.operator_user_id === null && (
            <span className="ml-1 text-gray-400">（系统）</span>
          )}
        </span>
      ),
    },
    {
      title: "变更前（摘要）",
      key: "before_data",
      width: 260,
      render: (_, row) => (
        <div className="max-w-64 text-xs leading-5 break-all">
          {summarizeAuditData(row.before_data)}
        </div>
      ),
    },
    {
      title: "变更后（摘要）",
      key: "after_data",
      width: 260,
      render: (_, row) => (
        <div className="max-w-64 text-xs leading-5 break-all">
          {summarizeAuditData(row.after_data)}
        </div>
      ),
    },
    {
      title: "操作",
      key: "row-detail",
      render: (_, row) => (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() =>
            setSelected((current) => (current?.id === row.id ? null : row))
          }
        >
          {selected?.id === row.id ? "收起详情" : "详情"}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <p className="mb-4 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm leading-6 text-gray-600">
        跨对象完整审计查询（只读；operator 精确匹配 operator_username，服务端
        trim+小写归一；object_id 须与 object_type 同现；created_from/created_to
        为闭区间、按 UTC 解释；同刻记录按 id 升序）。无修改 / 删除 / 清空入口，
        审计持续保留（§22）。
      </p>

      <Form layout="vertical" onFinish={applyFilters}>
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
          <div>
            <label
              htmlFor="audit-filter-operator"
              className="mb-1 block text-sm text-gray-700"
            >
              操作者（operator_username 精确匹配）
            </label>
            <Input
              id="audit-filter-operator"
              value={draft.operator}
              onChange={(event) => setDraft({ ...draft, operator: event.target.value })}
              placeholder="如 user01（trim 后 ≤64 字符）"
              status={fieldError("operator") ? "error" : undefined}
            />
            {fieldError("operator") && (
              <p className="mt-1 text-xs text-red-500">{fieldError("operator")}</p>
            )}
          </div>
          <div>
            <label
              htmlFor="audit-filter-object-type"
              className="mb-1 block text-sm text-gray-700"
            >
              object_type
            </label>
            <Select<"" | AuditObjectType>
              id="audit-filter-object-type"
              className="w-full"
              value={draft.objectType}
              onChange={(value) => setDraft({ ...draft, objectType: value })}
              options={[{ value: "", label: "全部（默认）" }, ...OBJECT_TYPE_OPTIONS]}
            />
          </div>
          <div>
            <label
              htmlFor="audit-filter-object-id"
              className="mb-1 block text-sm text-gray-700"
            >
              object_id（UUID，须与 object_type 同现）
            </label>
            <Input
              id="audit-filter-object-id"
              value={draft.objectId}
              onChange={(event) => setDraft({ ...draft, objectId: event.target.value })}
              placeholder="00000000-0000-0000-0000-000000000000"
              className="font-mono"
              status={fieldError("objectId") ? "error" : undefined}
            />
            {fieldError("objectId") && (
              <p className="mt-1 text-xs text-red-500">{fieldError("objectId")}</p>
            )}
          </div>
          <div>
            <label
              htmlFor="audit-filter-action"
              className="mb-1 block text-sm text-gray-700"
            >
              action
            </label>
            <Select<"" | AuditAction>
              id="audit-filter-action"
              className="w-full"
              value={draft.action}
              onChange={(value) => setDraft({ ...draft, action: value })}
              options={[{ value: "", label: "全部（默认）" }, ...ACTION_OPTIONS]}
            />
          </div>
          <div>
            <label
              htmlFor="audit-filter-from"
              className="mb-1 block text-sm text-gray-700"
            >
              created_from（UTC，闭区间含边界）
            </label>
            {/* 沿用 datetime-local 字符串语义，与 auditQueryForm 解析保持一致 */}
            <Input
              id="audit-filter-from"
              type="datetime-local"
              value={draft.createdFrom}
              onChange={(event) => setDraft({ ...draft, createdFrom: event.target.value })}
              status={fieldError("createdFrom") ? "error" : undefined}
            />
            {fieldError("createdFrom") && (
              <p className="mt-1 text-xs text-red-500">{fieldError("createdFrom")}</p>
            )}
          </div>
          <div>
            <label
              htmlFor="audit-filter-to"
              className="mb-1 block text-sm text-gray-700"
            >
              created_to（UTC，闭区间含边界）
            </label>
            <Input
              id="audit-filter-to"
              type="datetime-local"
              value={draft.createdTo}
              onChange={(event) => setDraft({ ...draft, createdTo: event.target.value })}
              status={fieldError("createdTo") ? "error" : undefined}
            />
            {fieldError("createdTo") && (
              <p className="mt-1 text-xs text-red-500">{fieldError("createdTo")}</p>
            )}
          </div>
        </div>
        <div className="mt-4 flex gap-2">
          <Button type="primary" htmlType="submit">
            筛选
          </Button>
          <Button onClick={resetFilters}>重置</Button>
        </div>
      </Form>

      {state.kind === "loading" && (
        <div className="mt-2 flex items-center gap-3 py-6 text-gray-500">
          <Spin />
          <span>正在加载审计记录…</span>
        </div>
      )}

      {state.kind === "error" && (
        <Alert
          className="mt-2"
          type="error"
          message={`加载审计记录失败：${state.message}`}
          description={
            <>
              {Object.keys(state.fields).length > 0 && (
                <ul className="list-disc pl-5">
                  {Object.entries(state.fields).map(([field, message]) => (
                    <li key={field}>
                      {field}：{message}
                    </li>
                  ))}
                </ul>
              )}
              <Button
                className="mt-2"
                onClick={() => setReloadToken((token) => token + 1)}
              >
                重试
              </Button>
            </>
          }
        />
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <Empty
            className="mt-8"
            description="没有符合条件的审计记录（当前过滤 / 分页下无数据，非错误）。"
          />
        ) : (
          <>
            <div className="mt-2 overflow-x-auto">
              <Table<AuditRow>
                rowKey="id"
                columns={columns}
                dataSource={state.data.items}
                pagination={false}
                rowClassName={(row) => (selected?.id === row.id ? "[&>td]:bg-blue-50" : "")}
              />
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
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold">
              审计行详情 — <span className="font-mono">{selected.id}</span>
            </h3>
            <Button onClick={() => setSelected(null)}>关闭详情</Button>
          </div>
          <dl className="grid grid-cols-[max-content_minmax(0,1fr)] items-start gap-x-6 gap-y-1 text-sm">
            <dt className="text-gray-500">id</dt>
            <dd className="font-mono">{selected.id}</dd>
            <dt className="text-gray-500">action</dt>
            <dd className="font-mono">{selected.action}</dd>
            <dt className="text-gray-500">object_type</dt>
            <dd className="font-mono">{selected.object_type}</dd>
            <dt className="text-gray-500">object_id</dt>
            <dd className="font-mono">{selected.object_id}</dd>
            <dt className="text-gray-500">operator_user_id</dt>
            <dd className="font-mono">
              {selected.operator_user_id ?? (
                <span className="text-gray-400">—（系统 / 引导写入）</span>
              )}
            </dd>
            <dt className="text-gray-500">operator_username</dt>
            <dd>{selected.operator_username}</dd>
            <dt className="text-gray-500">created_at</dt>
            <dd className="font-mono">{selected.created_at}</dd>
          </dl>
          <h4 className="mt-4 mb-2 text-sm font-semibold text-gray-700">
            before_data（变更前快照）
          </h4>
          <pre className="overflow-auto rounded-md bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-100">
            {formatAuditDataJson(selected.before_data)}
          </pre>
          <h4 className="mt-4 mb-2 text-sm font-semibold text-gray-700">
            after_data（变更后快照）
          </h4>
          <pre className="overflow-auto rounded-md bg-gray-950 p-3 font-mono text-xs leading-5 text-gray-100">
            {formatAuditDataJson(selected.after_data)}
          </pre>
        </div>
      )}
    </div>
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
