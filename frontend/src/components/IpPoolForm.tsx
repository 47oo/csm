import { useState, type FormEvent } from "react";
import { Button, Input, Select } from "antd";
import type { Network } from "../api/networks";
import type {
  IpOccupancyConflictItem,
  IpPool,
  IpPoolActionError,
  IpPoolAllocationMode,
} from "../api/ipPools";
import {
  emptyIpPoolFormValues,
  ipPoolFormFieldFromPath,
  ipPoolFormValuesFromIpPool,
  parseIpPoolFormValues,
  type IpPoolFieldKey,
  type IpPoolFormErrors,
  type IpPoolFormValues,
  type IpPoolServerFieldKey,
} from "./ipPoolForm";

interface IpPoolFormProps {
  mode: "create" | "edit";
  /** 供选择的网络列表（父组件已加载，仅未删除；edit 模式下用于查 CIDR 本地提示）。 */
  networks: Network[];
  /** edit 模式：被编辑的地址池。 */
  ipPool?: IpPool;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeIpPoolActionError 解析后传入）。 */
  serverError: IpPoolActionError | null;
  onSubmit: (values: IpPoolFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/** 服务端字段错误经点路径映射后的键（Contract §2.3 顶层字段）。 */
type ServerFieldKey = IpPoolServerFieldKey;

/**
 * IPPool 创建 / 编辑表单（F009，Contract §2/§6.2/§6.4）：
 * - network 选择器：创建必填（仅未删除网络，服务端校验存在/未软删，422
 *   field="network"）；创建后不可改（DR-107），编辑时只读展示所属网络与 CIDR；
 *   当前网络不在候选（如已软删）时仍展示其引用，不静默丢失；
 * - name 必填（大小写不敏感、同 Network 未删唯一，软删后可复用，§2.1）；
 * - start/end 必填单个 IPv4 主机地址（不带掩码）；start ≤ end（相等为单地址池）；
 *   均属所属 Network CIDR（本地提示，服务端权威校验 422）；同 Network 未删
 *   闭区间不重叠（含共享端点）由服务端 409 range_overlap 承载；
 * - allocation_mode ∈ {MANUAL, AUTO, RESERVED} 默认 MANUAL（分配执行 F010）；
 * - description 清空 = 删除描述（显式 null）；IPPool 无 metadata（I-6）；
 * - 422 点路径经 ipPoolFormFieldFromPath 映射到对应输入，未知路径在通用
 *   错误区呈现（不静默丢弃）；409 unique_conflict → name 字段级错误；
 *   409 range_overlap → start/end 字段级错误 + 重叠池明细；
 *   409 address_in_use → 对应字段错误 + 占用数量与明细预览（conflicts_truncated
 *   提示截断）；409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）。
 */
export default function IpPoolForm({
  mode,
  networks,
  ipPool,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: IpPoolFormProps) {
  const isCreate = mode === "create";
  const [values, setValues] = useState<IpPoolFormValues>(() =>
    isCreate ? emptyIpPoolFormValues() : ipPoolFormValuesFromIpPool(ipPool ?? null),
  );
  const [localErrors, setLocalErrors] = useState<IpPoolFormErrors>({});
  const [networkError, setNetworkError] = useState<string | null>(null);

  function setField<K extends keyof IpPoolFormValues>(key: K, value: IpPoolFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  // 服务端字段错误：点路径归一到表单键；未知路径保留原文在通用错误区呈现
  const serverFields: Partial<Record<ServerFieldKey, string>> = {};
  const unmappedServerFields: { path: string; message: string }[] = [];
  for (const [path, message] of Object.entries(serverError?.fields ?? {})) {
    const key = ipPoolFormFieldFromPath(path);
    if (key !== null) {
      serverFields[key] = message;
    } else {
      unmappedServerFields.push({ path, message });
    }
  }

  // 当前所选网络的 CIDR（本地属 CIDR 提示用；编辑时网络列表缺失该网络则回退到对象展开引用）
  const selectedNetwork = networks.find((item) => item.id === values.network) ?? null;
  const networkCidr =
    selectedNetwork?.cidr ??
    (mode === "edit" && ipPool !== undefined && ipPool.network.id === values.network
      ? ipPool.network.cidr
      : null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const parsed = parseIpPoolFormValues(values, networkCidr);
    const errors: IpPoolFormErrors = parsed.ok ? {} : parsed.errors;
    const nextNetworkError =
      isCreate && values.network === ""
        ? "必须选择所属网络（服务端校验 network 存在且未删除；创建后不可更改）"
        : null;
    setLocalErrors(errors);
    setNetworkError(nextNetworkError);
    if (!parsed.ok || Object.keys(errors).length > 0 || nextNetworkError !== null) {
      return;
    }
    onSubmit(values);
  }

  const currentNetwork = ipPool?.network ?? null;
  const networkMissing =
    currentNetwork !== null && !networks.some((item) => item.id === currentNetwork.id);

  function fieldError(key: IpPoolFieldKey): string | undefined {
    return localErrors[key] ?? serverFields[key];
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      {isCreate ? (
        <div className="mb-4 flex flex-col gap-1.5">
          <label htmlFor="ip-pool-network" className="text-sm font-medium text-gray-700">
            network（所属网络，必填；创建后不可更改）
          </label>
          <Select
            id="ip-pool-network"
            className="w-full"
            status={(networkError ?? serverFields.network) ? "error" : undefined}
            value={values.network}
            onChange={(value) => setField("network", value)}
            disabled={submitting}
          >
            <Select.Option value="">请选择网络…</Select.Option>
            {networks.map((item) => (
              <Select.Option key={item.id} value={item.id}>
                {item.name}（{item.cidr}）
              </Select.Option>
            ))}
          </Select>
          {(networkError ?? serverFields.network) && (
            <p className="text-sm text-red-500" role="alert">
              {networkError ?? serverFields.network}
            </p>
          )}
        </div>
      ) : (
        <div className="mb-4 flex flex-col gap-1.5">
          <label htmlFor="ip-pool-network-readonly" className="text-sm font-medium text-gray-700">
            network（所属网络，创建后不可更改）
          </label>
          <output
            id="ip-pool-network-readonly"
            className="rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 font-mono text-sm text-gray-700"
          >
            {currentNetwork !== null
              ? `${currentNetwork.name}（${currentNetwork.cidr}）`
              : "未知（网络引用缺失）"}
            {networkMissing && (
              <span className="text-amber-600">（不在当前网络候选列表，如已软删）</span>
            )}
          </output>
          {serverFields.network && (
            <p className="text-sm text-red-500" role="alert">
              {serverFields.network}
            </p>
          )}
        </div>
      )}

      <div className="mb-4 flex flex-col gap-1.5">
        <label htmlFor="ip-pool-name" className="text-sm font-medium text-gray-700">
          name（必填；大小写不敏感，同网络未删除唯一；允许中文与内部空格，≤255）
        </label>
        <Input
          id="ip-pool-name"
          name="name"
          status={fieldError("name") ? "error" : undefined}
          value={values.name}
          onChange={(event) => setField("name", event.target.value)}
          disabled={submitting}
          placeholder="如 MGMT-自动池；与 mgmt-自动池 视为同名；已软删地址池不占用名称"
        />
        {fieldError("name") && (
          <p className="text-sm text-red-500" role="alert">
            {fieldError("name")}
          </p>
        )}
      </div>

      <div className="mb-4 flex flex-col gap-1.5">
        <label htmlFor="ip-pool-start" className="text-sm font-medium text-gray-700">
          start_address（必填；单个 IPv4 主机地址，不带掩码；须属所属网络 CIDR）
        </label>
        <Input
          id="ip-pool-start"
          name="start_address"
          status={fieldError("start_address") ? "error" : undefined}
          value={values.start_address}
          onChange={(event) => setField("start_address", event.target.value)}
          disabled={submitting}
          placeholder="如 10.0.0.10；单个 IPv4 主机地址，不带掩码；同网络未删除池范围不可重叠（含共享端点）"
        />
        {fieldError("start_address") && (
          <p className="text-sm text-red-500" role="alert">
            {fieldError("start_address")}
          </p>
        )}
      </div>

      <div className="mb-4 flex flex-col gap-1.5">
        <label htmlFor="ip-pool-end" className="text-sm font-medium text-gray-700">
          end_address（必填；单个 IPv4 主机地址；≥ start_address，相等为单地址池）
        </label>
        <Input
          id="ip-pool-end"
          name="end_address"
          status={fieldError("end_address") ? "error" : undefined}
          value={values.end_address}
          onChange={(event) => setField("end_address", event.target.value)}
          disabled={submitting}
          placeholder="如 10.0.0.100；与 start_address 相等表示单地址池"
        />
        {fieldError("end_address") && (
          <p className="text-sm text-red-500" role="alert">
            {fieldError("end_address")}
          </p>
        )}
      </div>

      <div className="mb-4 flex flex-col gap-1.5">
        <label htmlFor="ip-pool-allocation-mode" className="text-sm font-medium text-gray-700">
          allocation_mode（分配模式；RESERVED 时范围内不得存在未删除 IP，由服务端校验）
        </label>
        <Select
          id="ip-pool-allocation-mode"
          className="w-full"
          status={serverFields.allocation_mode ? "error" : undefined}
          value={values.allocation_mode}
          onChange={(value) => setField("allocation_mode", value as IpPoolAllocationMode)}
          disabled={submitting}
        >
          <Select.Option value="MANUAL">MANUAL（仅手动分配，默认）</Select.Option>
          <Select.Option value="AUTO">AUTO（允许自动与手动分配）</Select.Option>
          <Select.Option value="RESERVED">RESERVED（保留，禁止分配）</Select.Option>
        </Select>
        {serverFields.allocation_mode && (
          <p className="text-sm text-red-500" role="alert">
            {serverFields.allocation_mode}
          </p>
        )}
      </div>

      <div className="mb-4 flex flex-col gap-1.5">
        <label htmlFor="ip-pool-description" className="text-sm font-medium text-gray-700">
          description（描述，可选）
        </label>
        <Input.TextArea
          id="ip-pool-description"
          name="description"
          rows={3}
          status={fieldError("description") ? "error" : undefined}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          placeholder="可选，无长度上限；编辑时清空表示删除描述（显式置 null）"
        />
        {fieldError("description") && (
          <p className="text-sm text-red-500" role="alert">
            {fieldError("description")}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div
          className="mb-4 space-y-1 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
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
          {serverError.rangeConflicts.length > 0 && (
            <ul className="list-disc pl-5">
              {serverError.rangeConflicts.map((conflict) => (
                <li key={`${conflict.object_type}-${conflict.object_id}`}>
                  重叠地址池：
                  {conflict.label ? `${conflict.label}（` : "("}
                  {conflict.start_address} – {conflict.end_address}）
                </li>
              ))}
            </ul>
          )}
          {serverError.occupancy !== null && (
            <>
              <p>
                占用冲突共 {serverError.occupancy.count} 个未删除 IP 地址
                {serverError.occupancy.truncated
                  ? "（以下明细已被截断，仅显示前若干条；完整明细可通过 IP 地址列表查询）"
                  : "："}
              </p>
              {serverError.occupancy.conflicts.length > 0 && (
                <ul className="list-disc pl-5">
                  {serverError.occupancy.conflicts.map((item) => (
                    <li key={`${item.object_type}-${item.object_id}`}>
                      {occupancyItemText(item)}
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
          {serverError.versionConflict && onRefresh && (
            <p>
              <Button htmlType="button" onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </Button>
            </p>
          )}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button type="primary" htmlType="submit" loading={submitting} disabled={submitting}>
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </Button>
        <Button htmlType="button" onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </div>
    </form>
  );
}

/** address_in_use 明细条目文案（含未绑定；接口 / 资源引用缺失时如实展示）。 */
function occupancyItemText(item: IpOccupancyConflictItem): string {
  const parts: string[] = [item.address];
  if (item.bound) {
    parts.push(
      item.interface_id !== null ? `已绑定接口（${item.interface_id}）` : "已绑定接口",
    );
  } else {
    parts.push("未绑定接口");
  }
  if (item.resource_hostname !== null) {
    parts.push(
      item.resource_id !== null
        ? `资源 ${item.resource_hostname}（${item.resource_id}）`
        : `资源 ${item.resource_hostname}`,
    );
  } else if (item.resource_id !== null) {
    parts.push(`资源（${item.resource_id}）`);
  }
  return parts.join(" — ");
}
