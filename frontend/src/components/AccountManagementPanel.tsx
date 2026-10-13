import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  Select,
  Spin,
  Table,
  Tag,
  type TableProps,
} from "antd";
import type { Role, UserStatus } from "../api/auth";
import {
  createUser,
  describeUserActionError,
  getUser,
  listUsers,
  updateUser,
  type UserActionError,
  type UserListResponse,
  type UserRow,
  type UserSortField,
} from "../api/users";

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: UserListResponse }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单 / 编辑表单。 */
type PanelMode =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "edit"; user: UserRow };

/** 已应用的查询（过滤 + 分页 + 排序，Contract §4.1）。 */
interface AppliedQuery {
  q: string;
  role: "" | Role;
  status: "" | UserStatus;
  page: number;
  pageSize: number;
  sort: UserSortField;
  order: "asc" | "desc";
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  role: "",
  status: "",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

const SORT_COLUMNS: { field: UserSortField; label: string }[] = [
  { field: "username", label: "username" },
  { field: "role", label: "role" },
  { field: "status", label: "status" },
  { field: "created_at", label: "创建时间" },
  { field: "updated_at", label: "更新时间" },
];

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "VIEWER", label: "VIEWER（只读）" },
  { value: "EDITOR", label: "EDITOR（编辑）" },
  { value: "ADMIN", label: "ADMIN（管理员）" },
];

const STATUS_OPTIONS: { value: UserStatus; label: string }[] = [
  { value: "ACTIVE", label: "ACTIVE（启用）" },
  { value: "DISABLED", label: "DISABLED（停用）" },
];

/** username 规则（Contract §4.3：trim+小写归一后 ^[a-z0-9._-]{3,64}$）。 */
const USERNAME_PATTERN = /^[a-z0-9._-]{3,64}$/;

/** password 长度（Contract §8 可实施默认 8–128，非产品业务规则）。 */
const PASSWORD_MIN = 8;
const PASSWORD_MAX = 128;

/** 创建表单原始值。 */
interface CreateFormValues {
  username: string;
  password: string;
  role: Role;
}

/** 创建表单本地校验错误（键与服务端 422 fields 同名）。 */
type CreateFormErrors = Partial<Record<"username" | "password" | "role", string>>;

/** 编辑表单值（username 只读展示；role/status 可改）。 */
interface EditFormValues {
  role: Role;
  status: UserStatus;
}

function emptyCreateFormValues(): CreateFormValues {
  return { username: "", password: "", role: "VIEWER" };
}

/** status 徽标（ACTIVE 启用 / DISABLED 停用）。 */
function statusBadge(status: UserStatus): ReactNode {
  return status === "ACTIVE" ? (
    <Tag color="success">{status}</Tag>
  ) : (
    <Tag color="default">{status}</Tag>
  );
}

/** 创建表单本地校验（服务端 422 的本地镜像，快速反馈）。 */
function parseCreateFormValues(
  values: CreateFormValues,
): { ok: true; fields: CreateFormValues } | { ok: false; errors: CreateFormErrors } {
  const errors: CreateFormErrors = {};
  const username = values.username.trim();
  // 服务端 trim+小写归一后校验；本地按同一口径镜像（归一后须全为合法字符）
  if (username === "") {
    errors.username = "username 不能为空";
  } else if (!USERNAME_PATTERN.test(username.toLowerCase())) {
    errors.username =
      "username 须为 3–64 位小写字母 / 数字 / . _ -（服务端会去除首尾空白并转小写后校验）";
  }
  if (values.password === "") {
    errors.password = "password 不能为空";
  } else if (values.password.length < PASSWORD_MIN || values.password.length > PASSWORD_MAX) {
    errors.password = `password 长度须为 ${PASSWORD_MIN}–${PASSWORD_MAX} 字符（初始密码，创建后不回显）`;
  }
  if (Object.keys(errors).length > 0) {
    return { ok: false, errors };
  }
  return { ok: true, fields: { username, password: values.password, role: values.role } };
}

/**
 * System 页 · 账号管理面板（F015，Contract §4；§23/T26；DR-218–DR-221）：
 * - 列表：GET /api/v1/users（USER_ADMIN，仅 ADMIN）：role/status/q（username
 *   大小写不敏感子串）过滤 + 分页 + 排序（§28 列表基线）；Loading / Empty /
 *   Error 显式区分，错误绝不伪装成空列表；
 * - 创建（§4.3）：username（trim+小写归一 ^[a-z0-9._-]{3,64}$）/ 初始密码
 *   （8–128，Contract §8 可实施默认；argon2 hash，不回显、不入 Audit）/ role；
 *   重复 username → 409 unique_conflict → username 字段级错误；
 * - 编辑（§4.4）：role / status 变更（PATCH 仅携带变化字段 + version 乐观锁）；
 *   停用同事务删该账号全部会话（其现有登录立即失效、重新启用前无法登录），
 *   启用恢复登录，角色变更即时生效；409 VERSION_CONFLICT → 刷新最新数据后
 *   重改，不静默重试；
 * - 无删除账号、无改密 / 重置 / 注册入口（§4.5，I-9/I-10）；本面板仅对具
 *   USER_ADMIN 的角色渲染（SystemPage 门控；服务端仍鉴权）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用与参数 / 创建 /
 * 角色分配 / 停用启用行为 / 校验与错误文案 / 权限门控 / 四态 / 文案均不变）。
 */
export default function AccountManagementPanel() {
  const [draft, setDraft] = useState<{ q: string; role: "" | Role; status: "" | UserStatus }>({
    q: "",
    role: "",
    status: "",
  });
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [reloadToken, setReloadToken] = useState(0);

  // 创建表单
  const [createValues, setCreateValues] = useState<CreateFormValues>(emptyCreateFormValues());
  const [createErrors, setCreateErrors] = useState<CreateFormErrors>({});
  const [createServerError, setCreateServerError] = useState<UserActionError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 编辑表单
  const [editValues, setEditValues] = useState<EditFormValues>({ role: "VIEWER", status: "ACTIVE" });
  const [editFormKey, setEditFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [editServerError, setEditServerError] = useState<UserActionError | null>(null);
  const [editNotice, setEditNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listUsers({
      q: query.q === "" ? undefined : query.q,
      role: query.role === "" ? undefined : query.role,
      status: query.status === "" ? undefined : query.status,
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
        // 401/403/422/500/网络层：显式呈现，可重试
        const described = describeUserActionError(error);
        setState({ kind: "error", message: described.message });
      });
    return () => {
      cancelled = true;
    };
  }, [query, reloadToken]);

  /** 点击“筛选”才应用草稿（AntD Form onFinish 已 preventDefault）。 */
  function applyFilters() {
    setQuery((current) => ({
      ...current,
      q: draft.q,
      role: draft.role,
      status: draft.status,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", role: "", status: "" });
    setQuery((current) => ({ ...current, q: "", role: "", status: "", page: 1 }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: UserSortField) {
    setQuery((current) => ({
      ...current,
      sort: field,
      order: current.sort === field && current.order === "asc" ? "desc" : "asc",
      page: 1,
    }));
  }

  function gotoPage(page: number) {
    setQuery((current) => ({ ...current, page }));
  }

  function changePageSize(pageSize: number) {
    setQuery((current) => ({ ...current, pageSize, page: 1 }));
  }

  // ---- 创建（POST，Contract §4.3；AntD Form onFinish 已 preventDefault）----

  function handleCreateSubmit() {
    const parsed = parseCreateFormValues(createValues);
    if (!parsed.ok) {
      // 本地镜像校验失败：不发请求（服务端同样 422）
      setCreateErrors(parsed.errors);
      return;
    }
    setCreateErrors({});
    setSubmitting(true);
    setCreateServerError(null);
    createUser(parsed.fields)
      .then(() => {
        // 201：创建成功（该账号可按角色登录）；回列表并重载
        setCreateValues(emptyCreateFormValues());
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 unique_conflict（username）/ 422 / 403：明确呈现，不静默重试
        setCreateServerError(describeUserActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  // ---- 编辑（PATCH，Contract §4.4；AntD Form onFinish 已 preventDefault）----

  function openEdit(user: UserRow) {
    setEditServerError(null);
    setEditNotice(null);
    setEditValues({ role: user.role, status: user.status });
    setEditFormKey((key) => key + 1);
    setMode({ kind: "edit", user });
  }

  function handleEditSubmit() {
    if (mode.kind !== "edit") {
      return;
    }
    const user = mode.user;
    // PATCH 仅携带变化字段（省略 = 保持原值）；role/status 至少一个（都缺 422）
    const payload: { version: number; role?: Role; status?: UserStatus } = {
      version: user.version,
    };
    if (editValues.role !== user.role) {
      payload.role = editValues.role;
    }
    if (editValues.status !== user.status) {
      payload.status = editValues.status;
    }
    if (payload.role === undefined && payload.status === undefined) {
      setEditNotice("没有检测到修改内容：请修改角色或状态后再保存。");
      return;
    }
    setEditNotice(null);
    setSubmitting(true);
    setEditServerError(null);
    updateUser(user.id, payload)
      .then(() => {
        // 200：version+1；角色变更即时生效；停用已删该账号全部会话
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT / 404 / 422 / 403：明确呈现，不静默重试
        setEditServerError(describeUserActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重取该账号并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    if (mode.kind !== "edit") {
      return;
    }
    const id = mode.user.id;
    setEditServerError(null);
    setEditNotice(null);
    setSubmitting(true);
    getUser(id)
      .then(({ user: fresh }) => {
        setMode({ kind: "edit", user: fresh });
        setEditValues({ role: fresh.role, status: fresh.status });
        setEditFormKey((key) => key + 1);
      })
      .catch((error: unknown) => {
        setEditServerError(describeUserActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 服务端字段错误（创建 / 编辑共用键空间）优先于本地校验错误呈现。 */
  function createFieldError(
    key: keyof CreateFormErrors,
  ): string | undefined {
    if (createServerError?.fields[key] !== undefined) {
      return createServerError.fields[key];
    }
    return createErrors[key];
  }

  /** 可排序列表头（同字段切换 asc/desc，新字段默认 asc）。 */
  const sortHeader = (field: UserSortField, label: string): ReactNode => (
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

  /** 列定义（文案与数据口径同旧版；排序经表头按钮，分页由下方 Pagination 承担）。 */
  const columns: TableProps<UserRow>["columns"] = [
    ...SORT_COLUMNS.map(({ field, label }) => {
      if (field === "status") {
        return {
          title: sortHeader(field, label),
          dataIndex: field,
          key: field,
          render: (value: UserStatus) => statusBadge(value),
        };
      }
      return {
        title: sortHeader(field, label),
        dataIndex: field,
        key: field,
        render: (value: string) => <span className="font-mono">{value}</span>,
      };
    }),
    { title: "version", dataIndex: "version", key: "version" },
    {
      title: "操作",
      key: "actions",
      render: (_, user: UserRow) => (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() => openEdit(user)}
        >
          编辑
        </Button>
      ),
    },
  ];

  return (
    <div>
      <p className="mb-4 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-sm leading-6 text-gray-600">
        本地账号管理（仅 ADMIN）：创建账号并分配角色、变更角色、停用 / 启用账号。
        不开放自行注册；账号不物理删除（停用保留历史身份，既有审计不变）；
        无改密 / 重置入口（一期未实现）。停用会立即失效该账号全部现有会话，
        且在重新启用前无法登录；角色变更即时生效。
      </p>

      {mode.kind === "list" && (
        <>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold text-gray-900">账号列表</h3>
            <Button
              type="primary"
              onClick={() => {
                setCreateValues(emptyCreateFormValues());
                setCreateErrors({});
                setCreateServerError(null);
                setMode({ kind: "create" });
              }}
            >
              新建账号
            </Button>
          </div>

          <Form layout="vertical" onFinish={applyFilters}>
            <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
              <div>
                <label
                  htmlFor="user-filter-q"
                  className="mb-1 block text-sm text-gray-700"
                >
                  模糊搜索（username 子串，大小写不敏感）
                </label>
                <Input
                  id="user-filter-q"
                  value={draft.q}
                  onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                  placeholder="大小写不敏感子串匹配"
                />
              </div>
              <div>
                <label
                  htmlFor="user-filter-role"
                  className="mb-1 block text-sm text-gray-700"
                >
                  role
                </label>
                <Select<"" | Role>
                  id="user-filter-role"
                  className="w-full"
                  value={draft.role}
                  onChange={(value) => setDraft({ ...draft, role: value })}
                  options={[{ value: "", label: "全部（默认）" }, ...ROLE_OPTIONS]}
                />
              </div>
              <div>
                <label
                  htmlFor="user-filter-status"
                  className="mb-1 block text-sm text-gray-700"
                >
                  status
                </label>
                <Select<"" | UserStatus>
                  id="user-filter-status"
                  className="w-full"
                  value={draft.status}
                  onChange={(value) => setDraft({ ...draft, status: value })}
                  options={[{ value: "", label: "全部（默认）" }, ...STATUS_OPTIONS]}
                />
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
              <span>正在加载账号列表…</span>
            </div>
          )}

          {state.kind === "error" && (
            <Alert
              className="mt-2"
              type="error"
              showIcon
              message={`加载账号列表失败：${state.message}`}
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
                className="mt-8"
                description="没有符合条件的账号（当前过滤 / 分页下无数据，非错误）。"
              />
            ) : (
              <>
                <div className="mt-2 overflow-x-auto">
                  <Table<UserRow>
                    rowKey="id"
                    size="middle"
                    columns={columns}
                    dataSource={state.data.items}
                    pagination={false}
                    scroll={{ x: "max-content" }}
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
        </>
      )}

      {mode.kind === "create" && (
        <Form layout="vertical" onFinish={handleCreateSubmit} noValidate>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold text-gray-900">新建账号</h3>
            <Button onClick={() => setMode({ kind: "list" })} disabled={submitting}>
              返回列表
            </Button>
          </div>

          <div className="mb-4">
            <label
              htmlFor="user-create-username"
              className="mb-1 block text-sm text-gray-700"
            >
              username
            </label>
            <Input
              id="user-create-username"
              value={createValues.username}
              onChange={(event) =>
                setCreateValues({ ...createValues, username: event.target.value })
              }
              placeholder="3–64 位小写字母 / 数字 / . _ -"
              status={createFieldError("username") ? "error" : undefined}
            />
            {createFieldError("username") && (
              <p className="mt-1 text-xs text-red-500">{createFieldError("username")}</p>
            )}
          </div>

          <div className="mb-4">
            <label
              htmlFor="user-create-password"
              className="mb-1 block text-sm text-gray-700"
            >
              初始密码（8–128 字符；创建后不回显）
            </label>
            <Input
              id="user-create-password"
              type="password"
              value={createValues.password}
              onChange={(event) =>
                setCreateValues({ ...createValues, password: event.target.value })
              }
              autoComplete="new-password"
              status={createFieldError("password") ? "error" : undefined}
            />
            {createFieldError("password") && (
              <p className="mt-1 text-xs text-red-500">{createFieldError("password")}</p>
            )}
          </div>

          <div className="mb-4">
            <label
              htmlFor="user-create-role"
              className="mb-1 block text-sm text-gray-700"
            >
              role
            </label>
            <Select<Role>
              id="user-create-role"
              className="w-full"
              value={createValues.role}
              onChange={(value) => setCreateValues({ ...createValues, role: value })}
              options={ROLE_OPTIONS}
              status={createFieldError("role") ? "error" : undefined}
            />
            {createFieldError("role") && (
              <p className="mt-1 text-xs text-red-500">{createFieldError("role")}</p>
            )}
          </div>

          {createServerError && (
            <Alert
              className="mb-4"
              type="error"
              showIcon
              message={createServerError.message}
            />
          )}

          <div className="flex gap-2">
            <Button type="primary" htmlType="submit" disabled={submitting}>
              {submitting ? "正在创建…" : "创建账号"}
            </Button>
          </div>
        </Form>
      )}

      {mode.kind === "edit" && (
        <Form
          layout="vertical"
          onFinish={handleEditSubmit}
          key={editFormKey}
          noValidate
        >
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold text-gray-900">
              编辑账号 — <span className="font-mono">{mode.user.username}</span>
            </h3>
            <Button onClick={() => setMode({ kind: "list" })} disabled={submitting}>
              返回列表
            </Button>
          </div>

          <dl className="mb-4 grid grid-cols-[max-content_minmax(0,1fr)] items-start gap-x-6 gap-y-1 text-sm">
            <dt className="text-gray-500">username（不可修改）</dt>
            <dd className="font-mono">{mode.user.username}</dd>
            <dt className="text-gray-500">id</dt>
            <dd className="font-mono">{mode.user.id}</dd>
            <dt className="text-gray-500">version（乐观锁）</dt>
            <dd>{mode.user.version}</dd>
          </dl>

          <div className="mb-4">
            <label htmlFor="user-edit-role" className="mb-1 block text-sm text-gray-700">
              role
            </label>
            <Select<Role>
              id="user-edit-role"
              className="w-full"
              value={editValues.role}
              onChange={(value) => setEditValues({ ...editValues, role: value })}
              options={ROLE_OPTIONS}
              status={editServerError?.fields.role ? "error" : undefined}
            />
            {editServerError?.fields.role && (
              <p className="mt-1 text-xs text-red-500">{editServerError.fields.role}</p>
            )}
          </div>

          <div className="mb-4">
            <label htmlFor="user-edit-status" className="mb-1 block text-sm text-gray-700">
              status
            </label>
            <Select<UserStatus>
              id="user-edit-status"
              className="w-full"
              value={editValues.status}
              onChange={(value) => setEditValues({ ...editValues, status: value })}
              options={STATUS_OPTIONS}
              status={editServerError?.fields.status ? "error" : undefined}
            />
            {editServerError?.fields.status && (
              <p className="mt-1 text-xs text-red-500">{editServerError.fields.status}</p>
            )}
          </div>

          {editNotice && (
            <Alert className="mb-4" type="error" showIcon message={editNotice} />
          )}

          {editServerError && (
            <Alert
              className="mb-4"
              type="error"
              showIcon
              message={editServerError.message}
              description={
                editServerError.versionConflict ? (
                  <Button
                    className="mt-1"
                    size="small"
                    onClick={refreshAfterConflict}
                    disabled={submitting}
                  >
                    刷新最新数据
                  </Button>
                ) : undefined
              }
            />
          )}

          <div className="flex gap-2">
            <Button type="primary" htmlType="submit" disabled={submitting}>
              {submitting ? "正在保存…" : "保存修改"}
            </Button>
          </div>
        </Form>
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
