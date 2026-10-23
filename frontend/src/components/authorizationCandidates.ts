/**
 * 集群授权授予模态的候选计算（F030；Contract：docs/api/F026.md v3
 * §3/§4/§5 不变，不新增端点 / 参数 / 字段 / 错误码；
 * docs/features/F030/architecture.md §7.2 与 DR-F030-06/DR-F030-07）。
 *
 * 纯逻辑模块（无 JSX / React / antd 依赖）：scripts/smoke-client.mjs 以
 * Node type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、
 * ./resourceIpAddresses.ts；ClusterAuthorizationPanel.tsx 含 JSX 无法被
 * Node 加载，故候选规则独立成文件）。
 *
 * 不变量（消除 F029-RV-05 的误导性中间态，不改变任何业务规则）：
 * - `active` 非 `success`（idle / loading / error）时**永不返回候选**：加载
 *   期间不把上一轮或空集当作「无授权」，失败时不把错误伪装为「无授权」；
 * - `clusters` 非 `success` 时同样不返回候选（列表错误不伪装为空结果）；
 * - 仅两者均 `success` 时过滤掉已授权 Cluster（服务端分页已按 ACTIVE 拉取）；
 * - `truncated` = 该账号 ACTIVE 授权加载被安全上限截断 **或** 集群列表
 *   `total > items.length`；呈现层必须显式提示，不静默截断（DR-F030-07）。
 * - 可提交要求候选为 `success` 且 `selectedClusterId` **仍存在于候选**：
 *   授权集合或搜索条件变化后，旧选中集群不再可提交（Architecture I-2），
 *   服务端唯一约束与 409 `already_granted` 始终是最终事实。
 */
import type { Cluster } from "../api/clusters.ts";

/** 集群列表加载状态（面板与候选计算共用；不扩张 API 契约）。 */
export type ClustersState =
  | { kind: "loading" }
  | { kind: "success"; clusters: Cluster[]; total: number }
  | { kind: "error"; message: string };

/**
 * 该账号已有 ACTIVE 授权的加载状态。
 *
 * - `success.loaded` = 已加载的 ACTIVE 授权行数，`total` = 服务端 `total`；
 * - `success.truncated` = 达到分页安全上限仍未覆盖 `total`（显式提示用）。
 */
export type ActiveGrantLoad =
  | { kind: "idle" }
  | { kind: "loading" }
  | {
      kind: "success";
      ids: ReadonlySet<string>;
      loaded: number;
      total: number;
      truncated: boolean;
    }
  | { kind: "error"; message: string };

/** 可授予候选集合的计算结果（`loading` / `error` 时不携带任何候选）。 */
export type GrantCandidates =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "success"; clusters: Cluster[]; truncated: boolean };

/**
 * 集群列表是否被截断（Contract：F003 列表分页；`total` 与 `items` 同 filters）。
 * 非 `success` 时不判定（无从比较，也不呈现列表）。
 */
export function clusterListTruncated(clusters: ClustersState): boolean {
  if (clusters.kind !== "success") return false;
  return clusters.total > clusters.clusters.length;
}

/**
 * 计算可授予候选：先门控 `active` 加载态，再门控 `clusters` 加载态，
 * 两者均 `success` 才过滤已授权 Cluster。
 */
export function computeGrantCandidates(
  active: ActiveGrantLoad,
  clusters: ClustersState,
): GrantCandidates {
  if (active.kind === "error") return { kind: "error", message: active.message };
  if (active.kind !== "success") return { kind: "loading" };
  if (clusters.kind === "error") return { kind: "error", message: clusters.message };
  if (clusters.kind !== "success") return { kind: "loading" };
  return {
    kind: "success",
    clusters: clusters.clusters.filter((cluster) => !active.ids.has(cluster.id)),
    truncated: active.truncated || clusterListTruncated(clusters),
  };
}

/**
 * 是否允许提交授予：`active` 与候选均 `success`、有选中集群、该集群**仍
 * 在候选中**且无提交进行中。非 `success` 恒 `false`（加载中/失败不可提交）。
 */
export function canSubmitGrant(
  active: ActiveGrantLoad,
  candidates: GrantCandidates,
  selectedClusterId: string,
  busy: boolean,
): boolean {
  if (busy) return false;
  if (selectedClusterId === "") return false;
  if (active.kind !== "success") return false;
  if (candidates.kind !== "success") return false;
  return candidates.clusters.some((cluster) => cluster.id === selectedClusterId);
}
