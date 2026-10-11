import { useEffect, useState, type FormEvent } from "react";
import { displayError, isApiError } from "../api/client";
import { listIpAddresses } from "../api/ipAddresses";
import { listInterfaces } from "../api/interfaces";
import type { Service } from "../api/services";
import type {
  EndpointProtocol,
  ServiceEndpoint,
  ServiceEndpointActionError,
} from "../api/serviceEndpoints";
import {
  emptyServiceEndpointFormValues,
  parseServiceEndpointFormValues,
  serviceEndpointFormFieldFromPath,
  serviceEndpointFormValuesFromEndpoint,
  type ServiceEndpointFieldKey,
  type ServiceEndpointFormErrors,
  type ServiceEndpointFormValues,
  type ServiceEndpointServerFieldKey,
} from "./serviceEndpointForm";

/** 服务端字段错误经点路径映射后的键（Contract §2.4 顶层字段）。 */
type ServerFieldKey = ServiceEndpointServerFieldKey;

/** 候选 IP 选项（同 Resource 已绑定未删 IP；经接口列表 → 各接口 IP 展平）。 */
interface IpOption {
  /** IPAddress UUID（载荷 ip_address）。 */
  id: string;
  address: string;
  networkName: string;
  interfaceName: string;
}

/** 候选 IP 加载状态（idle=未选择 Service）。 */
type IpOptionsState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; options: IpOption[]; truncated: boolean }
  | { kind: "error"; message: string };

interface ServiceEndpointFormProps {
  mode: "create" | "edit";
  /** 供选择的 Service 列表（父组件已加载，仅未删除；create 模式选择器数据源）。 */
  services: Service[];
  /** 面板所属 Service（create 模式预选；不在候选列表时仍可解析其归属资源）。 */
  ownerService: Service;
  /** edit 模式：被编辑的端点。 */
  endpoint?: ServiceEndpoint;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeServiceEndpointActionError 解析后传入）。 */
  serverError: ServiceEndpointActionError | null;
  onSubmit: (values: ServiceEndpointFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/**
 * ServiceEndpoint 创建 / 编辑表单（F012，Contract §2/§6.2/§6.4）：
 * - Service 选择器：创建必填（仅未删除 Service，服务端校验存在/未软删，422
 *   field="service"）；创建后不可改（DR-157），编辑时只读展示所属 Service；
 * - IPAddress 选择器：创建必填；候选 = 已绑定所选 Service 所属 Resource 的
 *   未删接口、且自身未删除的 IP（归属要求 interface.resource_id ==
 *   service.resource_id，DR-158；服务端仍权威校验 422 field="ip_address"）；
 *   创建后不可改，编辑时只读展示；切换 Service 时清空已选 IP；
 * - protocol ∈ {TCP, UDP}（仅大写规范值，下拉恒合法，DR-160）；
 * - port 整数 1–65535（含端点；本地快速校验，服务端 422 权威）；
 * - description 可选 nullable、无长度上限；清空 = 删除描述（显式 null）；
 * - 422 点路径经 serviceEndpointFormFieldFromPath 映射到对应输入，未知路径
 *   在通用错误区呈现（不静默丢弃）；409 unique_conflict{field:"port"} →
 *   port 字段级错误；409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）。
 */
export default function ServiceEndpointForm({
  mode,
  services,
  ownerService,
  endpoint,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: ServiceEndpointFormProps) {
  const isCreate = mode === "create";
  const [values, setValues] = useState<ServiceEndpointFormValues>(() =>
    isCreate
      ? { ...emptyServiceEndpointFormValues(), service: ownerService.id }
      : serviceEndpointFormValuesFromEndpoint(endpoint ?? null),
  );
  const [localErrors, setLocalErrors] = useState<ServiceEndpointFormErrors>({});
  const [serviceError, setServiceError] = useState<string | null>(null);
  const [ipAddressError, setIpAddressError] = useState<string | null>(null);
  const [ipOptions, setIpOptions] = useState<IpOptionsState>({ kind: "idle" });
  const [ipReloadToken, setIpReloadToken] = useState(0);

  function setField<K extends keyof ServiceEndpointFormValues>(
    key: K,
    value: ServiceEndpointFormValues[K],
  ) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  /** 切换 Service：候选 IP 作用域随归属资源变化，清空已选 IP（不保留失效选择）。 */
  function changeService(serviceId: string) {
    setValues((prev) => ({ ...prev, service: serviceId, ipAddress: "" }));
  }

  // 服务端字段错误：点路径归一到表单键；未知路径保留原文在通用错误区呈现
  const serverFields: Partial<Record<ServerFieldKey, string>> = {};
  const unmappedServerFields: { path: string; message: string }[] = [];
  for (const [path, message] of Object.entries(serverError?.fields ?? {})) {
    const key = serviceEndpointFormFieldFromPath(path);
    if (key !== null) {
      serverFields[key] = message;
    } else {
      unmappedServerFields.push({ path, message });
    }
  }

  /** 解析所选 Service 对象（面板所属 Service 回退：不在候选列表时仍可加载候选 IP）。 */
  function resolveService(serviceId: string): Service | null {
    if (serviceId === ownerService.id) {
      return ownerService;
    }
    return services.find((item) => item.id === serviceId) ?? null;
  }

  // 候选 IP 加载（仅 create；edit 模式 ip_address 只读展示）：
  // 所选 Service 的归属 Resource → 未删接口列表 → 各接口未删 IP（已绑定）。
  // F010 列表无 resource_id 过滤，故经接口链路逐接口查询（接口数有限）。
  useEffect(() => {
    if (!isCreate) {
      return;
    }
    if (values.service === "") {
      setIpOptions({ kind: "idle" });
      return;
    }
    const service = resolveService(values.service);
    if (service === null) {
      setIpOptions({
        kind: "error",
        message: "无法解析所选 Service 的归属资源（不在候选列表，如列表已截断）；请重新选择 Service",
      });
      return;
    }
    let cancelled = false;
    setIpOptions({ kind: "loading" });
    listInterfaces({
      resource_id: service.resource.id,
      deleted: "exclude",
      page_size: 100,
      sort: "name",
      order: "asc",
    })
      .then(async (interfaceData) => {
        const ipLists = await Promise.all(
          interfaceData.items.map((iface) =>
            listIpAddresses({
              interface_id: iface.id,
              deleted: "exclude",
              page_size: 100,
              sort: "address",
              order: "asc",
            }),
          ),
        );
        if (cancelled) {
          return;
        }
        const options: IpOption[] = [];
        for (const ipList of ipLists) {
          for (const ip of ipList.items) {
            if (ip.interface === null) {
              continue; // 防御：interface_id 过滤已保证已绑定
            }
            options.push({
              id: ip.id,
              address: ip.address,
              networkName: ip.network.name,
              interfaceName: ip.interface.name,
            });
          }
        }
        const truncated =
          interfaceData.total > interfaceData.items.length ||
          ipLists.some((ipList) => ipList.total > ipList.items.length);
        setIpOptions({ kind: "success", options, truncated });
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setIpOptions({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
    // services/ownerService 为面板一次性加载的候选快照，不作为重载触发条件
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCreate, values.service, ipReloadToken]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const parsed = parseServiceEndpointFormValues(values);
    const errors: ServiceEndpointFormErrors = parsed.ok ? {} : parsed.errors;
    const nextServiceError = isCreate && values.service === ""
      ? "必须选择所属服务（服务端校验 service 存在且未删除；创建后不可更改）"
      : null;
    const nextIpAddressError = isCreate && values.ipAddress === ""
      ? "必须选择 IP 地址（候选 = 已绑定该服务所属资源接口且未删除的 IP；创建后不可更改）"
      : null;
    setLocalErrors(errors);
    setServiceError(nextServiceError);
    setIpAddressError(nextIpAddressError);
    if (
      !parsed.ok ||
      Object.keys(errors).length > 0 ||
      nextServiceError !== null ||
      nextIpAddressError !== null
    ) {
      return;
    }
    onSubmit(values);
  }

  function fieldError(key: ServiceEndpointFieldKey): string | undefined {
    return localErrors[key] ?? serverFields[key];
  }

  const currentService = endpoint?.service ?? null;
  const currentIpAddress = endpoint?.ip_address ?? null;

  return (
    <form onSubmit={handleSubmit} noValidate>
      {isCreate ? (
        <div className="form-field">
          <label htmlFor="service-endpoint-service">
            service（所属服务，必填；创建后不可更改）
          </label>
          <select
            id="service-endpoint-service"
            name="service"
            value={values.service}
            onChange={(event) => changeService(event.target.value)}
            disabled={submitting}
          >
            <option value="">请选择服务…</option>
            {services.some((item) => item.id === ownerService.id) || (
              <option value={ownerService.id}>
                {ownerService.name}（{ownerService.resource.hostname}；当前面板服务）
              </option>
            )}
            {services.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}（{item.resource.hostname}）
              </option>
            ))}
          </select>
          {(serviceError ?? serverFields.service) && (
            <p className="field-error" role="alert">
              {serviceError ?? serverFields.service}
            </p>
          )}
        </div>
      ) : (
        <div className="form-field">
          <label htmlFor="service-endpoint-service-readonly">
            service（所属服务，创建后不可更改）
          </label>
          <output id="service-endpoint-service-readonly" className="mono">
            {currentService !== null
              ? `${currentService.name}（${currentService.resource.hostname}）`
              : "未知（服务引用缺失）"}
          </output>
          {serverFields.service && (
            <p className="field-error" role="alert">
              {serverFields.service}
            </p>
          )}
        </div>
      )}

      {isCreate ? (
        <div className="form-field">
          <label htmlFor="service-endpoint-ip-address">
            ip_address（引用 IP，必填；创建后不可更改；须已绑定该服务所属资源的接口）
          </label>
          <select
            id="service-endpoint-ip-address"
            name="ip_address"
            value={values.ipAddress}
            onChange={(event) => setField("ipAddress", event.target.value)}
            disabled={submitting || values.service === "" || ipOptions.kind !== "success"}
          >
            <option value="">
              {ipOptions.kind === "success" && ipOptions.options.length === 0
                ? "无候选 IP（该资源无已绑定未删除的 IP）"
                : "请选择 IP 地址…"}
            </option>
            {ipOptions.kind === "success" &&
              ipOptions.options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.address}（接口 {option.interfaceName} · 网络 {option.networkName}）
                </option>
              ))}
          </select>
          {(ipAddressError ?? serverFields.ip_address) && (
            <p className="field-error" role="alert">
              {ipAddressError ?? serverFields.ip_address}
            </p>
          )}
          {ipOptions.kind === "idle" && (
            <p className="permissions-note">请先选择服务，再选择其归属资源上已绑定的 IP。</p>
          )}
          {ipOptions.kind === "loading" && (
            <p className="status status-loading">正在加载候选 IP（该服务所属资源的接口与已绑定 IP）…</p>
          )}
          {ipOptions.kind === "error" && (
            <div className="status status-error" role="alert">
              <p>加载候选 IP 失败：{ipOptions.message}</p>
              <button
                type="button"
                onClick={() => setIpReloadToken((token) => token + 1)}
                disabled={submitting}
              >
                重试
              </button>
            </div>
          )}
          {ipOptions.kind === "success" && ipOptions.truncated && (
            <p className="status status-empty">
              候选 IP 列表超过单页上限 100，仅显示前 {ipOptions.options.length} 条；服务端仍按全量校验归属与唯一。
            </p>
          )}
        </div>
      ) : (
        <div className="form-field">
          <label htmlFor="service-endpoint-ip-address-readonly">
            ip_address（引用 IP，创建后不可更改）
          </label>
          <output id="service-endpoint-ip-address-readonly" className="mono">
            {currentIpAddress !== null
              ? `${currentIpAddress.address}（接口 ${currentIpAddress.interface.name} · 网络 ${currentIpAddress.network.name}）`
              : "未知（IP 引用缺失）"}
          </output>
          {serverFields.ip_address && (
            <p className="field-error" role="alert">
              {serverFields.ip_address}
            </p>
          )}
        </div>
      )}

      <div className="form-field">
        <label htmlFor="service-endpoint-protocol">
          protocol（必填；仅 TCP / UDP 大写规范值）
        </label>
        <select
          id="service-endpoint-protocol"
          name="protocol"
          value={values.protocol}
          onChange={(event) => setField("protocol", event.target.value as EndpointProtocol)}
          disabled={submitting}
        >
          <option value="TCP">TCP</option>
          <option value="UDP">UDP</option>
        </select>
        {fieldError("protocol") && (
          <p className="field-error" role="alert">
            {fieldError("protocol")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="service-endpoint-port">port（必填；整数 1–65535，含端点）</label>
        <input
          id="service-endpoint-port"
          name="port"
          type="text"
          value={values.port}
          onChange={(event) => setField("port", event.target.value)}
          disabled={submitting}
          placeholder="如 6818；0、65536、负数、小数均非法（服务端同样校验）"
        />
        {fieldError("port") && (
          <p className="field-error" role="alert">
            {fieldError("port")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="service-endpoint-description">description（描述，可选）</label>
        <textarea
          id="service-endpoint-description"
          name="description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          placeholder="可选，无长度上限；编辑时清空表示删除描述（显式置 null）"
        />
        {serverFields.description && (
          <p className="field-error" role="alert">
            {serverFields.description}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div className="form-error status status-error" role="alert">
          <p>
            {serverError.message}
            {serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}
          </p>
          {unmappedServerFields.length > 0 && (
            <ul>
              {unmappedServerFields.map(({ path, message }) => (
                <li key={path}>
                  {path}：{message}
                </li>
              ))}
            </ul>
          )}
          {serverError.references.length > 0 && (
            <ul>
              {serverError.references.map((reference) => (
                <li key={`${reference.object_type}-${reference.object_id}`}>
                  引用对象：{reference.label ?? reference.object_id}（{reference.object_type}）
                </li>
              ))}
            </ul>
          )}
          {serverError.dependencyConflicts.length > 0 && (
            <ul>
              {serverError.dependencyConflicts.map((conflict) => (
                <li key={`${conflict.object_type}-${conflict.object_id}`}>
                  {conflict.object_type === "service"
                    ? `所属服务（${conflict.object_id}）仍处于已删除状态或已不存在`
                    : conflict.object_type === "ip_address"
                      ? `引用的 IP 地址（${conflict.object_id}）仍处于已删除状态或已不存在`
                      : conflict.object_type === "interface"
                        ? `IP 绑定的接口（${conflict.object_id}）仍处于已删除状态或已不存在`
                        : `依赖对象 ${conflict.object_type}（${conflict.object_id}）仍处于已删除状态`}
                </li>
              ))}
            </ul>
          )}
          {serverError.versionConflict && onRefresh && (
            <p>
              <button type="button" onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </button>
            </p>
          )}
        </div>
      )}

      <div className="form-actions">
        <button type="submit" disabled={submitting}>
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </button>
        <button type="button" onClick={onCancel} disabled={submitting}>
          取消
        </button>
      </div>
    </form>
  );
}
