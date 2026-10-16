import { InputNumber, Modal } from "antd";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Input, Select, DataTable } from "./ui/controls";
import { ConfirmDialog } from "./ui/ConfirmDialog";
import {
  EmptyState,
  ErrorState,
  InfoState,
  LoadingState,
  WarningState,
} from "./ui/feedback";
import { ServerPagination as Pagination, StatusTag } from "./ui/surfaces";
import {
  apiKeyFormFieldFromPath,
  buildCreateApiKeyInput,
  emptyApiKeyFormValues,
  parseApiKeyFormValues,
  VALIDITY_DAYS_DEFAULT,
  VALIDITY_DAYS_MAX,
  VALIDITY_DAYS_MIN,
  type ApiKeyFormErrors,
  type ApiKeyFormValues,
} from "./apiKeyForm";
import {
  createApiKey,
  describeApiKeyActionError,
  describeApiKeyQueryError,
  listApiKeys,
  revokeApiKey,
  type ApiKeyActionError,
  type ApiKeyListResponse,
  type ApiKeyRow,
  type ApiKeySortField,
  type ApiKeyStatus,
  type CreatedApiKeyRow,
} from "../api/apiKeys";
import { describeUserActionError, listUsers, type UserRow } from "../api/users";

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: ApiKeyListResponse }
  | { kind: "error"; message: string };

/** 账号下拉数据状态（创建 / 过滤共用；分页上限 100，超出截断提示）。 */
type UsersOptionsState =
  | { kind: "loading" }
  | { kind: "success"; users: UserRow[]; total: number }
  | { kind: "error"; message: string };

/** 面板交互模式：列表 / 创建表单。 */
type PanelMode = { kind: "list" } | { kind: "create" };

/** 已应用的查询（过滤 + 分页 + 排序，Contract §3/§4.1）。 */
interface AppliedQuery {
  q: string;
  userId: string;
  status: "" | ApiKeyStatus;
  page: number;
  pageSize: number;
  sort: ApiKeySortField;
  order: "asc" | "desc";
}

const DEFAULT_QUERY: AppliedQuery = {
  q: "",
  userId: "",
  status: "",
  page: 1,
  pageSize: 20,
  sort: "created_at",
  order: "desc",
};

/** 可排序列（Contract §3：仅 created_at/expires_at/label，默认 created_at desc）。 */
const SORT_COLUMNS: { field: ApiKeySortField; label: string }[] = [
  { field: "label", label: "label" },
  { field: "created_at", label: "创建时间" },
  { field: "expires_at", label: "过期时间" },
];

const STATUS_OPTIONS: { value: ApiKeyStatus; label: string }[] = [
  { value: "ACTIVE", label: "ACTIVE（有效）" },
  { value: "REVOKED", label: "REVOKED（已吊销）" },
  { value: "EXPIRED", label: "EXPIRED（已过期）" },
];

/** API Key 状态 → 标签色调（服务端派生：REVOKED 优先于 EXPIRED，Contract §2）。 */
function apiKeyStatusTone(status: ApiKeyStatus): string {
  switch (status) {
    case "ACTIVE":
      return "success";
    case "EXPIRED":
      return "warning";
    case "REVOKED":
      return "error";
  }
}

/**
 * System 页 · API Key 管理面板（F017，Contract：docs/api/F017.md v1；§23.1；
 * DR-312）：
 * - 列表：GET /api/v1/api-keys（USER_ADMIN，仅 ADMIN）：user_id/status/q
 *   （label 大小写不敏感子串）过滤 + 分页 + 排序（§3 基线）；Loading /
 *   Empty / Error 显式区分，错误绝不伪装成空列表；
 * - 创建（§4.3）：绑定账号（存在且 ACTIVE）+ label（trim 非空、禁控制字符、
 *   ≤255 code point、不要求唯一）+ 有效期（整数 1..365，默认 90，无永不过
 *   期）；201 的 plaintext 仅在一次性弹窗展示，关闭即从内存清除，不写日志 /
 *   本地存储（§5）；列表 / 详情永不显示 key_hash 或明文；
 * - 吊销（§4.4）：确认对话框；成功后立即生效且不可恢复；重复吊销 → 409
 *   already_revoked、未知 id → 404 明确呈现，不静默重试；
 * - 本面板仅对具 USER_ADMIN 的角色渲染（SystemPage 门控；服务端仍鉴权，
 *   §1.2 权限矩阵：VIEWER/EDITOR 一律 403）。
 */
export default function ApiKeyManagementPanel() {
  // 账号下拉（过滤 / 创建共用）
  const [usersState, setUsersState] = useState<UsersOptionsState>({ kind: "loading" });
  const [usersReloadToken, setUsersReloadToken] = useState(0);

  // 列表查询
  const [draft, setDraft] = useState<{ q: string; userId: string; status: "" | ApiKeyStatus }>({
    q: "",
    userId: "",
    status: "",
  });
  const [query, setQuery] = useState<AppliedQuery>(DEFAULT_QUERY);
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  // 创建表单
  const [mode, setMode] = useState<PanelMode>({ kind: "list" });
  const [createValues, setCreateValues] = useState<ApiKeyFormValues>(emptyApiKeyFormValues());
  const [createErrors, setCreateErrors] = useState<ApiKeyFormErrors>({});
  const [createServerError, setCreateServerError] = useState<ApiKeyActionError | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // 一次性明文（仅存于内存，弹窗关闭即清除；不写日志 / 本地存储）
  const [created, setCreated] = useState<CreatedApiKeyRow | null>(null);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  // 吊销确认
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyRow | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [revokeError, setRevokeError] = useState<ApiKeyActionError | null>(null);

  // 账号下拉加载（USER_ADMIN；page_size 上限 100，超出截断提示）
  useEffect(() => {
    let cancelled = false;
    setUsersState({ kind: "loading" });
    listUsers({ page: 1, page_size: 100, sort: "username", order: "asc" })
      .then((data) => {
        if (!cancelled) {
          setUsersState({ kind: "success", users: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setUsersState({ kind: "error", message: describeUserActionError(error).message });
      });
    return () => {
      cancelled = true;
    };
  }, [usersReloadToken]);

  // 列表加载（过滤 + 分页 + 排序，服务端语义）
  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listApiKeys({
      user_id: query.userId === "" ? undefined : query.userId,
      status: query.status === "" ? undefined : query.status,
      q: query.q === "" ? undefined : query.q,
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
        // 401/403/422/500/网络层：显式呈现，可重试，不伪装成空列表
        setState({ kind: "error", message: describeApiKeyQueryError(error).message });
      });
    return () => {
      cancelled = true;
    };
  }, [query, reloadToken]);

  const filterUsers: UserRow[] = usersState.kind === "success" ? usersState.users : [];
  // 创建仅可为存在且 ACTIVE 的账号（Contract §4.3）；过滤下拉含全部账号
  const activeUsers = filterUsers.filter((user) => user.status === "ACTIVE");

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setQuery((current) => ({
      ...current,
      q: draft.q,
      userId: draft.userId,
      status: draft.status,
      page: 1,
    }));
  }

  function resetFilters() {
    setDraft({ q: "", userId: "", status: "" });
    setQuery((current) => ({ ...current, q: "", userId: "", status: "", page: 1 }));
  }

  /** 点击表头：同字段切换 asc/desc，新字段默认 asc；回到第 1 页。 */
  function toggleSort(field: ApiKeySortField) {
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
    const parsed = parseApiKeyFormValues(createValues);
    if (!parsed.ok) {
      // 本地镜像校验失败：不发请求（服务端同样 422）
      setCreateErrors(parsed.errors);
      return;
    }
    setCreateErrors({});
    setSubmitting(true);
    setCreateServerError(null);
    createApiKey(buildCreateApiKeyInput(parsed.fields))
      .then(({ api_key }) => {
        // 201：plaintext 仅此一次返回（§4.3/§5）——仅存于内存待一次性弹窗
        // 展示，关闭即清除；列表 / 详情 / 日志均不含明文（服务端只存哈希）
        setCreated(api_key);
        setCreateValues(emptyApiKeyFormValues());
        setMode({ kind: "list" });
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 422（user_id/label/validity_days）/ 403：明确呈现，不静默重试
        setCreateServerError(describeApiKeyActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 服务端 422 字段错误（user_id/label/validity_days → 表单键）优先于本地校验呈现。 */
  function createFieldError(key: keyof ApiKeyFormErrors): string | undefined {
    if (createServerError !== null) {
      for (const [path, message] of Object.entries(createServerError.fields)) {
        if (apiKeyFormFieldFromPath(path) === key) {
          return message;
        }
      }
    }
    return createErrors[key];
  }

  // ---- 一次性明文（Contract §5）----

  function closeCreatedPlaintext() {
    // 明文一次性纪律：关闭即从内存清除，此后任何界面 / 请求均无法再取回
    setCreated(null);
    setCopied(false);
    setCopyError(null);
  }

  async function copyPlaintextToClipboard() {
    if (created === null) {
      return;
    }
    try {
      await navigator.clipboard.writeText(created.plaintext);
      setCopied(true);
      setCopyError(null);
    } catch {
      setCopied(false);
      setCopyError("复制失败（浏览器剪贴板不可用）：请手动选中文本复制。");
    }
  }

  // ---- 吊销（POST /{id}/revoke，Contract §4.4）----

  function requestRevoke(row: ApiKeyRow) {
    setRevokeError(null);
    setRevokeTarget(row);
  }

  function closeRevoke() {
    if (revokeBusy) {
      return; // 提交中不可关闭，避免误触丢失确认上下文
    }
    setRevokeTarget(null);
    setRevokeError(null);
  }

  function confirmRevoke() {
    if (revokeTarget === null) {
      return;
    }
    const row = revokeTarget;
    setRevokeBusy(true);
    setRevokeError(null);
    revokeApiKey(row.id)
      .then(() => {
        // 200：吊销成功（立即生效、不可恢复、不提供重新启用）；重载列表
        setRevokeTarget(null);
        setRevokeError(null);
        setReloadToken((token) => token + 1);
      })
      .catch((error: unknown) => {
        // 409 already_revoked / 404 / 403：明确呈现，不静默重试
        setRevokeError(describeApiKeyActionError(error));
      })
      .finally(() => {
        setRevokeBusy(false);
      });
  }

  return (
    <div>
      <InfoState message="API Key 机器凭据管理（仅 ADMIN）：为启用（ACTIVE）的账号创建供外部自动化使用的 Bearer 凭据（请求头 Authorization: Bearer csm_ak_…），权限完全等于绑定账号的角色、不支持缩小范围。明文仅在创建成功时展示一次，此后任何列表 / 详情 / 日志均不可取回（系统只保存不可逆哈希），请立即妥善保存。吊销立即生效且不可恢复；有效期 1–365 天（默认 90 天，无永不过期）。" />

      {usersState.kind === "error" && (
        <ErrorState
          message={`加载账号列表失败（创建 API Key 需选择绑定账号，按账号过滤同样依赖）：${usersState.message}`}
          action={
            <Button type="button" onClick={() => setUsersReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}
      {usersState.kind === "success" && usersState.total > usersState.users.length && (
        <InfoState
          message={`账号总数 ${usersState.total} 个，下拉仅显示前 ${usersState.users.length} 个（按 username 排序；列表分页上限 100）。`}
        />
      )}

      {mode.kind === "list" && (
        <>
          <div className="table-toolbar">
            <h3>API Key 列表</h3>
            <Button
              type="button"
              onClick={() => {
                setCreateValues(emptyApiKeyFormValues());
                setCreateErrors({});
                setCreateServerError(null);
                setMode({ kind: "create" });
              }}
            >
              新建 API Key
            </Button>
          </div>

          <form className="filter-form" onSubmit={applyFilters}>
            <div className="form-field">
              <label htmlFor="api-key-filter-q">模糊搜索（label 子串，大小写不敏感）</label>
              <Input
                id="api-key-filter-q"
                type="text"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="大小写不敏感子串匹配"
              />
            </div>
            <div className="form-field">
              <label htmlFor="api-key-filter-user">绑定账号</label>
              <Select
                id="api-key-filter-user"
                value={draft.userId}
                onChange={(event) => setDraft({ ...draft, userId: event.target.value })}
                disabled={usersState.kind !== "success"}
              >
                <option value="">全部（默认）</option>
                {filterUsers.map((user) => (
                  <option key={user.id} value={user.id}>
                    {user.username}
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-field">
              <label htmlFor="api-key-filter-status">status</label>
              <Select
                id="api-key-filter-status"
                value={draft.status}
                onChange={(event) =>
                  setDraft({ ...draft, status: event.target.value as "" | ApiKeyStatus })
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

          {state.kind === "loading" && <LoadingState label="正在加载 API Key 列表…" />}

          {state.kind === "error" && (
            <ErrorState
              message={`加载 API Key 列表失败：${state.message}`}
              action={
                <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                  重试
                </Button>
              }
            />
          )}

          {state.kind === "success" &&
            (state.data.items.length === 0 ? (
              <EmptyState description="没有符合条件的 API Key（当前过滤 / 分页下无数据，非错误）。" />
            ) : (
              <>
                <div className="table-wrap">
                  <DataTable className="data-table" aria-label="API Key 列表">
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
                        <th>绑定账号</th>
                        <th>status</th>
                        <th>吊销时间</th>
                        <th>创建人</th>
                        <th>id</th>
                        <th>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {state.data.items.map((row) => (
                        <tr key={row.id}>
                          <td>{row.label}</td>
                          <td className="mono">{row.created_at}</td>
                          <td className="mono">{row.expires_at}</td>
                          <td className="mono">{row.username}</td>
                          <td>
                            <StatusTag tone={apiKeyStatusTone(row.status)}>{row.status}</StatusTag>
                          </td>
                          <td className="mono">
                            {row.revoked_at === null ? (
                              <span className="unset">—</span>
                            ) : (
                              row.revoked_at
                            )}
                          </td>
                          <td className="mono">{row.created_by_username}</td>
                          <td className="mono">{row.id}</td>
                          <td>
                            {row.status === "REVOKED" ? (
                              <span className="unset">—</span>
                            ) : (
                              <Button
                                type="button"
                                className="link-button"
                                danger
                                onClick={() => requestRevoke(row)}
                              >
                                吊销
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
        </>
      )}

      {mode.kind === "create" && (
        <form className="account-form" onSubmit={handleCreateSubmit} noValidate>
          <div className="table-toolbar">
            <h3>新建 API Key</h3>
            <Button type="button" onClick={() => setMode({ kind: "list" })} disabled={submitting}>
              返回列表
            </Button>
          </div>

          <div className="form-field">
            <label htmlFor="api-key-create-user">绑定账号（必选；须为存在且启用（ACTIVE）的账号）</label>
            <Select
              id="api-key-create-user"
              value={createValues.userId}
              onChange={(event) =>
                setCreateValues({ ...createValues, userId: event.target.value })
              }
              disabled={usersState.kind !== "success" || submitting}
            >
              <option value="">请选择账号</option>
              {activeUsers.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.username}（{user.role}）
                </option>
              ))}
            </Select>
            {usersState.kind === "loading" && (
              <p className="unset" role="status" style={{ margin: "0.25rem 0 0", fontSize: "0.85rem" }}>
                正在加载可选账号…
              </p>
            )}
            {usersState.kind === "error" && (
              <p className="field-error">账号列表加载失败：请先重试上方「重试」按钮。</p>
            )}
            {usersState.kind === "success" && activeUsers.length === 0 && (
              <p className="field-error">当前没有启用（ACTIVE）的账号可绑定。</p>
            )}
            {createFieldError("userId") && (
              <p className="field-error">{createFieldError("userId")}</p>
            )}
          </div>

          <div className="form-field">
            <label htmlFor="api-key-create-label">
              label（可读标签；trim 后非空、禁控制字符、≤255 字符；不要求唯一）
            </label>
            <Input
              id="api-key-create-label"
              type="text"
              value={createValues.label}
              onChange={(event) => setCreateValues({ ...createValues, label: event.target.value })}
              placeholder="如 ci-runner"
              disabled={submitting}
            />
            {createFieldError("label") && (
              <p className="field-error">{createFieldError("label")}</p>
            )}
          </div>

          <div className="form-field">
            <label htmlFor="api-key-create-validity">
              有效期（天；{VALIDITY_DAYS_MIN}–{VALIDITY_DAYS_MAX} 整数，默认{" "}
              {VALIDITY_DAYS_DEFAULT}；无永不过期）
            </label>
            <InputNumber
              id="api-key-create-validity"
              min={VALIDITY_DAYS_MIN}
              max={VALIDITY_DAYS_MAX}
              precision={0}
              step={1}
              value={createValues.validityDays}
              onChange={(value) =>
                setCreateValues({ ...createValues, validityDays: value })
              }
              disabled={submitting}
              style={{ width: 180 }}
            />
            {createFieldError("validityDays") && (
              <p className="field-error">{createFieldError("validityDays")}</p>
            )}
          </div>

          <WarningState message="创建成功后，凭据明文（csm_ak_…）仅在弹出窗口中展示一次；关闭窗口后无法再取回（系统只保存不可逆哈希）。请确保在关闭前复制并妥善保存。" />

          {createServerError && <ErrorState message={createServerError.message} />}

          <div className="form-actions">
            <Button type="submit" disabled={submitting}>
              {submitting ? "正在创建…" : "创建 API Key"}
            </Button>
          </div>
        </form>
      )}

      {/* 一次性明文弹窗（Contract §4.3/§5：仅创建 201 返回一次；关闭即清除） */}
      <Modal
        open={created !== null}
        title="API Key 创建成功 — 明文仅此一次展示"
        onCancel={closeCreatedPlaintext}
        maskClosable={false}
        keyboard={false}
        width={560}
        footer={
          <Button type="button" onClick={closeCreatedPlaintext}>
            我已妥善保存，关闭
          </Button>
        }
      >
        {created !== null && (
          <div className="detail-actions">
            <WarningState message="明文仅此一次展示：关闭后无法再取回（系统只保存不可逆哈希，列表 / 详情 / 日志均不含明文）。请立即复制并妥善保存。" />
            <dl className="detail-grid">
              <dt>label</dt>
              <dd>{created.label}</dd>
              <dt>绑定账号</dt>
              <dd className="mono">{created.username}</dd>
              <dt>过期时间</dt>
              <dd className="mono">{created.expires_at}</dd>
              <dt>使用方式</dt>
              <dd className="mono">Authorization: Bearer &lt;下方明文&gt;</dd>
            </dl>
            <div>
              <p className="json-block mono" style={{ userSelect: "all" }}>
                {created.plaintext}
              </p>
              <div className="form-actions">
                <Button type="button" onClick={copyPlaintextToClipboard}>
                  复制明文
                </Button>
                {copied && (
                  <span role="status" className="self-center">
                    已复制到剪贴板。
                  </span>
                )}
                {copyError && <span role="alert" className="field-error">{copyError}</span>}
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* 吊销确认对话框（Contract §4.4：立即生效且不可恢复；F020 起经由共享 ConfirmDialog，语义不变） */}
      <ConfirmDialog
        open={revokeTarget !== null}
        title="吊销 API Key"
        okText="确认吊销"
        danger
        confirmLoading={revokeBusy}
        onConfirm={confirmRevoke}
        onCancel={closeRevoke}
      >
        {revokeTarget !== null && (
          <div className="detail-actions">
            <WarningState
              message={
                <>
                  确认吊销 API Key「{revokeTarget.label}」（绑定账号{" "}
                  <span className="mono">{revokeTarget.username}</span>，当前状态{" "}
                  {revokeTarget.status}）？吊销立即生效且不可恢复（不提供重新启用）；
                  使用该 Key 的后续请求将立即返回 401。已过期但未吊销的 Key 也可以吊销。
                </>
              }
            />
            {revokeError && (
              <ErrorState
                message={revokeError.message}
                action={
                  revokeError.alreadyRevoked || revokeError.code === "NOT_FOUND" ? (
                    <Button
                      type="button"
                      onClick={() => {
                        setRevokeTarget(null);
                        setRevokeError(null);
                        setReloadToken((token) => token + 1);
                      }}
                    >
                      刷新列表
                    </Button>
                  ) : undefined
                }
              />
            )}
          </div>
        )}
      </ConfirmDialog>
    </div>
  );
}
