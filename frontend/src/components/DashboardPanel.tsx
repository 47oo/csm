import { useEffect, useState } from "react";
import { Alert, Button, Card, Empty, Select, Spin, Statistic, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
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

type NetworkRow = DashboardResponse["networks"]["items"][number];

/** AUTO 池容量行内展示（每行 AUTO 池容量，A15/A17）。 */
function AutoPoolItem({ pool }: { pool: DashboardAutoPoolCapacity }) {
  return (
    <li>
      <span className="font-mono">{pool.ip_pool.name}</span>
      <span className="font-mono text-gray-500">
        （{pool.ip_pool.start_address}–{pool.ip_pool.end_address}）
      </span>
      ：可分配 {pool.allocatable_total} · 已占用 {pool.occupied} · 剩余{" "}
      <span className={pool.remaining < 0 ? "text-red-600" : undefined}>
        {pool.remaining}
      </span>
    </li>
  );
}

/** Network 容量表列（列头、口径与文案与迁移前一致；DR-130 剩余为负原样展示）。 */
const capacityColumns: ColumnsType<NetworkRow> = [
  {
    title: "cluster",
    key: "cluster",
    render: (_, row) => (
      <>
        <span className="font-mono">{row.network.cluster.code}</span>
        <span className="text-gray-500">（{row.network.cluster.name}）</span>
      </>
    ),
  },
  {
    title: "network",
    key: "network",
    render: (_, row) => row.network.name,
  },
  {
    title: "cidr",
    key: "cidr",
    render: (_, row) => <span className="font-mono">{row.network.cidr}</span>,
  },
  {
    title: "status",
    key: "status",
    render: (_, row) => (
      <Tag color={row.network.status === "ACTIVE" ? "green" : "default"}>
        {row.network.status}
      </Tag>
    ),
  },
  {
    title: "auto_allocate",
    key: "auto_allocate",
    render: (_, row) => (row.network.auto_allocate ? "true" : "false"),
  },
  {
    title: "可分配总量",
    key: "allocatable_total",
    render: (_, row) => <span className="font-mono">{row.capacity.allocatable_total}</span>,
  },
  {
    title: "已占用",
    key: "occupied",
    render: (_, row) => <span className="font-mono">{row.capacity.occupied}</span>,
  },
  {
    title: "剩余",
    key: "remaining",
    render: (_, row) => (
      <span
        className={row.capacity.remaining < 0 ? "font-mono text-red-600" : "font-mono"}
      >
        {row.capacity.remaining}
      </span>
    ),
  },
  {
    title: "AUTO 池容量",
    key: "auto_pools",
    render: (_, row) =>
      row.auto_pools.length === 0 ? (
        <span className="text-gray-500">—（无 AUTO 池）</span>
      ) : (
        <ul className="list-disc pl-5">
          {row.auto_pools.map((pool) => (
            <AutoPoolItem key={pool.ip_pool.id} pool={pool} />
          ))}
        </ul>
      ),
  },
];

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
    <section aria-label="Dashboard 资源汇总">
      <Card title="Dashboard（资源汇总）">
        <Alert
          className="mb-4"
          type="info"
          showIcon
          message="计数与容量均为未删除口径（含 INACTIVE 集群 / 网络；软删不计）。剩余 = 可分配总量 − 已占用，可为负值并原样展示（不截断）；不提供跨 Network 全局合计（不同集群可含相同地址）。"
        />

        {state.kind === "loading" && (
          <div className="flex items-center justify-center gap-3 py-10">
            <Spin />
            <span>正在加载汇总数据…</span>
          </div>
        )}

        {state.kind === "error" && (
          <Alert
            type="error"
            showIcon
            message={`加载汇总数据失败：${state.error.message}`}
            action={
              <Button
                type="primary"
                danger
                onClick={() => setReloadToken((token) => token + 1)}
              >
                重试
              </Button>
            }
          />
        )}

        {state.kind === "success" && (
          <>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <Statistic title="Clusters（集群）" value={state.data.counts.clusters} />
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <Statistic title="Resources（资源总数）" value={state.data.counts.resources} />
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <Statistic title="BareMetal（物理机）" value={state.data.counts.bare_metal} />
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <Statistic title="VM（虚拟机）" value={state.data.counts.virtual_machines} />
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <Statistic title="Networks（网络）" value={state.data.counts.networks} />
              </div>
            </div>

            <h3 className="mb-3 mt-6 text-base font-semibold">Network 容量（按网络）</h3>
            {state.data.networks.items.length === 0 ? (
              <Empty
                className="py-8"
                description="暂无未删除的网络（计数仍为全局未删口径，非错误）。"
              />
            ) : (
              <>
                <Table<NetworkRow>
                  columns={capacityColumns}
                  dataSource={state.data.networks.items}
                  rowKey={(row) => row.network.id}
                  pagination={false}
                  scroll={{ x: "max-content" }}
                />
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <span>
                    共 {state.data.networks.total} 个网络 · 第 {state.data.networks.page} /{" "}
                    {Math.max(
                      1,
                      Math.ceil(state.data.networks.total / state.data.networks.page_size),
                    )}{" "}
                    页
                  </span>
                  <Button
                    disabled={state.data.networks.page <= 1}
                    onClick={() => setPage(state.data.networks.page - 1)}
                  >
                    上一页
                  </Button>
                  <Button
                    disabled={
                      state.data.networks.page >=
                      Math.max(
                        1,
                        Math.ceil(state.data.networks.total / state.data.networks.page_size),
                      )
                    }
                    onClick={() => setPage(state.data.networks.page + 1)}
                  >
                    下一页
                  </Button>
                  <label className="flex items-center gap-2">
                    每页
                    <Select
                      className="w-20"
                      value={pageSize}
                      onChange={(value) => {
                        setPageSize(value);
                        setPage(1);
                      }}
                      options={[
                        { value: 20, label: "20" },
                        { value: 50, label: "50" },
                        { value: 100, label: "100" },
                      ]}
                    />
                    条
                  </label>
                </div>
              </>
            )}
          </>
        )}
      </Card>
    </section>
  );
}
