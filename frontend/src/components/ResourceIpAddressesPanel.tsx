import { Button, DataTable } from "./ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState, WarningState } from "./ui/feedback";
import { useEffect, useState } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import { listInterfaces, type Interface } from "../api/interfaces";
import { listIpAddresses, type IpAddress, type IpAddressListResponse } from "../api/ipAddresses";
import type { Resource } from "../api/resources";
import {
  buildResourceInterfaceIpsQuery,
  buildResourceInterfacesQuery,
  collectResourceIpTruncations,
  mergeResourceIpRows,
  RESOURCE_INTERFACES_MAX_PAGES,
  RESOURCE_IP_DESCRIPTION_NULL_LABEL,
  RESOURCE_IP_LOAD_CONCURRENCY,
  RESOURCE_IP_POOL_NULL_LABEL,
  resourceInterfacesListBoundary,
  summarizeResourceIpInterfaceLoads,
  type ResourceIpInterfaceFailure,
  type ResourceIpRow,
  type ResourceIpTruncation,
} from "./resourceIpAddresses";

interface ResourceIpAddressesPanelProps {
  /** 所属 Resource（聚合入口：先取其未删接口，再逐接口取已绑定 IP）。 */
  resource: Resource;
  /** READ 全角色内容一致（DR-390）：本区域只读、不按权限差异化渲染；保持与相邻区域一致的挂载签名。 */
  user: User;
}

/** 面板加载状态：Loading / Error（可重试）/ Success（含部分失败与截断明细）。 */
type ResourceIpAddressesState =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | {
      kind: "success";
      /** 合并排序后的展示行（interface.name ASC → IP 数值 ASC → id ASC，DR-385）。 */
      rows: ResourceIpRow[];
      /** 部分接口加载失败（DR-389）：保留已加载行 + 警告，不静默丢弃。 */
      failures: ResourceIpInterfaceFailure[];
      /** 接口列表超安全上限被截断（DR-383）：显式提示总数。 */
      interfacesTruncation: { total: number; loaded: number } | null;
      /** 任一接口 IP 超单次加载上限被截断（DR-388）：逐接口显式提示。 */
      ipTruncations: ResourceIpTruncation[];
    };

/** 加载失败文案（沿用各详情区域口径：API 错误带 code / HTTP 状态）。 */
function loadErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    return `${error.message}（${error.code ?? `HTTP ${error.status}`}）`;
  }
  return displayError(error);
}

/** 失败接口清单文案（数量多时截断列举，始终给出总数，不静默省略）。 */
function failedInterfacesText(failures: ResourceIpInterfaceFailure[]): string {
  const names = failures.map((failure) => failure.interfaceName);
  if (names.length <= 10) {
    return names.join("、");
  }
  return `${names.slice(0, 10).join("、")}…等共 ${names.length} 个`;
}

/**
 * Resource Detail 的 IP Addresses 区域（F022，§18 A1–A7 / DR-382–DR-400）：
 * - 只读聚合：先 GET /api/v1/interfaces?resource_id（未删、name 升序）逐页取全
 *   （单页 100、安全上限 50 页，超限显式提示），再对每个未删接口
 *   GET /api/v1/ip-addresses?interface_id（未删、address 升序、单次 100，
 *   复用 F019 buildInterfaceBoundIpsQuery）有界并发（≤6）加载；
 * - 合并按 interface.name ASC → IP 数值 ASC → id ASC 确定性排序（DR-385）；
 * - 字段（DR-386）：address / network(name,cidr) / interface.name /
 *   ip_pool（null → 「池外（手动）」）/ description（null → 「—」）；
 *   不显示 cluster（Overview 已有）、不显示 version / 时间戳（DR-399）；
 * - 状态（DR-387–DR-389）：Loading / Empty（无绑定 IP）/ Error（可重试，
 *   绝不伪装成空列表）；单接口 total>items 或接口列表超上限显式提示总数、
 *   不静默截断；部分接口失败 → 保留已加载行 + 警告失败接口，全部失败 →
 *   Error；重试重取全部；
 * - 只读、READ 全角色内容一致（DR-390）：无编辑 / 绑定 / 解绑 / 转移 / 释放
 *   / 分配入口；无 VIEW_DELETED 开关（接口与 IP 均固定 deleted=exclude，
 *   DR-391）；绑定到已软删 Interface 的 IP 因只查未删接口自然不出现；
 * - 不修改 / 不合并 F019 每接口「已绑定 IP」展示（DR-392：独立请求，不共享缓存）。
 */
export default function ResourceIpAddressesPanel({ resource }: ResourceIpAddressesPanelProps) {
  const [state, setState] = useState<ResourceIpAddressesState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });

    (async () => {
      // ---- 1. 接口列表逐页取全（DR-382/DR-383：未删接口、name 升序、≤50 页） ----
      const interfaces: Interface[] = [];
      let total = 0;
      try {
        for (let page = 1; ; page += 1) {
          const data = await listInterfaces(buildResourceInterfacesQuery(resource.id, page));
          if (cancelled) {
            return;
          }
          total = data.total;
          interfaces.push(...data.items);
          // 已覆盖 total / 空页（防御服务端异常，不无限翻页）/ 达安全上限即止
          if (data.items.length === 0 || interfaces.length >= total) {
            break;
          }
          if (page >= RESOURCE_INTERFACES_MAX_PAGES) {
            break;
          }
        }
      } catch (error) {
        if (!cancelled) {
          setState({ kind: "error", message: `加载接口列表失败：${loadErrorMessage(error)}` });
        }
        return;
      }

      // ---- 2. 逐接口已绑定 IP（DR-382/DR-398：有界并发 ≤6；单项失败不中止其余） ----
      const activeInterfaces = interfaces.filter((iface) => iface.deleted_at === null);
      const succeeded = new Map<string, IpAddressListResponse>();
      const failures: ResourceIpInterfaceFailure[] = [];
      let nextIndex = 0;
      const loadWorker = async (): Promise<void> => {
        for (;;) {
          if (cancelled) {
            return;
          }
          const index = nextIndex;
          nextIndex += 1;
          if (index >= activeInterfaces.length) {
            return;
          }
          const iface = activeInterfaces[index];
          try {
            const data = await listIpAddresses(buildResourceInterfaceIpsQuery(iface.id));
            if (!cancelled) {
              succeeded.set(iface.id, data);
            }
          } catch (error) {
            if (!cancelled) {
              failures.push({
                interfaceId: iface.id,
                interfaceName: iface.name,
                message: loadErrorMessage(error),
              });
            }
          }
        }
      };
      await Promise.all(
        Array.from(
          { length: Math.min(RESOURCE_IP_LOAD_CONCURRENCY, activeInterfaces.length) },
          () => loadWorker(),
        ),
      );
      if (cancelled) {
        return;
      }

      // ---- 3. 汇总（DR-389）：全失败 → Error（可重试）；否则合并 + 截断明细 ----
      const summary = summarizeResourceIpInterfaceLoads(activeInterfaces.length, failures);
      if (summary.allFailed) {
        setState({
          kind: "error",
          message:
            `该资源全部 ${failures.length} 个接口的 IP 地址加载均失败` +
            `（例如：${failures[0].message}）。`,
        });
        return;
      }
      const ipsByInterfaceId = new Map<string, readonly IpAddress[]>();
      const loads: { interfaceName: string; total: number; itemCount: number }[] = [];
      for (const iface of activeInterfaces) {
        const data = succeeded.get(iface.id);
        if (data !== undefined) {
          ipsByInterfaceId.set(iface.id, data.items);
          loads.push({
            interfaceName: iface.name,
            total: data.total,
            itemCount: data.items.length,
          });
        }
      }
      setState({
        kind: "success",
        rows: mergeResourceIpRows(activeInterfaces, ipsByInterfaceId),
        failures,
        interfacesTruncation:
          resourceInterfacesListBoundary(total, interfaces.length) === "truncated"
            ? { total, loaded: interfaces.length }
            : null,
        ipTruncations: collectResourceIpTruncations(loads),
      });
    })();

    return () => {
      cancelled = true;
    };
  }, [resource.id, reloadToken]);

  return (
    <>
      <h3 className="detail-section-title">IP Addresses（IP 地址）</h3>

      <div className="table-toolbar">
        <span className="permissions-note">
          经该资源各未删除网络接口聚合（{resource.hostname}；接口与 IP 均为未删除
          口径，按 interface.name 与 address 升序）；只读，READ 全角色一致
        </span>
      </div>

      {state.kind === "loading" && <LoadingState label="正在加载该资源的 IP 地址…" />}

      {state.kind === "error" && (
        <ErrorState
          message={`加载 IP 地址失败：${state.message}`}
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}

      {state.kind === "success" && (
        <>
          {state.failures.length > 0 && (
            <WarningState
              message={
                <>
                  <p>
                    {state.failures.length} 个接口的 IP 地址加载失败（
                    {failedInterfacesText(state.failures)}）：以下列表不含这些接口的
                    数据，为非完整结果；重试将重新加载全部数据。
                  </p>
                  <p>首个错误：{state.failures[0].message}</p>
                  <p>
                    <Button
                      type="button"
                      className="link-button"
                      onClick={() => setReloadToken((token) => token + 1)}
                    >
                      重试
                    </Button>
                  </p>
                </>
              }
            />
          )}

          {state.interfacesTruncation !== null && (
            <InfoState
              message={
                `该资源接口总数 ${state.interfacesTruncation.total} 个，超出单次安全加载` +
                `上限（${RESOURCE_INTERFACES_MAX_PAGES} 页 × 每页 100 条），仅聚合前 ` +
                `${state.interfacesTruncation.loaded} 个接口的 IP 地址（不静默截断）。`
              }
            />
          )}

          {state.ipTruncations.map((truncation) => (
            <InfoState
              key={truncation.interfaceName}
              message={
                `接口 ${truncation.interfaceName} 绑定 ${truncation.total} 个 IP 地址，` +
                `仅显示前 ${truncation.shown} 个（单接口单次加载分页上限 100，不静默截断）。`
              }
            />
          ))}

          {state.rows.length === 0 ? (
            <EmptyState
              description={
                state.failures.length > 0
                  ? "已加载的接口暂无绑定的 IP 地址；另有接口加载失败（见上方警告），当前为非完整结果。"
                  : "该资源的各接口暂无绑定的 IP 地址（未删除口径，非错误）。"
              }
            />
          ) : (
            <div className="table-wrap">
              <DataTable className="data-table" aria-label="资源 IP 地址列表">
                <thead>
                  <tr>
                    <th>address</th>
                    <th>network</th>
                    <th>interface</th>
                    <th>ip_pool（来源）</th>
                    <th>description</th>
                  </tr>
                </thead>
                <tbody>
                  {state.rows.map((row) => (
                    <tr key={row.ip.id}>
                      <td className="mono">{row.ip.address}</td>
                      <td>
                        <span className="mono">{row.ip.network.name}</span>
                        <span className="unset">（{row.ip.network.cidr}）</span>
                      </td>
                      <td className="mono">{row.interfaceName}</td>
                      <td>
                        {row.ip.ip_pool !== null ? (
                          row.ip.ip_pool.name
                        ) : (
                          <span className="unset">{RESOURCE_IP_POOL_NULL_LABEL}</span>
                        )}
                      </td>
                      <td>
                        {row.ip.description ?? (
                          <span className="unset">{RESOURCE_IP_DESCRIPTION_NULL_LABEL}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </DataTable>
            </div>
          )}
        </>
      )}
    </>
  );
}
