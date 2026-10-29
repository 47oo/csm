/**
 * 候选选择控件（F041；docs/features/F041/architecture.md §1.1/§1.3/§1.4）。
 *
 * 唯一承载「服务端检索 + 分页」的对象选择控件（方案 A / DR-F041-01）：
 * 共享 `./ui/controls.tsx` 的 `Select`（`showSearch` +
 * `optionFilterProp="label"`，仅在已加载选项内过滤）语义零 diff，本组件
 * 独立提供 `showSearch` + 受控 `searchValue` + `onSearch` +
 * `filterOption={false}`（服务端检索，禁 Ant 客户端二次过滤）。
 *
 * 数据流（§1.3）：
 * 输入 → 内联 `setTimeout(CANDIDATE_SEARCH_DEBOUNCE_MS)` → `committedSearch`；
 * `clusterId` / 域变更与 `committedSearch` 变化触发**唯一**的
 * `epoch = ++epochRef.current` + loading + 1 次请求 → `applyCandidateResponse`
 * （陈旧响应原样丢弃、否则整体替换，A4/ON-7）。打开下拉**不发请求**；重试是
 * 第三且最后一个触发源（`retryToken`，A8：不自动重试、失败不伪装为空）。
 *
 * 集群切换（ON-4/DR-F041-07）：host 域 `clusterId` 变化时清空检索词并调用
 * `onContextChange()`（调用方清空已选对象）；首次挂载 `""→实际值` 不清空。
 *
 * 状态机 / 文案 / 请求参数 / epoch 门控 / 选项合成全部在
 * `./candidateSelectModel.ts`（纯逻辑，无 JSX，可被 `smoke:client` 加载）。
 * 四态提示复用既有 `./ui/feedback`（InfoState / LoadingState / ErrorState /
 * EmptyState），并同时作为 Ant `notFoundContent`，保证四态在无候选时也可见。
 */
import { Select as AntSelect } from "antd";
import { useEffect, useRef, useState } from "react";
import { Button } from "./ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { displayError, isApiError } from "../api/client";
import { listClusters } from "../api/clusters";
import { listResources } from "../api/resources";
import {
  CANDIDATE_SEARCH_DEBOUNCE_MS,
  applyCandidateResponse,
  buildCandidateQuery,
  candidateOptions,
  candidateTruncation,
  candidateView,
  clusterCandidateItems,
  idleCandidateState,
  initialCandidateState,
  loadingCandidateState,
  resourceCandidateItems,
  type CandidateDomain,
  type CandidateItem,
  type CandidateOutcome,
  type CandidateSelectState,
  type CandidateView,
} from "./candidateSelectModel";

export interface CandidateSelectProps {
  /** 候选域（host = 同集群未删除 BARE_METAL；cluster = 未删除集群）。 */
  domain: CandidateDomain;
  /** host 域必填（空串 = 空闲态，不发请求）；cluster 域忽略。 */
  clusterId?: string;
  id?: string;
  /** 保留调用方的字段语义标识（Ant Select 无原生 name；落在包裹容器上）。 */
  name?: string;
  /** 受控值（空串 = 未选择）。 */
  value: string;
  onChange: (value: string) => void;
  /** 编辑态当前已选对象：loading / error / empty 态也保留，且恰出现一次。 */
  pinned?: CandidateItem | null;
  /** 仅提交中禁用（loading / error 不禁用，否则第 101 位之后仍不可达，DR-F041-05）。 */
  disabled?: boolean;
  placeholder?: string;
  /** 所属集群切换后的回调（调用方清空已选对象；首次挂载不触发）。 */
  onContextChange?: () => void;
  "aria-describedby"?: string;
}

/** 检索词按上下文（域 + 集群）归属：上下文变化即视为空，无需额外 effect 重置。 */
interface ScopedText {
  context: string;
  text: string;
}

function errorMessage(error: unknown): string {
  return isApiError(error)
    ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
    : displayError(error);
}

export default function CandidateSelect({
  domain,
  clusterId = "",
  id,
  name,
  value,
  onChange,
  pinned = null,
  disabled = false,
  placeholder,
  onContextChange,
  "aria-describedby": ariaDescribedBy,
}: CandidateSelectProps) {
  const contextKey = `${domain}:${clusterId}`;
  const [searchInput, setSearchInput] = useState<ScopedText>({ context: contextKey, text: "" });
  const [committedInput, setCommittedInput] = useState<ScopedText>({ context: contextKey, text: "" });
  const [retryToken, setRetryToken] = useState(0);
  const [state, setState] = useState<CandidateSelectState>(() =>
    initialCandidateState(domain, clusterId),
  );
  const epochRef = useRef(0);
  const prevClusterIdRef = useRef(clusterId);

  const search = searchInput.context === contextKey ? searchInput.text : "";
  const committedSearch = committedInput.context === contextKey ? committedInput.text : "";

  // 集群切换：清空已选对象（首次挂载 ""→实际值 不清空，DR-F041-07）。
  // 检索词由上面的上下文归属自然归零，不额外重置以免多打一次请求。
  useEffect(() => {
    if (prevClusterIdRef.current === clusterId) {
      return;
    }
    prevClusterIdRef.current = clusterId;
    onContextChange?.();
  }, [clusterId, onContextChange]);

  // 输入防抖：300ms 内只提交最后一次输入（内联 setTimeout，无新依赖）。
  useEffect(() => {
    if (search === committedSearch) {
      return;
    }
    const timer = setTimeout(() => {
      setCommittedInput({ context: contextKey, text: search });
    }, CANDIDATE_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [search, committedSearch, contextKey]);

  // 唯一请求触发点：域 / 集群 / 已提交检索词 / 显式重试。
  useEffect(() => {
    epochRef.current += 1;
    const epoch = epochRef.current;
    const idle = domain === "host" && clusterId === "";
    if (idle) {
      setState(idleCandidateState());
      return;
    }
    setState(loadingCandidateState());
    const candidateQuery = buildCandidateQuery(domain, { clusterId, search: committedSearch });
    const request: Promise<CandidateOutcome> =
      candidateQuery.domain === "host"
        ? listResources(candidateQuery.query).then(
            (data): CandidateOutcome => ({
              kind: "success",
              items: resourceCandidateItems(data.items),
              total: data.total,
              pageSize: data.page_size,
            }),
          )
        : listClusters(candidateQuery.query).then(
            (data): CandidateOutcome => ({
              kind: "success",
              items: clusterCandidateItems(data.items),
              total: data.total,
              pageSize: data.page_size,
            }),
          );
    request.then(
      (outcome) => {
        setState((current) => applyCandidateResponse(current, epoch, epochRef.current, outcome));
      },
      (error: unknown) => {
        setState((current) =>
          applyCandidateResponse(current, epoch, epochRef.current, {
            kind: "error",
            message: errorMessage(error),
          }),
        );
      },
    );
  }, [domain, clusterId, committedSearch, retryToken]);

  const view = candidateView(state, domain);
  const truncation = candidateTruncation(state, domain);
  const options = candidateOptions(state, pinned);

  const retryAction = (
    <Button type="button" onClick={() => setRetryToken((token) => token + 1)}>
      重试
    </Button>
  );

  /** 四态提示：复用既有 feedback 组件（kind → 组件一一对应）。 */
  function statusNode(current: CandidateView) {
    if (current.kind === "loading") {
      return <LoadingState label={current.text} />;
    }
    if (current.kind === "error") {
      return <ErrorState message={current.text} action={current.canRetry ? retryAction : undefined} />;
    }
    if (current.kind === "empty") {
      return <EmptyState description={current.text} />;
    }
    if (current.kind === "idle") {
      return <InfoState message={current.text} />;
    }
    return null;
  }

  const status = statusNode(view);

  return (
    <div className="flex flex-col gap-2" data-field-name={name}>
      <AntSelect
        aria-describedby={ariaDescribedBy}
        disabled={disabled}
        id={id}
        notFoundContent={status}
        onChange={(nextValue) => {
          onChange(nextValue === null || nextValue === undefined ? "" : String(nextValue));
        }}
        // 服务端检索：禁 Ant 客户端二次过滤（否则仅过滤已加载的 100 条）。
        options={options}
        placeholder={placeholder}
        popupMatchSelectWidth
        showSearch={{
          autoClearSearchValue: false,
          filterOption: false,
          onSearch: (text: string) => setSearchInput({ context: contextKey, text }),
          searchValue: search,
        }}
        style={{ width: "100%" }}
        value={value === "" ? undefined : value}
      />
      {status}
      {truncation.truncated && truncation.text !== null && <InfoState message={truncation.text} />}
    </div>
  );
}
