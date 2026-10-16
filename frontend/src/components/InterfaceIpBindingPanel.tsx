import { Modal } from "antd";
import { Button, Input, DataTable } from "./ui/controls";
import {
  EmptyState,
  ErrorState,
  InfoState,
  LoadingState,
  SuccessState,
  WarningState,
} from "./ui/feedback";
import { ServerPagination } from "./ui/surfaces";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { displayError, isApiError } from "../api/client";
import {
  describeIpAddressActionError,
  listIpAddresses,
  updateIpAddress,
  type IpAddress,
  type IpAddressListResponse,
} from "../api/ipAddresses";
import {
  addInterfaceIpCandidate,
  buildInterfaceIpBindingRequests,
  buildInterfaceIpCandidateQuery,
  emptyInterfaceIpSelection,
  interfaceIpCandidateFromIpAddress,
  interfaceIpTotalBoundary,
  removeInterfaceIpCandidate,
  submitInterfaceIpBindingRequests,
  summarizeInterfaceIpBindingOutcomes,
  type InterfaceIpBindingOutcome,
  type InterfaceIpBindingSummary,
  type InterfaceIpSelection,
} from "./interfaceIpSelection";

/** 候选列表加载状态（服务端分页，DR-332；错误绝不伪装成空列表）。 */
type CandidateListState =
  | { kind: "loading" }
  | { kind: "success"; data: IpAddressListResponse }
  | { kind: "error"; message: string };

interface InterfaceIpBindingPanelProps {
  /** 目标接口（未软删；入口门控 canOpenInterfaceIpBinding 见 InterfacesPanel）。 */
  iface: { id: string; name: string };
  /** 接口所属 Resource 的 Cluster（候选仅同 Cluster，§14/T54/AC1）。 */
  cluster: { id: string; code: string };
  onClose: () => void;
  /**
   * 提交完成（含部分成功）后通知父级；父级在有成功项时失效该接口的
   * 已绑定 IP 缓存并按需重取（DR-345）。
   */
  onCompleted: (ifaceId: string, summary: InterfaceIpBindingSummary) => void;
}

/** 单项失败原因文案（describeIpAddressActionError 归一；附 422 字段级明细）。 */
function interfaceIpBindingFailureText(outcome: InterfaceIpBindingOutcome): ReactNode {
  const described = describeIpAddressActionError(outcome.error);
  const fieldNotes = Object.entries(described.fields).map(
    ([field, message]) => `${field}：${message}`,
  );
  return (
    <span>
      {described.message}
      {fieldNotes.length > 0 && <span>（{fieldNotes.join("；")}）</span>}
    </span>
  );
}

/**
 * 接口侧选择并绑定 IP 的弹层（F019，复用 F010 Contract §4/§6.1/§6.5；
 * 由 InterfacesPanel 在 canOpenInterfaceIpBinding 门控下挂载）：
 * - 候选：GET /api/v1/ip-addresses?cluster_id=<所属集群>&bound=false&deleted=
 *   exclude&q=…&page=…（sort=address&order=asc，服务端分页）；跨 Cluster /
 *   已绑定 / 已删 IP 不出现（服务端过滤）；Loading / Empty / Error 显式区分，
 *   错误可重试、不伪装成空列表；
 * - 多选：以 IP id 为键跨页 / 跨搜索保留 {id,address,version}（DR-333）；
 *   total>items 显式提示分页截断；
 * - 提交：逐条串行 PATCH {interface,version}（单项失败不中止其余、不静默
 *   重试）；逐条呈现成功 / 失败及原因，部分成功不显示为整体成功（T55/AC3）；
 *   409 VERSION_CONFLICT 明确提示刷新重选（T58/AC6）；
 * - 本入口仅绑定已存在的未绑定 IP：不提供手动输入新地址、自动分配、
 *   接口侧解绑 / 转移（§13.4 明确不做）。
 */
export default function InterfaceIpBindingPanel({
  iface,
  cluster,
  onClose,
  onCompleted,
}: InterfaceIpBindingPanelProps) {
  const [listState, setListState] = useState<CandidateListState>({ kind: "loading" });
  const [draftQ, setDraftQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [reloadToken, setReloadToken] = useState(0);
  const [selection, setSelection] = useState<InterfaceIpSelection>(emptyInterfaceIpSelection);
  const [submitting, setSubmitting] = useState(false);
  const [outcomes, setOutcomes] = useState<InterfaceIpBindingOutcome[] | null>(null);

  // 候选加载（DR-332）：同 Cluster + 未绑定 + 未删；服务端分页 / address 升序。
  // 翻页 / 改搜索 / 提交成功后重取（DR-345）均经本 effect，已选集合不重置。
  useEffect(() => {
    let cancelled = false;
    setListState({ kind: "loading" });
    listIpAddresses(
      buildInterfaceIpCandidateQuery(cluster.id, { q: appliedQ, page, pageSize }),
    )
      .then((data) => {
        if (!cancelled) {
          setListState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setListState({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [cluster.id, appliedQ, page, pageSize, reloadToken]);

  // ---- 搜索（draft 应用制：点击“搜索”才发请求；回到第 1 页） ----

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setAppliedQ(draftQ.trim());
    setPage(1);
  }

  function resetSearch() {
    if (submitting) {
      return;
    }
    setDraftQ("");
    setAppliedQ("");
    setPage(1);
  }

  // ---- 多选（跨页 / 跨搜索保留，DR-333） ----

  function toggleCandidate(ip: IpAddress, checked: boolean) {
    if (submitting) {
      return;
    }
    setSelection((prev) =>
      checked
        ? addInterfaceIpCandidate(prev, interfaceIpCandidateFromIpAddress(ip))
        : removeInterfaceIpCandidate(prev, ip.id),
    );
  }

  function gotoPage(nextPage: number) {
    if (!submitting) {
      setPage(nextPage);
    }
  }

  function changePageSize(nextPageSize: number) {
    if (!submitting) {
      setPageSize(nextPageSize);
      setPage(1);
    }
  }

  // ---- 逐条提交（DR-334/T55：串行、单项失败不中止、不静默重试） ----

  async function handleSubmit() {
    if (submitting || selection.size === 0) {
      return;
    }
    const requests = buildInterfaceIpBindingRequests(selection, iface.id);
    setSubmitting(true);
    setOutcomes(null);
    const results = await submitInterfaceIpBindingRequests(requests, (request) =>
      updateIpAddress(request.id, { version: request.version, interface: request.interface }),
    );
    const summary = summarizeInterfaceIpBindingOutcomes(results);
    setOutcomes(results);
    setSelection(emptyInterfaceIpSelection());
    setSubmitting(false);
    if (summary.succeeded > 0) {
      // 绑定成功后重取当前候选页（DR-345）：已绑定 IP 不再出现在候选中
      setReloadToken((token) => token + 1);
    }
    onCompleted(iface.id, summary);
  }

  const summary = outcomes === null ? null : summarizeInterfaceIpBindingOutcomes(outcomes);

  return (
    <Modal
      open
      width={760}
      title={
        <>
          绑定 IP — <span className="mono">{iface.name}</span>
          <span className="unset">（集群 {cluster.code}）</span>
        </>
      }
      okText={submitting ? "正在逐条绑定…" : `提交绑定（已选 ${selection.size}）`}
      okButtonProps={{ disabled: submitting || selection.size === 0 }}
      confirmLoading={submitting}
      cancelText="关闭"
      onCancel={() => {
        if (!submitting) {
          onClose();
        }
      }}
      onOk={handleSubmit}
      maskClosable={!submitting}
      keyboard={!submitting}
      cancelButtonProps={{ disabled: submitting }}
    >
      <div className="detail-actions">
        <InfoState message="候选为与本接口所属资源同集群、未绑定任何接口且未删除的 IP 地址（cluster_id + bound=false + deleted=exclude，服务端过滤）；本入口仅绑定已有 IP，不提供手动输入新地址、自动分配或解绑 / 转移。" />

        {submitting && (
          <LoadingState label="正在逐条提交绑定（按地址升序串行，单项失败不中止其余，不自动重试）…" />
        )}

        {!submitting && summary !== null && (
          <>
            {summary.allSucceeded ? (
              <SuccessState
                message={`已成功绑定 ${summary.succeeded} 个 IP 地址到接口 ${iface.name}（每次成功绑定各产生一条 UPDATE 审计；不改变地址、网络与占用）。`}
              />
            ) : summary.succeeded > 0 ? (
              <WarningState
                message={`部分成功：${summary.succeeded} 个绑定成功、${summary.failed} 个失败（逐条结果见下方列表；失败项不会自动重试，请处理后重新选择）。`}
              />
            ) : (
              <ErrorState message={`绑定失败：所选 ${summary.total} 个 IP 全部失败（逐条原因见下方列表；不会自动重试）。`} />
            )}
          </>
        )}

        <form className="filter-form" onSubmit={applySearch}>
          <div className="form-field">
            <label htmlFor="interface-ip-binding-q">搜索候选（address 子串，大小写不敏感）</label>
            <Input
              id="interface-ip-binding-q"
              type="text"
              value={draftQ}
              onChange={(event) => setDraftQ(event.target.value)}
              disabled={submitting}
              placeholder="如 10.10.1；留空 = 全部候选；搜索不会清空已选"
            />
          </div>
          <div className="filter-actions">
            <Button type="submit" disabled={submitting}>
              搜索
            </Button>
            <Button type="button" onClick={resetSearch} disabled={submitting}>
              重置
            </Button>
          </div>
        </form>

        {listState.kind === "loading" && <LoadingState label="正在加载候选 IP…" />}

        {listState.kind === "error" && (
          <ErrorState
            message={`加载候选失败：${listState.message}`}
            action={
              <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
                重试
              </Button>
            }
          />
        )}

        {listState.kind === "success" &&
          (listState.data.items.length === 0 ? (
            <EmptyState
              description={
                appliedQ === ""
                  ? "该集群当前没有未绑定且未删除的 IP 地址（非错误；可先在 IP Addresses 页面分配）。"
                  : `没有匹配「${appliedQ}」的可绑定候选（同集群、未绑定、未删除口径）。`
              }
            />
          ) : (
            <>
              {interfaceIpTotalBoundary(listState.data.total, listState.data.items.length) ===
                "truncated" && (
                <InfoState
                  message={`候选共 ${listState.data.total} 个，当前页显示 ${listState.data.items.length} 个（服务端分页，按 address 升序）；翻页或搜索不会清空已选（已选 ${selection.size} 个跨页保留）。`}
                />
              )}
              <div className="table-wrap">
                <DataTable className="data-table" aria-label="可绑定 IP 候选列表">
                  <thead>
                    <tr>
                      <th>选择</th>
                      <th>address</th>
                      <th>network</th>
                      <th>ip_pool（来源）</th>
                      <th>description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listState.data.items.map((ip) => (
                      <tr key={ip.id}>
                        <td>
                          <Input
                            type="checkbox"
                            checked={selection.has(ip.id)}
                            onChange={(event) => toggleCandidate(ip, event.target.checked)}
                            disabled={submitting}
                            aria-label={`选择 ${ip.address}`}
                          />
                        </td>
                        <td className="mono">{ip.address}</td>
                        <td>
                          <span className="mono">{ip.network.name}</span>
                          <span className="unset">（{ip.network.cidr}）</span>
                        </td>
                        <td>
                          {ip.ip_pool !== null ? (
                            ip.ip_pool.name
                          ) : (
                            <span className="unset">池外（手动）</span>
                          )}
                        </td>
                        <td>{ip.description ?? <span className="unset">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              </div>
              <ServerPagination
                page={listState.data.page}
                pageSize={listState.data.page_size}
                total={listState.data.total}
                appliedPageSize={pageSize}
                onGotoPage={gotoPage}
                onChangePageSize={changePageSize}
              />
            </>
          ))}

        {!submitting && outcomes !== null && (
          <div>
            <h4 className="detail-section-title">绑定结果（逐条）</h4>
            <div className="table-wrap">
              <DataTable className="data-table" aria-label="绑定结果列表">
                <thead>
                  <tr>
                    <th>address</th>
                    <th>结果</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {outcomes.map((outcome) => (
                    <tr key={outcome.id}>
                      <td className="mono">{outcome.address}</td>
                      <td>{outcome.ok ? "成功" : "失败"}</td>
                      <td>
                        {outcome.ok ? (
                          <span className="unset">—</span>
                        ) : (
                          interfaceIpBindingFailureText(outcome)
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </div>
            <InfoState message="失败项不会自动重试；如提示版本冲突（VERSION_CONFLICT），说明该 IP 已被他人修改或并发绑定（后到者冲突），请重新选择候选后再提交。" />
          </div>
        )}
      </div>
    </Modal>
  );
}
