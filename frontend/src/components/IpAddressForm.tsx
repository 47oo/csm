import { useEffect, useState, type FormEvent } from "react";
import { Button, Input, Select } from "antd";
import type { Network } from "../api/networks";
import type { Resource } from "../api/resources";
import { listResources } from "../api/resources";
import type { Interface } from "../api/interfaces";
import { listInterfaces } from "../api/interfaces";
import { listIpPools, type IpPool } from "../api/ipPools";
import type {
  IpAddress,
  IpAddressActionError,
  NetworkCapacityResponse,
} from "../api/ipAddresses";
import { getNetworkCapacity } from "../api/ipAddresses";
import {
  emptyIpAddressFormValues,
  ipAddressFormFieldFromPath,
  ipAddressFormValuesFromIpAddress,
  parseIpAddressFormValues,
  type IpAddressFieldKey,
  type IpAddressFormErrors,
  type IpAddressFormMode,
  type IpAddressFormValues,
  type IpAddressServerFieldKey,
} from "./ipAddressForm";

interface IpAddressFormProps {
  /** manual=手动分配 / auto=自动分配 / edit=绑定/解绑/转移/描述。 */
  mode: IpAddressFormMode;
  /** 供选择的网络列表（父组件已加载，仅未删除；手动/自动分配的 network 选择器）。 */
  networks: Network[];
  /** edit 模式：被编辑的 IP 地址。 */
  ipAddress?: IpAddress;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeIpAddressActionError 解析后传入）。 */
  serverError: IpAddressActionError | null;
  onSubmit: (values: IpAddressFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/** AUTO 池下拉数据加载状态（自动分配模式；按所选 Network 加载，Contract §6.3）。 */
type PoolOptionsState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; pools: IpPool[]; total: number }
  | { kind: "error"; message: string };

/** 容量数据加载状态（自动分配模式的最小展示；显示归 F013，加载失败不阻塞分配）。 */
type CapacityState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: NetworkCapacityResponse }
  | { kind: "error"; message: string };

/** edit 模式：同集群 Resource 下拉（绑定/转移的两级选择第一级）。 */
type ResourceOptionsState =
  | { kind: "loading" }
  | { kind: "success"; resources: Resource[]; total: number }
  | { kind: "error"; message: string };

/** edit 模式：所选 Resource 的 Interface 下拉（两级选择第二级）。 */
type InterfaceOptionsState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; interfaces: Interface[]; total: number }
  | { kind: "error"; message: string };

/** Tailwind 工具类（F017：替代原 form-field / field-error / mono / unset / status 样式）。 */
const FIELD_CLASS = "flex flex-col gap-1.5";
const LABEL_CLASS = "text-sm font-medium text-gray-700";
const FIELD_ERROR_CLASS = "text-sm text-red-600";
const STATUS_CLASS = "text-sm text-gray-500";
const UNSET_CLASS = "text-gray-400";
const MONO_CLASS = "font-mono text-sm text-gray-900";
const STATUS_ERROR_CLASS =
  "flex flex-col items-start gap-2 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700";

/**
 * IPAddress 分配 / 编辑表单（F010，Contract §2/§6.2/§6.3/§6.5）：
 * - 手动分配（manual）：network 选择器（仅未删除网络；须 ACTIVE，INACTIVE 时
 *   服务端 409 allocation_not_allowed{network_inactive}，本地提示不拦截）+
 *   address（单个裸 IPv4 主机地址，不带掩码；属 CIDR 本地提示，服务端权威
 *   校验 422：网络/广播/禁用段/gateway/RESERVED）+ description；
 * - 自动分配（auto）：network 选择器 + 指定 AUTO 池选择器（按网络加载
 *   allocation_mode=AUTO 的未删池；非 AUTO / 网络未开 auto_allocate / INACTIVE
 *   由服务端 409 承载，本地提示不拦截；池耗尽 409 no_available_address 不切换）；
 *   附网络容量最小展示（显示归 F013；remaining 负值原样呈现，DR-130）；
 * - 编辑（edit）：network/address 只读（创建后不可改，DR-120）；绑定/解绑/转移
 *   经「同集群资源 → 接口」两级选择（interface 须与 IP 同 Cluster，422
 *   field="interface"）；空选 = 解绑（显式 null，IP 继续占用）；description
 *   清空 = 删除描述；分配与绑定分离（创建时不提供 interface，DR-137）；
 * - 422 点路径经 ipAddressFormFieldFromPath 映射到对应输入，未知路径在通用
 *   错误区呈现（不静默丢弃）；409 unique_conflict → address 字段级错误；
 *   409 reference_exists（Endpoint 引用）→ 通用错误区呈现引用列表；
 *   409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）。
 */
export default function IpAddressForm({
  mode,
  networks,
  ipAddress,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: IpAddressFormProps) {
  const isCreate = mode === "manual" || mode === "auto";
  const [values, setValues] = useState<IpAddressFormValues>(() =>
    isCreate ? emptyIpAddressFormValues() : ipAddressFormValuesFromIpAddress(ipAddress ?? null),
  );
  const [localErrors, setLocalErrors] = useState<IpAddressFormErrors>({});
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [poolError, setPoolError] = useState<string | null>(null);

  // 自动分配：按所选网络加载 AUTO 池 + 容量（最小展示）
  const [poolOptions, setPoolOptions] = useState<PoolOptionsState>({ kind: "idle" });
  const [capacity, setCapacity] = useState<CapacityState>({ kind: "idle" });

  // 编辑：同集群资源 → 接口 两级选择
  const [resourceOptions, setResourceOptions] = useState<ResourceOptionsState>({
    kind: "loading",
  });
  const [interfaceOptions, setInterfaceOptions] = useState<InterfaceOptionsState>({
    kind: "idle",
  });
  const [selectedResourceId, setSelectedResourceId] = useState<string>(
    ipAddress?.interface?.resource.id ?? "",
  );

  function setField<K extends keyof IpAddressFormValues>(key: K, value: IpAddressFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  // 服务端字段错误：点路径归一到表单键；未知路径保留原文在通用错误区呈现
  const serverFields: Partial<Record<IpAddressServerFieldKey, string>> = {};
  const unmappedServerFields: { path: string; message: string }[] = [];
  for (const [path, message] of Object.entries(serverError?.fields ?? {})) {
    const key = ipAddressFormFieldFromPath(path);
    if (key !== null) {
      serverFields[key] = message;
    } else {
      unmappedServerFields.push({ path, message });
    }
  }

  // 当前所选网络（手动/自动分配的 CIDR 提示与状态提示；edit 模式网络只读）
  const selectedNetwork = networks.find((item) => item.id === values.network) ?? null;
  const networkCidr =
    selectedNetwork?.cidr ??
    (mode === "edit" && ipAddress !== undefined && ipAddress.network.id === values.network
      ? ipAddress.network.cidr
      : null);

  // edit 模式：当前绑定接口（展开引用）；其所属资源/接口不在候选列表时
  // 仍展示为选项，不静默丢失当前绑定
  const currentInterface = ipAddress?.interface ?? null;
  const currentResourceMissing =
    currentInterface !== null &&
    resourceOptions.kind === "success" &&
    !resourceOptions.resources.some((item) => item.id === currentInterface.resource.id);
  const currentInterfaceMissing =
    currentInterface !== null && !interfaceOptionsLoadingHas(interfaceOptions, currentInterface.id);

  // 自动分配：网络选择变化 → 加载该网络的 AUTO 池与容量数据
  useEffect(() => {
    if (mode !== "auto") {
      return;
    }
    if (values.network === "") {
      setPoolOptions({ kind: "idle" });
      setCapacity({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setPoolOptions({ kind: "loading" });
    setCapacity({ kind: "loading" });
    listIpPools({
      network_id: values.network,
      allocation_mode: "AUTO",
      page: 1,
      page_size: 100,
      sort: "name",
      order: "asc",
    })
      .then((data) => {
        if (!cancelled) {
          setPoolOptions({ kind: "success", pools: data.items, total: data.total });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPoolOptions({
            kind: "error",
            message: "无法加载该网络的 AUTO 地址池列表，请重选网络或稍后重试",
          });
        }
      });
    getNetworkCapacity(values.network)
      .then((data) => {
        if (!cancelled) {
          setCapacity({ kind: "success", data });
        }
      })
      .catch(() => {
        // 容量仅为辅助展示（显示归 F013）：失败不阻塞分配，如实提示
        if (!cancelled) {
          setCapacity({ kind: "error", message: "容量数据加载失败（不影响分配操作）" });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, values.network]);

  // 编辑：加载 IP 所属集群的资源（绑定/转移的接口须与 IP 同 Cluster）
  useEffect(() => {
    if (mode !== "edit" || ipAddress === undefined) {
      return;
    }
    let cancelled = false;
    setResourceOptions({ kind: "loading" });
    listResources({
      cluster_id: ipAddress.cluster.id,
      page: 1,
      page_size: 100,
      sort: "hostname",
      order: "asc",
    })
      .then((data) => {
        if (!cancelled) {
          setResourceOptions({ kind: "success", resources: data.items, total: data.total });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResourceOptions({
            kind: "error",
            message: "无法加载同集群资源列表，请关闭后重试",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, ipAddress]);

  // 编辑：所选资源变化 → 加载其接口列表
  useEffect(() => {
    if (mode !== "edit" || selectedResourceId === "") {
      setInterfaceOptions({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setInterfaceOptions({ kind: "loading" });
    listInterfaces({
      resource_id: selectedResourceId,
      page: 1,
      page_size: 100,
      sort: "name",
      order: "asc",
    })
      .then((data) => {
        if (!cancelled) {
          setInterfaceOptions({ kind: "success", interfaces: data.items, total: data.total });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setInterfaceOptions({
            kind: "error",
            message: "无法加载该资源的接口列表，请重选资源或稍后重试",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [mode, selectedResourceId]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const parsed = parseIpAddressFormValues(values, mode, networkCidr);
    const errors: IpAddressFormErrors = parsed.ok ? {} : parsed.errors;
    const nextNetworkError =
      isCreate && values.network === ""
        ? "必须选择所属网络（服务端校验 network 存在且未删除；创建后不可更改）"
        : null;
    const nextPoolError =
      mode === "auto" && values.ip_pool === ""
        ? "必须选择 AUTO 地址池（服务端校验池存在、属该网络且为 AUTO 模式；耗尽不切换其它池）"
        : null;
    setLocalErrors(errors);
    setNetworkError(nextNetworkError);
    setPoolError(nextPoolError);
    if (!parsed.ok || nextNetworkError !== null || nextPoolError !== null) {
      return;
    }
    onSubmit(values);
  }

  function fieldError(key: IpAddressFieldKey): string | undefined {
    return localErrors[key] ?? serverFields[key];
  }

  /** 网络选择器（手动/自动分配共用；仅未删除网络）。 */
  function renderNetworkSelect() {
    return (
      <div className={FIELD_CLASS}>
        <label htmlFor="ip-address-network" className={LABEL_CLASS}>
          network（所属网络，必填；创建后不可更改；新增分配要求网络 ACTIVE）
        </label>
        <Select
          id="ip-address-network"
          className="w-full"
          value={values.network}
          onChange={(value) => {
            setField("network", value as string);
            // 自动分配：换网络后原池选择失效，重置（服务端校验池属该网络）
            if (mode === "auto") {
              setField("ip_pool", "");
            }
          }}
          disabled={submitting}
          status={(networkError ?? serverFields.network) ? "error" : undefined}
          options={[
            { value: "", label: "请选择网络…" },
            ...networks.map((item) => ({
              value: item.id,
              label: `${item.name}（${item.cidr}）`,
            })),
          ]}
        />
        {(networkError ?? serverFields.network) && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {networkError ?? serverFields.network}
          </p>
        )}
        {selectedNetwork !== null && selectedNetwork.status !== "ACTIVE" && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            注意：该网络当前为 INACTIVE，服务端将拒绝新增分配（409
            allocation_not_allowed/network_inactive；绑定/解绑/转移等关系编辑不受限）
          </p>
        )}
        {mode === "auto" && selectedNetwork !== null && !selectedNetwork.auto_allocate && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            注意：该网络未开启 auto_allocate 自动分配，服务端将拒绝自动分配（409
            allocation_not_allowed/auto_allocate_disabled）
          </p>
        )}
      </div>
    );
  }

  /** 网络只读展示（edit 模式；创建后不可改，DR-120）。 */
  function renderNetworkReadonly() {
    const current = ipAddress?.network ?? null;
    const networkMissing =
      current !== null && !networks.some((item) => item.id === current.id);
    return (
      <div className={FIELD_CLASS}>
        <label htmlFor="ip-address-network-readonly" className={LABEL_CLASS}>
          network（所属网络，创建后不可更改）
        </label>
        <p id="ip-address-network-readonly" className={MONO_CLASS}>
          {current !== null
            ? `${current.name}（${current.cidr}）`
            : "未知（网络引用缺失）"}
          {networkMissing && <span className={UNSET_CLASS}>（不在当前网络候选列表，如已软删）</span>}
        </p>
        {serverFields.network && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {serverFields.network}
          </p>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      {isCreate ? renderNetworkSelect() : renderNetworkReadonly()}

      {mode === "manual" && (
        <div className={FIELD_CLASS}>
          <label htmlFor="ip-address-address" className={LABEL_CLASS}>
            address（必填；单个裸 IPv4 主机地址，不带掩码；须属所属网络 CIDR）
          </label>
          <Input
            id="ip-address-address"
            name="address"
            value={values.address}
            onChange={(event) => setField("address", event.target.value)}
            disabled={submitting}
            status={fieldError("address") ? "error" : undefined}
            placeholder={"如 10.0.0.5；点分四段、不带掩码；网络/广播地址、禁用段、gateway、RESERVED 池范围由服务端校验"}
          />
          {fieldError("address") && (
            <p className={FIELD_ERROR_CLASS} role="alert">
              {fieldError("address")}
            </p>
          )}
        </div>
      )}

      {mode === "auto" && (
        <>
          <div className={FIELD_CLASS}>
            <label htmlFor="ip-address-pool" className={LABEL_CLASS}>
              ip_pool（必填；该网络的 AUTO 地址池；服务端在池范围内按地址升序自动选址）
            </label>
            <Select
              id="ip-address-pool"
              className="w-full"
              value={values.ip_pool}
              onChange={(value) => setField("ip_pool", value as string)}
              disabled={submitting || values.network === "" || poolOptions.kind === "loading"}
              status={(poolError ?? serverFields.ip_pool) ? "error" : undefined}
              options={[
                {
                  value: "",
                  label:
                    values.network === ""
                      ? "请先选择网络…"
                      : poolOptions.kind === "loading"
                        ? "正在加载 AUTO 池…"
                        : "请选择 AUTO 地址池…",
                },
                ...(poolOptions.kind === "success"
                  ? poolOptions.pools.map((pool) => {
                      const poolRemaining =
                        capacity.kind === "success"
                          ? capacity.data.auto_pools.find(
                              (entry) => entry.ip_pool.id === pool.id,
                            )?.remaining
                          : undefined;
                      return {
                        value: pool.id,
                        label: `${pool.name}（${pool.start_address} – ${pool.end_address}）${
                          poolRemaining !== undefined ? ` · 剩余 ${poolRemaining}` : ""
                        }`,
                      };
                    })
                  : []),
              ]}
            />
            {(poolError ?? serverFields.ip_pool) && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                {poolError ?? serverFields.ip_pool}
              </p>
            )}
            {poolOptions.kind === "error" && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                {poolOptions.message}
              </p>
            )}
            {poolOptions.kind === "success" && poolOptions.total > poolOptions.pools.length && (
              <p className={STATUS_CLASS}>
                该网络 AUTO 池较多（共 {poolOptions.total} 个），下拉仅显示前{" "}
                {poolOptions.pools.length} 个
              </p>
            )}
          </div>
          {capacity.kind === "success" && (
            <div className={FIELD_CLASS}>
              <p className={STATUS_CLASS}>
                网络容量（最小展示；完整容量展示归 F013 Dashboard）：可分配{" "}
                {capacity.data.network_capacity.allocatable_total} · 已占用{" "}
                {capacity.data.network_capacity.occupied} · 剩余{" "}
                {capacity.data.network_capacity.remaining}
                {capacity.data.network_capacity.remaining < 0 && (
                  <span className={UNSET_CLASS}>
                    （剩余为负：存量地址已落入当前保留范围，按口径原样呈现）
                  </span>
                )}
              </p>
            </div>
          )}
          {capacity.kind === "error" && (
            <div className={FIELD_CLASS}>
              <p className={UNSET_CLASS}>{capacity.message}</p>
            </div>
          )}
        </>
      )}

      {mode === "edit" && (
        <>
          <div className={FIELD_CLASS}>
            <label htmlFor="ip-address-address-readonly" className={LABEL_CLASS}>
              address（创建后不可更改；如需更换地址请释放后重新分配）
            </label>
            <p id="ip-address-address-readonly" className={MONO_CLASS}>
              {ipAddress?.address ?? "未知"}
            </p>
            {serverFields.address && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                {serverFields.address}
              </p>
            )}
          </div>

          <div className={FIELD_CLASS}>
            <label htmlFor="ip-address-interface-resource" className={LABEL_CLASS}>
              绑定接口 · 第 1 步：选择资源（仅列出与该 IP 同集群的未删除资源）
            </label>
            <Select
              id="ip-address-interface-resource"
              className="w-full"
              value={selectedResourceId}
              onChange={(value) => {
                setSelectedResourceId(value as string);
                // 换资源后原接口选择失效，重置为未绑定（显式提交才生效）
                setField("interface", "");
              }}
              disabled={submitting || resourceOptions.kind !== "success"}
              options={[
                { value: "", label: "不选择资源（接口将保持未绑定）" },
                ...(resourceOptions.kind === "success"
                  ? resourceOptions.resources.map((resource) => ({
                      value: resource.id,
                      label: `${resource.hostname}（${resource.resource_type}）`,
                    }))
                  : []),
                ...(currentResourceMissing && currentInterface !== null
                  ? [
                      {
                        value: currentInterface.resource.id,
                        label: `${currentInterface.resource.hostname}（当前绑定接口所属资源，不在候选列表）`,
                      },
                    ]
                  : []),
              ]}
            />
            {resourceOptions.kind === "error" && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                {resourceOptions.message}
              </p>
            )}
            {resourceOptions.kind === "success" &&
              resourceOptions.total > resourceOptions.resources.length && (
                <p className={STATUS_CLASS}>
                  同集群资源较多（共 {resourceOptions.total} 个），下拉仅显示前{" "}
                  {resourceOptions.resources.length} 个
                </p>
              )}
          </div>

          <div className={FIELD_CLASS}>
            <label htmlFor="ip-address-interface" className={LABEL_CLASS}>
              绑定接口 · 第 2 步：interface（空选 = 解绑 / 保持未绑定，IP 继续占用不被释放）
            </label>
            <Select
              id="ip-address-interface"
              className="w-full"
              value={values.interface}
              onChange={(value) => setField("interface", value as string)}
              disabled={submitting || selectedResourceId === ""}
              status={serverFields.interface ? "error" : undefined}
              options={[
                { value: "", label: "未绑定（解绑 / 保持未绑定）" },
                ...(interfaceOptions.kind === "success"
                  ? interfaceOptions.interfaces.map((iface) => ({
                      value: iface.id,
                      label: `${iface.name}${iface.enabled ? "" : "（已停用）"}`,
                    }))
                  : []),
                ...(currentInterfaceMissing && currentInterface !== null
                  ? [
                      {
                        value: currentInterface.id,
                        label: `${currentInterface.name}（当前绑定，不在该资源接口列表）`,
                      },
                    ]
                  : []),
              ]}
            />
            {interfaceOptions.kind === "error" && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                {interfaceOptions.message}
              </p>
            )}
            {interfaceOptions.kind === "success" &&
              interfaceOptions.total > interfaceOptions.interfaces.length && (
                <p className={STATUS_CLASS}>
                  该资源接口较多（共 {interfaceOptions.total} 个），下拉仅显示前{" "}
                  {interfaceOptions.interfaces.length} 个
                </p>
              )}
            {serverFields.interface && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                {serverFields.interface}
              </p>
            )}
            {ipAddress?.interface != null && values.interface === "" && (
              <p className={FIELD_ERROR_CLASS} role="alert">
                注意：当前选择为「未绑定」，保存后将解绑该 IP（仅移除接口关系，IP
                继续占用、不会被释放；被未删除 Endpoint 引用时服务端将拒绝）
              </p>
            )}
          </div>
        </>
      )}

      <div className={FIELD_CLASS}>
        <label htmlFor="ip-address-description" className={LABEL_CLASS}>
          description（描述，可选）
        </label>
        <Input.TextArea
          id="ip-address-description"
          name="description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          status={fieldError("description") ? "error" : undefined}
          placeholder="可选，无长度上限；编辑时清空表示删除描述（显式置 null）"
        />
        {fieldError("description") && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {fieldError("description")}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div className={STATUS_ERROR_CLASS} role="alert">
          <p>
            {serverError.message}
            {serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}
          </p>
          {unmappedServerFields.length > 0 && (
            <ul className="list-disc pl-5">
              {unmappedServerFields.map(({ path, message }) => (
                <li key={path}>
                  {path}：{message}
                </li>
              ))}
            </ul>
          )}
          {serverError.references.length > 0 && (
            <ul className="list-disc pl-5">
              {serverError.references.map((item) => (
                <li key={`${item.object_type}-${item.object_id}`}>
                  引用对象：{item.label ?? item.object_id}（{item.object_type}）
                </li>
              ))}
            </ul>
          )}
          {serverError.versionConflict && onRefresh && (
            <p>
              <Button onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </Button>
            </p>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button type="primary" htmlType="submit" disabled={submitting}>
          {submitting
            ? isCreate
              ? "正在分配…"
              : "正在保存…"
            : isCreate
              ? mode === "manual"
                ? "手动分配"
                : "自动分配"
              : "保存修改"}
        </Button>
        <Button onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </div>
    </form>
  );
}

/** 接口选项中是否已包含当前绑定接口（避免重复/丢失当前绑定选项）。 */
function interfaceOptionsLoadingHas(
  state: InterfaceOptionsState,
  interfaceId: string,
): boolean {
  return state.kind === "success" && state.interfaces.some((iface) => iface.id === interfaceId);
}
