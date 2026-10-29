/**
 * 对象选择控件候选完整性的纯逻辑（F041；docs/features/F041/architecture.md
 * §1.1–§1.5，DR-F041-02/03/05/06/08）。
 *
 * 纯逻辑模块（无 JSX / React / antd 依赖，仅 `import type`）：
 * scripts/smoke-client.mjs 以 Node type stripping 直接加载本模块做机制级
 * 冒烟（同 ./authorizationCandidates.ts、./virtualMachine.ts；
 * CandidateSelect.tsx 含 JSX 无法被 Node 加载，故状态机、文案、请求参数
 * 构造、epoch 门控与选项合成全部落在本文件 —— 架构 §1.2 R2 硬约束）。
 *
 * 候选来源 = 既有列表端点 + 既有查询参数（F003 §4/§6.1、F004 §4/§6.1）：
 * - host 域：GET /api/v1/resources（q · cluster_id · type=BARE_METAL ·
 *   page=1 · page_size=100 · sort=hostname · order=asc）；
 * - cluster 域：GET /api/v1/clusters（q · page=1 · page_size=100 ·
 *   sort=code · order=asc）。
 * 不新增端点 / 参数 / 权限项 / 错误码；不设置 `deleted`（默认 exclude，§21）、
 * 不设置 `include` / `only`、不附加 `role` / `status` / `code` 等候选专属过滤
 * （N10）；`page_size` 不提高（上限 100，N4/A2）；`page` 恒为 1，无「加载更多」
 * 与循环翻页（A3）；`q` 仅首尾 trim，非空才携带，不改大小写与折叠（A12）。
 *
 * 不变量：
 * - 运行态 4 值（idle / loading / success / error）→ 视图投影 5 值
 *   （idle / loading / error / empty / ready）；四态 `kind` 互异、文案两两
 *   不等且非空；error 可重试、role=alert 且不伪装成空结果（A7/A8）；
 * - 每次响应**整体替换**（不 merge、不追加）并由 epoch 门控：陈旧响应原样
 *   返回当前状态（A4/FR-2）；
 * - 超限提示 = `success && total > items.length`，文案取响应 `total` 与
 *   `pageSize`（§23.2 下 `total` 天然只计授权对象，前端不请求全库，
 *   A6/A9/ON-11）；
 * - `pinned`（编辑态当前已选对象）在 loading / error / empty 态同样保留为
 *   唯一选项，且恰出现一次（A16/DR-F041-06）。
 */
import type { Cluster, ListClustersQuery } from "../api/clusters.ts";
import type { ListResourcesQuery, Resource } from "../api/resources.ts";

/** 候选单页上限（既有列表分页上限，不提高；N4/A2）。 */
export const CANDIDATE_PAGE_SIZE = 100;

/** 输入检索的防抖间隔（内联 setTimeout，不新增依赖，DR-F041-03）。 */
export const CANDIDATE_SEARCH_DEBOUNCE_MS = 300;

/** 候选域（决定端点、参数与文案名词）。 */
export type CandidateDomain = "host" | "cluster";

/** 候选项（`id` = 服务端 UUID；`label` = 展示文本）。 */
export interface CandidateItem {
  id: string;
  label: string;
}

/** 下拉选项（Ant Design `options` 形状：value/label 递增不变）。 */
export interface CandidateSelectOption {
  value: string;
  label: string;
}

/** 候选运行态（4 值；视图投影见 `candidateView`）。 */
export type CandidateSelectState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; items: CandidateItem[]; total: number; pageSize: number }
  | { kind: "error"; message: string };

/**
 * 候选请求参数（既有参数，序列化顺序即参数表顺序）。
 * `domain` 与 `query` 一一对应：host → `ListResourcesQuery`，
 * cluster → `ListClustersQuery`（调用方按 `domain` 选择既有 api 函数）。
 */
export type CandidateQuery =
  | { domain: "host"; query: ListResourcesQuery }
  | { domain: "cluster"; query: ListClustersQuery };

/** 单次请求的响应结果（成功 / 失败；不含 loading，由驱动方直接置位）。 */
export type CandidateOutcome =
  | { kind: "success"; items: CandidateItem[]; total: number; pageSize: number }
  | { kind: "error"; message: string };

/**
 * 构造候选查询（既有参数；`q` 仅首尾 trim 后非空才携带，DR-F041-08）。
 *
 * host 域要求 `clusterId` 非空（空串 = 空闲态，调用方不得发请求）；
 * `cluster_id` 为空时 `listResources` 也不会序列化该键，故不会退化为跨集群
 * 全量候选。
 */
export function buildCandidateQuery(
  domain: CandidateDomain,
  input: { clusterId: string; search: string },
): CandidateQuery {
  const trimmed = input.search.trim();
  const q = trimmed === "" ? {} : { q: trimmed };
  if (domain === "host") {
    return {
      domain: "host",
      query: {
        ...q,
        cluster_id: input.clusterId,
        type: "BARE_METAL",
        page: 1,
        page_size: CANDIDATE_PAGE_SIZE,
        sort: "hostname",
        order: "asc",
      },
    };
  }
  return {
    domain: "cluster",
    query: {
      ...q,
      page: 1,
      page_size: CANDIDATE_PAGE_SIZE,
      sort: "code",
      order: "asc",
    },
  };
}

/** 空闲态（host 域且未选择集群；cluster 域不可达，DR-F041-02）。 */
export function idleCandidateState(): CandidateSelectState {
  return { kind: "idle" };
}

/** 加载态（每次请求发出即置位；不保留上一轮候选）。 */
export function loadingCandidateState(): CandidateSelectState {
  return { kind: "loading" };
}

/**
 * 初始态：host 域未选择集群 → idle（不发请求）；其余 → loading
 * （cluster 域 idle 不可达，T10）。
 */
export function initialCandidateState(
  domain: CandidateDomain,
  clusterId: string,
): CandidateSelectState {
  return domain === "host" && clusterId === ""
    ? idleCandidateState()
    : loadingCandidateState();
}

/** 陈旧响应判定：请求 epoch 不是最新 epoch 即为陈旧（A4/ON-7）。 */
export function isStaleCandidateResponse(
  requestEpoch: number,
  latestEpoch: number,
): boolean {
  return requestEpoch !== latestEpoch;
}

/**
 * 应用一次响应：陈旧 → **原样返回当前状态**（丢弃旧结果，不 merge）；
 * 否则整体替换为成功 / 失败态（复制数组，避免与调用方状态共享）。
 */
export function applyCandidateResponse(
  current: CandidateSelectState,
  requestEpoch: number,
  latestEpoch: number,
  outcome: CandidateOutcome,
): CandidateSelectState {
  if (isStaleCandidateResponse(requestEpoch, latestEpoch)) {
    return current;
  }
  if (outcome.kind === "success") {
    return {
      kind: "success",
      items: [...outcome.items],
      total: outcome.total,
      pageSize: outcome.pageSize,
    };
  }
  return { kind: "error", message: outcome.message };
}

/** 视图投影类型（5 值；与运行态 4 值的对应见架构 §1.2 表）。 */
export type CandidateViewKind = "idle" | "loading" | "error" | "empty" | "ready";

/** 语义角色（映射既有 feedback 组件：note=InfoState、status=LoadingState、
 * alert=ErrorState、log=EmptyState、none=无提示）。 */
export type CandidateViewRole = "note" | "status" | "alert" | "log" | "none";

/** 状态提示投影（kind / role / text / canRetry）。 */
export interface CandidateView {
  kind: CandidateViewKind;
  role: CandidateViewRole;
  text: string;
  canRetry: boolean;
}

/** 业务名词（文案用；host → 宿主机、cluster → 集群）。 */
function candidateNoun(domain: CandidateDomain): string {
  return domain === "host" ? "宿主机" : "集群";
}

/** 排序字段展示名（超限提示用；与请求参数 `sort` 一致）。 */
function candidateSortLabel(domain: CandidateDomain): string {
  return domain === "host" ? "hostname" : "code";
}

/** 状态 → 视图投影（四态 kind 互异、文案两两不等；error 不伪装为空）。 */
export function candidateView(
  state: CandidateSelectState,
  domain: CandidateDomain,
): CandidateView {
  const noun = candidateNoun(domain);
  if (state.kind === "idle") {
    return {
      kind: "idle",
      role: "note",
      text:
        domain === "host"
          ? "请先选择所属集群，再选择宿主机候选。"
          : "请先选择所属集群，再选择集群候选。",
      canRetry: false,
    };
  }
  if (state.kind === "loading") {
    return {
      kind: "loading",
      role: "status",
      text: `正在加载${noun}候选…`,
      canRetry: false,
    };
  }
  if (state.kind === "error") {
    return {
      kind: "error",
      role: "alert",
      text: `加载${noun}候选失败：${state.message}。可重试；失败态不代表${noun}候选为空。`,
      canRetry: true,
    };
  }
  if (state.items.length === 0) {
    return {
      kind: "empty",
      role: "log",
      text:
        domain === "host"
          ? "该集群内未检索到未删除的 BARE_METAL；可更换检索词，或确认该集群已登记物理机后再创建虚拟机。"
          : "未检索到可选择的集群；可更换检索词，或先在 Clusters 中创建集群。",
      canRetry: false,
    };
  }
  return { kind: "ready", role: "none", text: "", canRetry: false };
}

/**
 * 超限提示（ON-11 / A9）：`truncated = success && total > items.length`；
 * 文案取响应 `total`（只计可见对象）与 `pageSize`（分页上限），不静默截断。
 */
export function candidateTruncation(
  state: CandidateSelectState,
  domain: CandidateDomain,
): { truncated: boolean; text: string | null } {
  if (state.kind !== "success" || state.total <= state.items.length) {
    return { truncated: false, text: null };
  }
  const noun = candidateNoun(domain);
  const sortLabel = candidateSortLabel(domain);
  return {
    truncated: true,
    text:
      `按 ${sortLabel} 排序共 ${state.total} 个${noun}，当前仅显示前 ${state.pageSize} 个` +
      `（列表分页上限 ${state.pageSize} 条）；更靠后的对象请用检索词查找。`,
  };
}

/**
 * 选项合成：候选项只来自最近一次响应（success）；`pinned`（编辑态当前已选
 * 对象）在 idle / loading / error / empty 态也保留为唯一选项，且与候选同 id
 * 时**恰出现一次**（用 pinned 的标注文本替换候选项 label，DR-F041-06/A16）。
 */
export function candidateOptions(
  state: CandidateSelectState,
  pinned?: CandidateItem | null,
): CandidateSelectOption[] {
  const base = state.kind === "success" ? state.items : [];
  const options: CandidateSelectOption[] = base.map((item) =>
    pinned && pinned.id === item.id
      ? { value: item.id, label: pinned.label }
      : { value: item.id, label: item.label },
  );
  if (pinned && !base.some((item) => item.id === pinned.id)) {
    options.unshift({ value: pinned.id, label: pinned.label });
  }
  return options;
}

/** 资源（Host）响应项 → 候选项（label = hostname，同集群内唯一）。 */
export function resourceCandidateItems(items: Resource[]): CandidateItem[] {
  return items.map((item) => ({ id: item.id, label: item.hostname }));
}

/** 集群响应项 → 候选项（label = `code — name`，与创建表单原展示一致）。 */
export function clusterCandidateItems(items: Cluster[]): CandidateItem[] {
  return items.map((item) => ({ id: item.id, label: `${item.code} — ${item.name}` }));
}
