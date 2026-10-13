import { useState } from "react";
import { Alert, Button, Form, Input, Select } from "antd";
import type {
  Resource,
  ResourceActionError,
  ResourceRole,
  ResourceStatus,
  ResourceType,
} from "../api/resources";
import type { Cluster } from "../api/clusters";
import { parseMetadataText } from "./ClusterForm";
import {
  hardwareFormValuesFromResource,
  parseHardwareFormValues,
  type HardwareFieldKey,
  type HardwareFormErrors,
  type HardwareFormValues,
} from "./hardware";
import VirtualMachineFields from "./VirtualMachineFields";
import {
  parseVirtualMachineFormValues,
  virtualMachineFormValuesFromResource,
  type VirtualMachineFormErrors,
  type VirtualMachineFormValues,
} from "./virtualMachine";

/** 表单原始值（均为字符串；metadata 为 JSON 文本，提交前本地校验并解析）。 */
export interface ResourceFormValues {
  /** create：所选集群 UUID（下拉选择）；edit：不可改（原值透传，不上送）。 */
  cluster: string;
  hostname: string;
  resource_type: ResourceType;
  role: ResourceRole;
  status: ResourceStatus;
  description: string;
  metadata: string;
  /**
   * hardware 表单原始值（F005，Contract §2.4；仅 BARE_METAL 使用；
   * VM 时不渲染输入且不提交 hardware 键）。解析 / 载荷构造见 ./hardware。
   */
  hardware: HardwareFormValues;
  /**
   * virtual_machine 表单原始值（F006，Contract §2.5；仅 VIRTUAL_MACHINE
   * 使用；BARE_METAL 时不渲染输入且不提交 virtual_machine 键）。
   * 解析 / 载荷构造见 ./virtualMachine；host 选择器见 ./VirtualMachineFields。
   */
  virtual_machine: VirtualMachineFormValues;
}

/** 本地校验错误（服务端 422 / 409 字段错误由 serverError.fields 呈现）。 */
interface ResourceFormLocalErrors {
  cluster?: string;
  hostname?: string;
  metadata?: string;
  /** hardware 字段级错误（F005；服务端点路径 hardware.<field> 映射到对应输入）。 */
  hardware?: HardwareFormErrors;
  /** virtual_machine 字段级错误（F006；服务端点路径 virtual_machine.<field> 映射到对应输入）。 */
  virtual_machine?: VirtualMachineFormErrors;
}

interface ResourceFormProps {
  mode: "create" | "edit";
  /** create 模式：供选择的集群列表（父组件已加载，仅未删除集群）。 */
  clusters?: Cluster[];
  /** edit 模式：被编辑的资源（cluster / resource_type 只读展示，创建后不可改，Contract §2.2）。 */
  resource?: Resource;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeResourceActionError 解析后传入）。 */
  serverError: ResourceActionError | null;
  onSubmit: (values: ResourceFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

const RESOURCE_TYPE_OPTIONS: { value: ResourceType; label: string }[] = [
  { value: "BARE_METAL", label: "BARE_METAL（物理机）" },
  { value: "VIRTUAL_MACHINE", label: "VIRTUAL_MACHINE（虚拟机）" },
];

const ROLE_OPTIONS: { value: ResourceRole; label: string }[] = [
  { value: "COMPUTE", label: "COMPUTE（计算）" },
  { value: "LOGIN", label: "LOGIN（登录）" },
  { value: "MANAGEMENT", label: "MANAGEMENT（管理）" },
  { value: "STORAGE", label: "STORAGE（存储）" },
  { value: "SERVICE", label: "SERVICE（服务）" },
  { value: "GPU", label: "GPU" },
  { value: "OTHER", label: "OTHER（其它，默认）" },
];

const STATUS_OPTIONS: { value: ResourceStatus; label: string }[] = [
  { value: "IDLE", label: "IDLE（空闲）" },
  { value: "ALLOC", label: "ALLOC（已分配）" },
  { value: "DOWN", label: "DOWN（故障）" },
  { value: "UNKNOWN", label: "UNKNOWN（未知，默认）" },
];

/**
 * hardware 输入字段配置（F005，Contract §2.4；9 字段，metadata 单独渲染为
 * JSON 文本域）。渲染统一为文本输入，整数由本地校验 + 服务端严格校验。
 */
const HARDWARE_INPUT_FIELDS: {
  key: Exclude<HardwareFieldKey, "metadata">;
  label: string;
  placeholder: string;
}[] = [
  {
    key: "manufacturer",
    label: "manufacturer（厂商，可选）",
    placeholder: "如 Dell；留空 = 未登记（null）",
  },
  {
    key: "model",
    label: "model（型号，可选）",
    placeholder: "如 PowerEdge R760；留空 = 未登记",
  },
  {
    key: "serial_number",
    label: "serial_number（序列号，可选；一期不做唯一性校验）",
    placeholder: "如 JH1234567X；相同 SN 可登记多台；留空 = 未登记",
  },
  {
    key: "cpu_model",
    label: "cpu_model（CPU 型号，可选）",
    placeholder: "如 AMD EPYC 9654；留空 = 未登记",
  },
  {
    key: "cpu_sockets",
    label: "cpu_sockets（CPU 插槽数，可选，正整数）",
    placeholder: "如 2；留空 = 未知（null，不以 0 代替）",
  },
  {
    key: "cpu_cores",
    label: "cpu_cores（CPU 物理核心总数，可选，正整数；整机总数、不含超线程）",
    placeholder: "如 192（两颗 96 核填 192，不填 384）；留空 = 未知",
  },
  {
    key: "memory_mb",
    label: "memory_mb（内存容量，可选，正整数，单位 MiB）",
    placeholder: "如 1572864（= 1536 GiB）；留空 = 未知",
  },
  {
    key: "gpu_model",
    label: "gpu_model（GPU 型号，可选）",
    placeholder: "如 NVIDIA H100；留空 = 未登记",
  },
  {
    key: "gpu_count",
    label: "gpu_count（GPU 数量，可选，非负整数；0 = 明确无 GPU）",
    placeholder: "如 8；填 0 = 明确无 GPU；留空 = 未知（null）",
  },
];

/**
 * F004 资源创建 / 编辑表单（Contract §2/§6.2/§6.4）+ F005 hardware（§2.4）：
 * - 创建：cluster / hostname / resource_type 必填（本地非空校验，服务端为最终权威）；
 *   role 默认 OTHER、status 默认 UNKNOWN（可选）；
 * - 编辑：cluster / resource_type 只读展示（不可改），仅提交变化字段（由父组件构造 PATCH body）；
 * - hostname 允许 Unicode，禁内部空白 / 控制字符，≤253（服务端归一化小写存储）；
 * - description 留空 = 创建时省略 / 编辑时清空（显式 null）；
 * - metadata 留空视为 {}，非空必须为合法 JSON 对象；
 * - hardware（F005，仅 BARE_METAL）：字符串 trim 后非空或留空（null）；整数严格
 *   校验范围（正整数 / 非负整数）；VM 时不渲染 hardware 输入且不提交 hardware 键；
 * - virtual_machine（F006，仅 VIRTUAL_MACHINE）：宿主选择器从同集群未删除
 *   BARE_METAL 列表选（展示 hostname）；容量 / hypervisor 整数与口径本地校验
 *   （vcpu/memory_mb 正整数；disk_gb 非负，0 = 明确无磁盘；留空 = null 不以 0
 *   代替）；BARE_METAL 时不渲染 virtual_machine 输入且不提交该键（互斥不共存）；
 * - 409 VERSION_CONFLICT → 明确提示刷新后重改；409 CONFLICT unique_conflict
 *   → hostname 字段级错误；422 → details.fields 字段级错误（hardware /
 *   virtual_machine 为点路径 <对象>.<field>，如 hardware.cpu_cores、
 *   virtual_machine.host_resource_id）。
 *
 * 迁移说明（AntD + Tailwind）：本地校验仍仅在提交时触发（不使用 antd rules），
 * 以保持原有行为——错误文案只在下次提交时更新，字段级错误优先级为本地 ?? 服务端。
 * cluster 下拉保留 value="" 占位选项（等价原生 <option value="">“请选择集群”），
 * 表单值仍为 "" 字符串；受控值形状（ResourceFormValues）与提交行为不变。
 */
export default function ResourceForm({
  mode,
  clusters,
  resource,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: ResourceFormProps) {
  const isCreate = mode === "create";
  const [cluster, setCluster] = useState("");
  const [hostname, setHostname] = useState(resource?.hostname ?? "");
  const [resourceType, setResourceType] = useState<ResourceType>(
    resource?.resource_type ?? "BARE_METAL",
  );
  const [role, setRole] = useState<ResourceRole>(resource?.role ?? "OTHER");
  const [status, setStatus] = useState<ResourceStatus>(resource?.status ?? "UNKNOWN");
  const [description, setDescription] = useState(resource?.description ?? "");
  const [metadataText, setMetadataText] = useState(
    resource ? JSON.stringify(resource.metadata, null, 2) : "",
  );
  // hardware 表单值：edit 从 Resource.hardware 初始化（VM 为 null → 全空）。
  // create 切换到 VM 时保留已输入值但不渲染、不提交（页面按类型构造载荷）。
  const [hardware, setHardware] = useState<HardwareFormValues>(() =>
    hardwareFormValuesFromResource(resource?.hardware ?? null),
  );
  // virtual_machine 表单值：edit 从 Resource.virtual_machine 初始化
  // （BARE_METAL 为 null → 全空）；create 切换到 BARE_METAL 时保留但不渲染、
  // 不提交。换集群时重置宿主选择（宿主必须与 VM 同 Cluster，§9）。
  const [virtualMachine, setVirtualMachine] = useState<VirtualMachineFormValues>(() =>
    virtualMachineFormValuesFromResource(resource?.virtual_machine ?? null),
  );
  const [localErrors, setLocalErrors] = useState<ResourceFormLocalErrors>({});
  // 仅 BARE_METAL 渲染 hardware 输入、仅 VIRTUAL_MACHINE 渲染 virtual_machine
  // 输入（两对象互斥不共存；edit 模式类型固定；create 随下拉切换）
  const isBareMetal = resourceType === "BARE_METAL";
  const isVirtualMachine = resourceType === "VIRTUAL_MACHINE";

  function handleSubmit() {
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const errors: ResourceFormLocalErrors = {};
    if (isCreate && cluster === "") {
      errors.cluster = "必须选择所属集群（服务端校验 cluster 存在且未删除）";
    }
    if (hostname.trim() === "") {
      errors.hostname = "hostname 不能为空（服务端会去除首尾空白后再校验）";
    }
    const metadata = parseMetadataText(metadataText);
    if (!metadata.ok) {
      errors.metadata = metadata.message;
    }
    // hardware（F005）：仅 BARE_METAL 校验（VM 不渲染输入、不提交 hardware）
    if (isBareMetal) {
      const hardwareErrors: HardwareFormErrors = {};
      const hardwareParsed = parseHardwareFormValues(hardware);
      if (!hardwareParsed.ok) {
        Object.assign(hardwareErrors, hardwareParsed.errors);
      }
      const hardwareMetadata = parseMetadataText(hardware.metadata);
      if (!hardwareMetadata.ok) {
        hardwareErrors.metadata = hardwareMetadata.message;
      }
      if (Object.keys(hardwareErrors).length > 0) {
        errors.hardware = hardwareErrors;
      }
    }
    // virtual_machine（F006）：仅 VIRTUAL_MACHINE 校验（BARE_METAL 不渲染输入、
    // 不提交 virtual_machine；宿主必选，容量 / hypervisor 口径见 ./virtualMachine）
    if (isVirtualMachine) {
      const vmParsed = parseVirtualMachineFormValues(virtualMachine);
      if (!vmParsed.ok) {
        errors.virtual_machine = vmParsed.errors;
      }
    }
    setLocalErrors(errors);
    if (Object.keys(errors).length > 0) {
      return;
    }
    onSubmit({
      cluster,
      hostname,
      resource_type: resourceType,
      role,
      status,
      description,
      metadata: metadataText,
      hardware,
      virtual_machine: virtualMachine,
    });
  }

  const serverFields = serverError?.fields ?? {};
  const clusterError = localErrors.cluster ?? serverFields.cluster;
  const hostnameError = localErrors.hostname ?? serverFields.hostname;
  const metadataError = localErrors.metadata ?? serverFields.metadata;
  const hardwareMetadataError =
    localErrors.hardware?.metadata ?? serverFields["hardware.metadata"];

  return (
    <Form
      layout="vertical"
      colon={false}
      onFinish={handleSubmit}
      noValidate
      className="space-y-4"
    >
      {isCreate ? (
        <div>
          <label htmlFor="resource-cluster" className="mb-1 block text-sm font-medium">
            cluster（所属集群，必填，创建后不可修改）
          </label>
          <Select
            id="resource-cluster"
            value={cluster}
            onChange={(value) => {
              setCluster(value);
              // 换集群后宿主候选随集群重新加载；旧宿主不再属于新集群，重置选择
              setVirtualMachine((prev) => ({ ...prev, host_resource_id: "" }));
            }}
            disabled={submitting}
            status={clusterError ? "error" : undefined}
            className="w-full"
            options={[
              { value: "", label: "请选择集群" },
              ...(clusters ?? []).map((item) => ({
                value: item.id,
                label: `${item.code} — ${item.name}`,
              })),
            ]}
          />
          {clusterError && (
            <p className="mt-1 text-sm text-red-600" role="alert">
              {clusterError}
            </p>
          )}
        </div>
      ) : (
        <div>
          <span className="mb-1 block text-sm font-medium">cluster（创建后不可修改）</span>
          <p className="break-all font-mono text-sm text-gray-900">
            {resource?.cluster.code} — {resource?.cluster.name}
            <span className="text-gray-400">（id: {resource?.cluster.id}）</span>
          </p>
        </div>
      )}

      <div>
        <label htmlFor="resource-hostname" className="mb-1 block text-sm font-medium">
          hostname（必填；允许 Unicode 与“.”，禁内部空白 / 控制字符，≤253）
        </label>
        <Input
          id="resource-hostname"
          name="hostname"
          value={hostname}
          onChange={(event) => setHostname(event.target.value)}
          disabled={submitting}
          status={hostnameError ? "error" : undefined}
          placeholder="如 cn001；服务端归一化为小写存储，同集群内唯一"
        />
        {hostnameError && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {hostnameError}
          </p>
        )}
      </div>

      {isCreate ? (
        <div>
          <label htmlFor="resource-type" className="mb-1 block text-sm font-medium">
            resource_type（必填，创建后不可修改）
          </label>
          <Select<ResourceType>
            id="resource-type"
            value={resourceType}
            onChange={(value) => setResourceType(value)}
            disabled={submitting}
            status={serverFields.resource_type ? "error" : undefined}
            className="w-full"
            options={RESOURCE_TYPE_OPTIONS}
          />
          {serverFields.resource_type && (
            <p className="mt-1 text-sm text-red-600" role="alert">
              {serverFields.resource_type}
            </p>
          )}
        </div>
      ) : (
        <div>
          <span className="mb-1 block text-sm font-medium">resource_type（创建后不可修改）</span>
          <p className="break-all font-mono text-sm text-gray-900">{resource?.resource_type}</p>
        </div>
      )}

      <div>
        <label htmlFor="resource-role" className="mb-1 block text-sm font-medium">
          role（角色，可选，默认 OTHER）
        </label>
        <Select<ResourceRole>
          id="resource-role"
          value={role}
          onChange={(value) => setRole(value)}
          disabled={submitting}
          status={serverFields.role ? "error" : undefined}
          className="w-full"
          options={ROLE_OPTIONS}
        />
        {serverFields.role && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {serverFields.role}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="resource-status" className="mb-1 block text-sm font-medium">
          status（状态，可选，默认 UNKNOWN，人工维护）
        </label>
        <Select<ResourceStatus>
          id="resource-status"
          value={status}
          onChange={(value) => setStatus(value)}
          disabled={submitting}
          status={serverFields.status ? "error" : undefined}
          className="w-full"
          options={STATUS_OPTIONS}
        />
        {serverFields.status && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {serverFields.status}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="resource-description" className="mb-1 block text-sm font-medium">
          description（描述，可选）
        </label>
        <Input.TextArea
          id="resource-description"
          name="description"
          rows={3}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          disabled={submitting}
          status={serverFields.description ? "error" : undefined}
          placeholder="可选；编辑时清空表示删除描述（显式置 null）"
        />
        {serverFields.description && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {serverFields.description}
          </p>
        )}
      </div>

      <div>
        <label htmlFor="resource-metadata" className="mb-1 block text-sm font-medium">
          metadata（JSON 对象，可选）
        </label>
        <Input.TextArea
          id="resource-metadata"
          name="metadata"
          rows={5}
          value={metadataText}
          onChange={(event) => setMetadataText(event.target.value)}
          disabled={submitting}
          status={metadataError ? "error" : undefined}
          placeholder={'可选，例如 {"rack": "R42"}；留空视为 {}'}
        />
        {metadataError && (
          <p className="mt-1 text-sm text-red-600" role="alert">
            {metadataError}
          </p>
        )}
      </div>

      {isBareMetal && (
        <>
          <div>
            <h3 className="text-base font-semibold text-slate-900">
              hardware（硬件信息，可选；仅 BARE_METAL）
            </h3>
            <p className="mt-1 text-sm leading-6 text-slate-500">
              全部字段可选：留空 = 未登记（null，不以 0 代替；编辑时留空 = 清空该字段）；
              gpu_count 填 0 表示明确无 GPU；memory_mb 单位 MiB；cpu_cores 为整机物理核心总数（不含超线程）。
            </p>
            {serverFields.hardware && (
              <p className="mt-1 text-sm text-red-600" role="alert">
                {serverFields.hardware}
              </p>
            )}
          </div>
          {HARDWARE_INPUT_FIELDS.map((field) => (
            <div key={field.key}>
              <label htmlFor={`resource-hardware-${field.key}`} className="mb-1 block text-sm font-medium">
                {field.label}
              </label>
              <Input
                id={`resource-hardware-${field.key}`}
                name={`hardware.${field.key}`}
                value={hardware[field.key]}
                onChange={(event) =>
                  setHardware((prev) => ({ ...prev, [field.key]: event.target.value }))
                }
                disabled={submitting}
                status={
                  localErrors.hardware?.[field.key] ?? serverFields[`hardware.${field.key}`]
                    ? "error"
                    : undefined
                }
                placeholder={field.placeholder}
              />
              {(localErrors.hardware?.[field.key] ?? serverFields[`hardware.${field.key}`]) && (
                <p className="mt-1 text-sm text-red-600" role="alert">
                  {localErrors.hardware?.[field.key] ?? serverFields[`hardware.${field.key}`]}
                </p>
              )}
            </div>
          ))}
          <div>
            <label htmlFor="resource-hardware-metadata" className="mb-1 block text-sm font-medium">
              hardware.metadata（厂商特有 / 低频扩展，JSON 对象，可选）
            </label>
            <Input.TextArea
              id="resource-hardware-metadata"
              name="hardware.metadata"
              rows={5}
              value={hardware.metadata}
              onChange={(event) =>
                setHardware((prev) => ({ ...prev, metadata: event.target.value }))
              }
              disabled={submitting}
              status={hardwareMetadataError ? "error" : undefined}
              placeholder={'可选，例如 {"psu": "2000W"}；留空视为 {}；与 Resource 的 metadata 相互独立（整值替换）'}
            />
            {hardwareMetadataError && (
              <p className="mt-1 text-sm text-red-600" role="alert">
                {hardwareMetadataError}
              </p>
            )}
          </div>
        </>
      )}

      {isVirtualMachine && (
        <VirtualMachineFields
          clusterId={isCreate ? cluster : (resource?.cluster.id ?? "")}
          currentHost={
            resource?.virtual_machine
              ? {
                  id: resource.virtual_machine.host_resource_id,
                  hostname: resource.virtual_machine.host.hostname,
                }
              : null
          }
          values={virtualMachine}
          onChange={(patch) => setVirtualMachine((prev) => ({ ...prev, ...patch }))}
          submitting={submitting}
          localErrors={localErrors.virtual_machine ?? {}}
          serverFields={serverFields}
        />
      )}

      {serverError && serverError.message && (
        <Alert
          type="error"
          role="alert"
          message={`${serverError.message}${
            serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""
          }`}
          description={
            serverError.versionConflict && onRefresh ? (
              <Button htmlType="button" onClick={onRefresh} disabled={submitting}>
                刷新最新数据（放弃本次未保存的修改，重做变更）
              </Button>
            ) : undefined
          }
        />
      )}

      <div className="flex gap-3">
        <Button type="primary" htmlType="submit" disabled={submitting}>
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </Button>
        <Button htmlType="button" onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </div>
    </Form>
  );
}
