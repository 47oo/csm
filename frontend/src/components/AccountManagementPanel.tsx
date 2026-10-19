import { Button, Input, Select, DataTable } from "./ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { ServerPagination as Pagination, StatusTag, statusTone } from "./ui/surfaces";
import { useEffect, useState, type FormEvent } from "react";
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

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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

  // ---- 创建（POST，Contract §4.3）----

  function handleCreateSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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

  // ---- 编辑（PATCH，Contract §4.4）----

  function openEdit(user: UserRow) {
    setEditServerError(null);
    setEditNotice(null);
    setEditValues({ role: user.role, status: user.status });
    setEditFormKey((key) => key + 1);
    setMode({ kind: "edit", user });
  }

  function handleEditSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
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

  return (
    <div>
      <InfoState message="本地账号管理（仅 ADMIN）：创建账号并分配角色、变更角色、停用 / 启用账号。不开放自行注册；账号不物理删除（停用保留历史身份，既有审计不变）；无改密 / 重置入口（一期未实现）。停用会立即失效该账号全部现有会话，且在重新启用前无法登录；角色变更即时生效。" />

      {mode.kind === "list" && (
        <>
          <div className="table-toolbar">
            <h3>账号列表</h3>
            <Button
              type="button"
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

          <form className="filter-form" onSubmit={applyFilters}>
            <div className="form-field">
              <label htmlFor="user-filter-q">模糊搜索（username 子串，大小写不敏感）</label>
              <Input
                id="user-filter-q"
                type="text"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="form-field">
              <label htmlFor="user-filter-role">role</label>
              <Select
                id="user-filter-role"
                value={draft.role}
                onChange={(event) => setDraft({ ...draft, role: event.target.value as "" | Role })}
              >
                <option value="">全部（默认）</option>
                {ROLE_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-field">
              <label htmlFor="user-filter-status">status</label>
              <Select
                id="user-filter-status"
                value={draft.status}
                onChange={(event) =>
                  setDraft({ ...draft, status: event.target.value as "" | UserStatus })
                }
              >
                <option value="">全部（默认）</option>
                {STATUS_OPTIONS.map(({ value, label }) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="filter-actions">
              <Button type="submit">筛选</Button>
              <Button type="button" onClick={resetFilters}>
                重置
              </Button>
            </div>
          </form>

          {state.kind === "loading" && <LoadingState label="正在加载账号列表…" />}

          {state.kind === "error" && (
            <ErrorState
              message={`加载账号列表失败：${state.message}`}
              action={
                <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          {state.kind === "success" &&
            (state.data.items.length === 0 ? (
              <EmptyState description="没有符合条件的账号（当前过滤 / 分页下无数据，非错误）。" />
            ) : (
              <>
                <div className="table-wrap">
                  <DataTable className="data-table">
                    <thead>
                      <tr>
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
                        <th>version</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.items.map((user) => (
                        <tr key={user.id}>
                          <td className="mono">{user.username}</td>
                          <td className="mono">{user.role}</td>
                          <td>
                            <StatusTag tone={statusTone(user.status)}>{user.status}</StatusTag>
                          </td>
                          <td className="mono">{user.created_at}</td>
                          <td className="mono">{user.updated_at}</td>
                          <td>{user.version}</td>
                          <td>
                            <Button
                              type="button"
                              className="link-button"
                              onClick={() => openEdit(user)}
                            >
                              编辑
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
        </>
      )}

      {mode.kind === "create" && (
        <form
          className="account-form"
          onSubmit={handleCreateSubmit}
          noValidate
        >
          <div className="table-toolbar">
            <h3>新建账号</h3>
            <Button type="button" onClick={() => setMode({ kind: "list" })} disabled={submitting}>
              返回列表
            </Button>
          </div>

          <div className="form-field">
            <label htmlFor="user-create-username">username</label>
            <Input
              id="user-create-username"
              type="text"
              value={createValues.username}
              onChange={(event) =>
                setCreateValues({ ...createValues, username: event.target.value })
              }
              placeholder="3–64 位小写字母 / 数字 / . _ -"
            />
            {createFieldError("username") && (
              <p className="field-error">{createFieldError("username")}</p>
            )}
          </div>

          <div className="form-field">
            <label htmlFor="user-create-password">初始密码（8–128 字符；创建后不回显）</label>
            <Input
              id="user-create-password"
              type="password"
              value={createValues.password}
              onChange={(event) =>
                setCreateValues({ ...createValues, password: event.target.value })
              }
              autoComplete="new-password"
            />
            {createFieldError("password") && (
              <p className="field-error">{createFieldError("password")}</p>
            )}
          </div>

          <div className="form-field">
            <label htmlFor="user-create-role">role</label>
            <Select
              id="user-create-role"
              value={createValues.role}
              onChange={(event) =>
                setCreateValues({ ...createValues, role: event.target.value as Role })
              }
            >
              {ROLE_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            {createFieldError("role") && (
              <p className="field-error">{createFieldError("role")}</p>
            )}
          </div>

          {createServerError && (
            <ErrorState message={createServerError.message} />
          )}

          <div className="form-actions">
            <Button type="submit" disabled={submitting}>
              {submitting ? "正在创建…" : "创建账号"}
            </Button>
          </div>
        </form>
      )}

      {mode.kind === "edit" && (
        <form
          className="account-form"
          onSubmit={handleEditSubmit}
          key={editFormKey}
          noValidate
        >
          <div className="table-toolbar">
            <h3>
              编辑账号 — <span className="mono">{mode.user.username}</span>
            </h3>
            <Button type="button" onClick={() => setMode({ kind: "list" })} disabled={submitting}>
              返回列表
            </Button>
          </div>

          <dl className="detail-grid">
            <dt>username（不可修改）</dt>
            <dd className="mono">{mode.user.username}</dd>
            <dt>id</dt>
            <dd className="mono">{mode.user.id}</dd>
            <dt>version（乐观锁）</dt>
            <dd>{mode.user.version}</dd>
          </dl>

          <div className="form-field">
            <label htmlFor="user-edit-role">role</label>
            <Select
              id="user-edit-role"
              value={editValues.role}
              onChange={(event) =>
                setEditValues({ ...editValues, role: event.target.value as Role })
              }
            >
              {ROLE_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            {editServerError?.fields.role && (
              <p className="field-error">{editServerError.fields.role}</p>
            )}
          </div>

          <div className="form-field">
            <label htmlFor="user-edit-status">status</label>
            <Select
              id="user-edit-status"
              value={editValues.status}
              onChange={(event) =>
                setEditValues({ ...editValues, status: event.target.value as UserStatus })
              }
            >
              {STATUS_OPTIONS.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
            {editServerError?.fields.status && (
              <p className="field-error">{editServerError.fields.status}</p>
            )}
          </div>

          {editNotice && <ErrorState message={editNotice} />}

          {editServerError && (
            <ErrorState
              message={editServerError.message}
              action={
                editServerError.versionConflict ? (
                  <Button type="button" onClick={refreshAfterConflict} disabled={submitting}>
                    刷新最新数据
                  </Button>
                ) : undefined
              }
            />
          )}

          <div className="form-actions">
            <Button
              type="submit"
              danger={mode.user.status !== "DISABLED" && editValues.status === "DISABLED"}
              disabled={submitting}
            >
              {submitting ? "正在保存…" : "保存修改"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
