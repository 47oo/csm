import { Statistic } from "antd";
import { Button, DataTable } from "./ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { ServerPagination, StatusTag, SurfaceCard, statusTone } from "./ui/surfaces";
import { useEffect, useState } from "react";
import {
  describeDashboardError,
  getDashboard,
  type DashboardAutoPoolCapacity,
  type DashboardLoadError,
  type DashboardResponse,
} from "../api/dashboard";

type DashboardState =
  | { kind: "loading" }
  | { kind: "success"; data: DashboardResponse }
  | { kind: "error"; error: DashboardLoadError };

/** AUTO 池容量行内展示（每行 AUTO 池容量，A15/A17）。 */
function AutoPoolItem({ pool }: { pool: DashboardAutoPoolCapacity }) {
  return (
    <li>
      <span className="mono">{pool.ip_pool.name}</span>
      <span className="unset mono">
        （{pool.ip_pool.start_address}–{pool.ip_pool.end_address}）
      </span>
      ：可分配 {pool.allocatable_total} · 已占用 {pool.occupied} · 剩余{" "}
      <span className={pool.remaining < 0 ? "capacity-negative" : undefined}>
        {pool.remaining}
      </span>
    </li>
  );
}

/**
 * F013 Dashboard 汇总面板（Contract §3；§20/T32/A13–A20）：
 * - 计数：Cluster / Resource / BareMetal / VM / Network，全局未删口径
 *   （含 INACTIVE；软删不计，I-1/I-8/DR-180），不受分页影响；
 * - per-Network 容量：可分配总量 / 已占用 / 剩余（F010 §6.9 口径，DR-182，
 *   前端只消费不重算）；剩余可为负、原样展示不截断（DR-130）；
 * - 每行 AUTO 池容量（池范围 ∩ 可分配集合口径）；
 * - 容量与 status / auto_allocate 分别展示（A19）：INACTIVE 网络仍出现且
 *   容量不清零；状态 / 许可不改变容量数字；
 * - 不提供跨 Network 全局合计（I-16/DR-183 定稿：不同 Cluster 可含相同
 *   地址，相加易误导），前端不自行相加；
 * - 不是监控面板（§3/§20）：无实时 CPU / 内存 / 流量 / 可达性数据；
 * - Loading / Success / Empty / Error 显式区分，错误绝不伪装成空数据 /
 *   计数为 0；只读，无任何写入口（A21）。
 */
export default function DashboardPanel() {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [state, setState] = useState<DashboardState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  // page/page_size 仅作用于 networks.items（Contract §3.1；counts 不受分页影响）
  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    getDashboard({ page, page_size: pageSize })
      .then((data) => {
        if (!cancelled) {
          setState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        // 401 已由 client 全局处理器回登录页；403 / 422 / 500 / 网络错误显式呈现
        if (!cancelled) {
          setState({ kind: "error", error: describeDashboardError(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [page, pageSize, reloadToken]);

  return (
    <SurfaceCard className="panel" aria-label="Dashboard 资源汇总">
      <h2>Dashboard（资源汇总）</h2>
      <div className="dashboard-note">
        <InfoState message="计数与容量均为未删除口径（含 INACTIVE 集群 / 网络；软删不计）。剩余 = 可分配总量 − 已占用，可为负值并原样展示（不截断）；不提供跨 Network 全局合计（不同集群可含相同地址）。" />
      </div>

      {state.kind === "loading" && <LoadingState label="正在加载汇总数据…" />}

      {state.kind === "error" && (
        <ErrorState
          message={`加载汇总数据失败：${state.error.message}`}
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}

      {state.kind === "success" && (
        <>
          <div className="dashboard-counts">
            <SurfaceCard className="count-card"><Statistic title="Clusters（集群）" value={state.data.counts.clusters} /></SurfaceCard>
            <SurfaceCard className="count-card"><Statistic title="Resources（资源总数）" value={state.data.counts.resources} /></SurfaceCard>
            <SurfaceCard className="count-card"><Statistic title="BareMetal（物理机）" value={state.data.counts.bare_metal} /></SurfaceCard>
            <SurfaceCard className="count-card"><Statistic title="VM（虚拟机）" value={state.data.counts.virtual_machines} /></SurfaceCard>
            <SurfaceCard className="count-card"><Statistic title="Networks（网络）" value={state.data.counts.networks} /></SurfaceCard>
          </div>

          <h3 className="detail-section-title">Network 容量（按网络）</h3>
          {state.data.networks.items.length === 0 ? (
            <EmptyState description="暂无未删除的网络（计数仍为全局未删口径，非错误）。" />
          ) : (
            <>
              <div className="table-wrap">
                <DataTable className="data-table">
                  <thead>
                    <tr>
                      <th>cluster</th>
                      <th>network</th>
                      <th>cidr</th>
                      <th>status</th>
                      <th>auto_allocate</th>
                      <th>可分配总量</th>
                      <th>已占用</th>
                      <th>剩余</th>
                      <th>AUTO 池容量</th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.networks.items.map((row) => (
                      <tr key={row.network.id}>
                        <td>
                          <span className="mono">{row.network.cluster.code}</span>
                          <span className="unset">（{row.network.cluster.name}）</span>
                        </td>
                        <td>{row.network.name}</td>
                        <td className="mono">{row.network.cidr}</td>
                        <td>
                          <StatusTag tone={statusTone(row.network.status)}>{row.network.status}</StatusTag>
                        </td>
                        <td>{row.network.auto_allocate ? "true" : "false"}</td>
                        <td className="mono">{row.capacity.allocatable_total}</td>
                        <td className="mono">{row.capacity.occupied}</td>
                        <td className="mono">
                          <span
                            className={
                              row.capacity.remaining < 0 ? "capacity-negative" : undefined
                            }
                          >
                            {row.capacity.remaining}
                          </span>
                        </td>
                        <td>
                          {row.auto_pools.length === 0 ? (
                            <span className="unset">—（无 AUTO 池）</span>
                          ) : (
                            <ul className="pool-list">
                              {row.auto_pools.map((pool) => (
                                <AutoPoolItem key={pool.ip_pool.id} pool={pool} />
                              ))}
                            </ul>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </DataTable>
              </div>
              <ServerPagination
                page={state.data.networks.page}
                pageSize={state.data.networks.page_size}
                total={state.data.networks.total}
                appliedPageSize={pageSize}
                onGotoPage={setPage}
                onChangePageSize={(nextPageSize) => {
                  setPageSize(nextPageSize);
                  setPage(1);
                }}
              />
            </>
          )}
        </>
      )}
    </SurfaceCard>
  );
}
