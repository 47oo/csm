import { Modal } from "antd";
import { useEffect, useState, type FormEvent } from "react";
import { Button, Input, Select, DataTable } from "./ui/controls";
import { ConfirmDialog } from "./ui/ConfirmDialog";
import {
  EmptyState,
  ErrorState,
  InfoState,
  LoadingState,
  SuccessState,
} from "./ui/feedback";
import { ServerPagination as Pagination, StatusTag } from "./ui/surfaces";
import {
  canSubmitGrant,
  clusterListTruncated,
  computeGrantCandidates,
  type ActiveGrantLoad,
  type ClustersState,
} from "./authorizationCandidates";
import { listClusters } from "../api/clusters";
import { listUsers, type UserRow } from "../api/users";
import {
  describeClusterAuthorizationError,
  grantClusterAuthorization,
  listClusterAuthorizations,
  revokeClusterAuthorization,
  type AuthorizationStatus,
  type ClusterAuthorizationListResponse,
  type ClusterAuthorizationRow,
} from "../api/clusterAuthorizations";

type ListState =
  | { kind: "loading" }
  | { kind: "success"; data: ClusterAuthorizationListResponse }
  | { kind: "error"; message: string };

type UsersState =
  | { kind: "loading" }
  | { kind: "success"; users: UserRow[]; total: number }
  | { kind: "error"; message: string };

const PAGE_SIZE = 20;
/** 该账号 ACTIVE 授权分页（docs/api/F026.md v3 §3 已批准 page_size 上限 100）。 */
const ACTIVE_GRANT_PAGE_SIZE = 100;
/** 分页安全上限：达到后不再继续请求，改以显式 truncated 提示（DR-F030-07）。 */
const ACTIVE_GRANT_MAX_PAGES = 20;

/**
 * System 页 · 集群授权管理（F026，Contract：docs/api/F026.md v3）。
 *
 * 仅 USER_ADMIN 角色由 SystemPage 渲染；服务端仍强制鉴权。左侧选择账号，
 * 右侧查看/授予/撤销该账号的 Cluster 授权。撤销是历史保留的状态变更，使用
 * ConfirmDialog 二次确认，不提供 DELETE。
 *
 * F030（docs/features/F030/architecture.md §7.2 / DR-F030-06）只修正交互，
 * 不新增端点 / 参数 / 业务规则：
 * - 候选由 ./authorizationCandidates 纯逻辑计算——该账号 ACTIVE 授权加载完成前
 *   不呈现任何候选且不可提交；加载失败显式报错并可按「重试」，不置空集冒充
 *   「无授权」；
 * - 该账号授权或集群列表被截断时显式提示，不静默截断（DR-F030-07）；服务端
 *   唯一约束与 409 `already_granted` 始终是最终事实；
 * - 409 `already_granted` 保持模态打开、内联呈现并重新加载候选（不当作成功）；
 *   409 `already_revoked` 仍按 Contract D-5 关闭 + 提示 + 刷新。
 */
export default function ClusterAuthorizationPanel() {
  const [usersState, setUsersState] = useState<UsersState>({ kind: "loading" });
  const [userQuery, setUserQuery] = useState("");
  const [selectedUser, setSelectedUser] = useState<UserRow | null>(null);

  const [statusFilter, setStatusFilter] = useState<"" | AuthorizationStatus>("");
  const [state, setState] = useState<ListState>({ kind: "loading" });
  const [page, setPage] = useState(1);
  const [reloadToken, setReloadToken] = useState(0);

  const [grantOpen, setGrantOpen] = useState(false);
  // 已授权集合的加载态：非 success 时永不呈现候选（F030 P5 / 架构 §7.2）。
  const [activeGrants, setActiveGrants] = useState<ActiveGrantLoad>({ kind: "idle" });
  const [grantReloadToken, setGrantReloadToken] = useState(0);
  const [clustersState, setClustersState] = useState<ClustersState>({ kind: "loading" });
  const [clustersReloadToken, setClustersReloadToken] = useState(0);
  const [clusterQuery, setClusterQuery] = useState("");
  const [selectedClusterId, setSelectedClusterId] = useState("");
  const [grantBusy, setGrantBusy] = useState(false);
  const [grantError, setGrantError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [revokeTarget, setRevokeTarget] = useState<ClusterAuthorizationRow | null>(null);
  const [revokeBusy, setRevokeBusy] = useState(false);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  // Load users (ADMIN manages authorization for any non-ADMIN account).
  useEffect(() => {
    let cancelled = false;
    setUsersState({ kind: "loading" });
    listUsers({ q: userQuery || undefined, page: 1, page_size: 100, sort: "username", order: "asc" })
      .then((data) => {
        if (!cancelled) setUsersState({ kind: "success", users: data.items, total: data.total });
      })
      .catch((error: unknown) => {
        if (!cancelled) setUsersState({ kind: "error", message: describeClusterAuthorizationError(error).message });
      });
    return () => {
      cancelled = true;
    };
  }, [userQuery]);

  // Load authorizations for the selected user.
  useEffect(() => {
    if (selectedUser === null) return;
    let cancelled = false;
    setState({ kind: "loading" });
    listClusterAuthorizations(selectedUser.id, {
      status: statusFilter === "" ? undefined : statusFilter,
      page,
      page_size: PAGE_SIZE,
      sort: "granted_at",
      order: "desc",
    })
      .then((data) => {
        if (!cancelled) setState({ kind: "success", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ kind: "error", message: describeClusterAuthorizationError(error).message });
      });
    return () => {
      cancelled = true;
    };
  }, [selectedUser, statusFilter, page, reloadToken]);

  // Load cluster candidates when the grant modal opens or search changes.
  useEffect(() => {
    if (!grantOpen) return;
    let cancelled = false;
    setClustersState({ kind: "loading" });
    listClusters({ q: clusterQuery || undefined, deleted: "exclude", page: 1, page_size: 50, sort: "code", order: "asc" })
      .then((data) => {
        if (!cancelled) setClustersState({ kind: "success", clusters: data.items, total: data.total });
      })
      .catch((error: unknown) => {
        if (!cancelled) setClustersState({ kind: "error", message: describeClusterAuthorizationError(error).message });
      });
    return () => {
      cancelled = true;
    };
  }, [grantOpen, clusterQuery, clustersReloadToken]);

  // Load the account's existing ACTIVE authorizations (gate for candidate rendering).
  useEffect(() => {
    if (!grantOpen || selectedUser === null) {
      setActiveGrants({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setActiveGrants({ kind: "loading" });
    loadActiveGrants(selectedUser.id)
      .then((load) => {
        if (!cancelled) setActiveGrants(load);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setActiveGrants({ kind: "error", message: describeClusterAuthorizationError(error).message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [grantOpen, selectedUser, grantReloadToken]);

  async function loadActiveGrants(userId: string): Promise<ActiveGrantLoad> {
    const ids = new Set<string>();
    let total = 0;
    let page = 1;
    for (;;) {
      const data = await listClusterAuthorizations(userId, {
        status: "ACTIVE",
        page,
        page_size: ACTIVE_GRANT_PAGE_SIZE,
      });
      total = data.total;
      for (const item of data.items) {
        ids.add(item.cluster.id);
      }
      if (data.items.length === 0) break;
      if (ids.size >= total) break;
      if (page >= ACTIVE_GRANT_MAX_PAGES) break;
      page += 1;
    }
    return { kind: "success", ids, loaded: ids.size, total, truncated: ids.size < total };
  }

  const candidates = computeGrantCandidates(activeGrants, clustersState);
  const candidateIds = candidates.kind === "success" ? candidates.clusters.map((cluster) => cluster.id) : [];
  // 旧选中集群不在新候选中时，选择框不呈现该脏值且不可提交（规则见 authorizationCandidates.ts::canSubmitGrant；F030 architecture §17.1）。
  const visibleSelectedClusterId =
    selectedClusterId !== "" && candidateIds.includes(selectedClusterId) ? selectedClusterId : "";
  const grantSubmittable = canSubmitGrant(activeGrants, candidates, selectedClusterId, grantBusy);

  function openGrant() {
    if (selectedUser === null) return;
    setSelectedClusterId("");
    setClusterQuery("");
    setGrantError(null);
    // 先置加载态：模态打开的第一帧就不呈现旧/空候选集合。
    setActiveGrants({ kind: "loading" });
    setGrantOpen(true);
  }

  async function submitGrant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (selectedUser === null) return;
    if (selectedClusterId === "") {
      setGrantError("请选择目标集群。");
      return;
    }
    if (!grantSubmittable) {
      setGrantError("候选尚未加载完成或所选集群已不在候选中，请重新选择。");
      return;
    }
    setGrantBusy(true);
    setGrantError(null);
    try {
      await grantClusterAuthorization(selectedUser.id, selectedClusterId);
      setGrantOpen(false);
      setNotice("集群授权已授予。");
      setReloadToken((value) => value + 1);
    } catch (error: unknown) {
      const described = describeClusterAuthorizationError(error);
      setGrantError(described.message);
      if (described.alreadyGranted) {
        // 409 already_granted 不是成功：保持模态打开、内联呈现，并重新加载候选集合。
        setSelectedClusterId("");
        setGrantReloadToken((value) => value + 1);
      }
    } finally {
      setGrantBusy(false);
    }
  }

  async function confirmRevoke() {
    if (revokeTarget === null) return;
    setRevokeBusy(true);
    setRevokeError(null);
    try {
      await revokeClusterAuthorization(revokeTarget.id);
      setRevokeTarget(null);
      setNotice("集群授权已撤销；历史记录保留。");
      setReloadToken((value) => value + 1);
    } catch (error: unknown) {
      const described = describeClusterAuthorizationError(error);
      if (described.alreadyRevoked) {
        setRevokeTarget(null);
        setNotice("该授权已被撤销（可能已被他人操作），列表已刷新。");
        setReloadToken((value) => value + 1);
      } else {
        setRevokeError(described.message);
      }
    } finally {
      setRevokeBusy(false);
    }
  }

  return (
    <section className="authorization-panel" aria-label="集群授权管理">
      <InfoState
        message={
          <>
            ADMIN 不受集群范围限制，不建立授权行；ADMIN 降级为 VIEWER / EDITOR 后立即按既有授权解析（可能为空）。
            本页管理授权事实；非 ADMIN 的可见范围按已授权 Cluster 逐请求生效。
          </>
        }
      />
      {notice && <SuccessState message={notice} />}

      <div className="authorization-layout" style={{ display: "grid", gridTemplateColumns: "minmax(260px, 1fr) 2fr", gap: 16 }}>
        <section aria-label="账号列表">
          <h3>账号</h3>
          <form onSubmit={(event) => { event.preventDefault(); }}>
            <Input
              aria-label="搜索账号"
              placeholder="搜索 username"
              value={userQuery}
              onChange={(event) => setUserQuery(event.target.value)}
            />
          </form>
          {usersState.kind === "loading" && <LoadingState />}
          {usersState.kind === "error" && <ErrorState message={usersState.message} />}
          {usersState.kind === "success" && usersState.users.length === 0 && (
            <EmptyState description="没有匹配的账号" />
          )}
          {usersState.kind === "success" && usersState.users.length > 0 && (
            <ul className="authorization-user-list" style={{ listStyle: "none", padding: 0 }}>
              {usersState.users.map((user) => (
                <li key={user.id}>
                  <Button
                    type="button"
                    variant={selectedUser?.id === user.id ? "primary" : "default"}
                    onClick={() => {
                      setSelectedUser(user);
                      setPage(1);
                      setStatusFilter("");
                      setNotice(null);
                    }}
                  >
                    {user.username} · {user.role} · {user.status}
                  </Button>
                </li>
              ))}
            </ul>
          )}
          {usersState.kind === "success" && usersState.total > usersState.users.length && (
            <p>仅显示前 {usersState.users.length} 个账号，请用搜索缩小范围。</p>
          )}
        </section>

        <section aria-label="授权列表">
          <h3>集群授权</h3>
          {selectedUser === null && <EmptyState description="请选择左侧账号以查看或管理其集群授权" />}
          {selectedUser !== null && (
            <>
              <p>
                目标账号：<strong>{selectedUser.username}</strong>（{selectedUser.role} / {selectedUser.status}）
              </p>
              {selectedUser.role === "ADMIN" ? (
                <InfoState message="ADMIN 不受集群范围限制，不建立授权行；无需也无法为其授予集群。" />
              ) : (
                <>
                  <div className="toolbar">
                    <Select
                      aria-label="授权状态过滤"
                      value={statusFilter}
                      onChange={(event) => {
                        setStatusFilter(event.target.value as "" | AuthorizationStatus);
                        setPage(1);
                      }}
                    >
                      <option value="">全部状态</option>
                      <option value="ACTIVE">ACTIVE（有效）</option>
                      <option value="REVOKED">REVOKED（已撤销）</option>
                    </Select>
                    <Button type="button" variant="primary" onClick={openGrant}>
                      授予集群访问
                    </Button>
                  </div>

                  {state.kind === "loading" && <LoadingState />}
                  {state.kind === "error" && <ErrorState message={state.message} />}
                  {state.kind === "success" && state.data.items.length === 0 && (
                    <EmptyState description="该账号暂无集群授权（非 ADMIN 未授权时为默认拒绝，不会回退为全部可见）" />
                  )}
                  {state.kind === "success" && state.data.items.length > 0 && (
                    <>
                      <DataTable aria-label="集群授权列表">
                        <thead>
                          <tr>
                            <th>Cluster</th>
                            <th>授权状态</th>
                            <th>生效</th>
                            <th>授予</th>
                            <th>撤销</th>
                            <th>操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {state.data.items.map((row) => (
                            <tr key={row.id}>
                              <td>
                                {row.cluster.code} — {row.cluster.name}（{row.cluster.status}）
                                {row.cluster.deleted_at !== null && " · 集群已删除"}
                              </td>
                              <td><StatusTag tone={row.status === "ACTIVE" ? "success" : "error"}>{row.status}</StatusTag></td>
                              <td>{row.effective ? "是" : "否"}</td>
                              <td>
                                {row.granted_at}
                                <br />
                                {row.granted_by_username ?? "系统回填"}
                              </td>
                              <td>
                                {row.revoked_at ?? "—"}
                                <br />
                                {row.revoked_by_username ?? "—"}
                              </td>
                              <td>
                                {row.status === "ACTIVE" ? (
                                  <Button
                                    type="button"
                                    danger
                                    onClick={() => {
                                      setRevokeTarget(row);
                                      setRevokeError(null);
                                    }}
                                  >
                                    撤销
                                  </Button>
                                ) : (
                                  <span className="muted">已撤销</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </DataTable>
                      <Pagination
                        appliedPageSize={PAGE_SIZE}
                        onChangePageSize={() => setPage(1)}
                        onGotoPage={setPage}
                        page={page}
                        pageSize={PAGE_SIZE}
                        total={state.data.total}
                      />
                    </>
                  )}
                </>
              )}
            </>
          )}
        </section>
      </div>

      <Modal
        open={grantOpen}
        title="授予集群访问"
        onCancel={() => setGrantOpen(false)}
        footer={null}
        width={560}
        maskClosable={!grantBusy}
        keyboard={!grantBusy}
      >
        <form onSubmit={submitGrant}>
          <p>
            目标账号：<strong>{selectedUser?.username}</strong>
          </p>
          <Input
            aria-label="搜索集群"
            placeholder="搜索 Cluster code / name"
            value={clusterQuery}
            onChange={(event) => setClusterQuery(event.target.value)}
          />
          {activeGrants.kind === "success" && activeGrants.truncated && (
            <InfoState
              message={
                <>
                  该账号有效授权数量为 {activeGrants.total}（已加载 {activeGrants.loaded}）。为限制请求量，候选可能仍包含
                  已授权集群；重复提交会被服务端以 409 already_granted 拒绝，不会重复建立授权。
                </>
              }
            />
          )}
          {activeGrants.kind === "error" ? (
            <ErrorState
              message={`无法加载该账号已有的有效授权：${activeGrants.message}（加载完成前不可提交）`}
              action={
                <Button
                  type="button"
                  disabled={grantBusy}
                  onClick={() => setGrantReloadToken((value) => value + 1)}
                >
                  重试
                </Button>
              }
            />
          ) : candidates.kind === "error" ? (
            <ErrorState
              message={`无法加载集群列表：${candidates.message}`}
              action={
                <Button
                  type="button"
                  disabled={grantBusy}
                  onClick={() => setClustersReloadToken((value) => value + 1)}
                >
                  重试
                </Button>
              }
            />
          ) : candidates.kind === "loading" ? (
            <LoadingState
              label={
                activeGrants.kind === "success"
                  ? "正在加载集群列表…"
                  : "正在加载该账号已有的有效授权…（加载完成前不可提交）"
              }
            />
          ) : candidates.clusters.length === 0 ? (
            <EmptyState description="没有可授予的集群（已有效授权的集群不会重复出现）" />
          ) : (
            <>
              <Select
                aria-label="选择集群"
                value={visibleSelectedClusterId}
                onChange={(event) => setSelectedClusterId(event.target.value)}
              >
                <option value="">请选择集群</option>
                {candidates.clusters.map((cluster) => (
                  <option key={cluster.id} value={cluster.id}>
                    {cluster.code} — {cluster.name}（{cluster.status}）
                  </option>
                ))}
              </Select>
              {clustersState.kind === "success" && clusterListTruncated(clustersState) && (
                <p>仅显示前 {clustersState.clusters.length} 个匹配集群，请用搜索缩小范围。</p>
              )}
            </>
          )}
          {grantError && <ErrorState message={grantError} />}
          <div className="toolbar">
            <Button type="button" onClick={() => setGrantOpen(false)} disabled={grantBusy}>
              取消
            </Button>
            <Button type="submit" variant="primary" disabled={!grantSubmittable}>
              {grantBusy ? "提交中…" : "确认授予"}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={revokeTarget !== null}
        title="撤销集群访问"
        danger
        okText="确认撤销"
        confirmLoading={revokeBusy}
        onCancel={() => {
          if (!revokeBusy) {
            setRevokeTarget(null);
            setRevokeError(null);
          }
        }}
        onConfirm={() => {
          void confirmRevoke();
        }}
      >
        <p>
          目标账号：<strong>{revokeTarget?.user.username}</strong>
          <br />
          Cluster：<strong>{revokeTarget?.cluster.code} — {revokeTarget?.cluster.name}</strong>
        </p>
        <p>撤销后该账号立即失去该集群的访问范围；历史记录保留、不物理删除。</p>
        {revokeError && <ErrorState message={revokeError} />}
      </ConfirmDialog>
    </section>
  );
}
