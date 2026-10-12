import { useEffect, useState } from "react";
import { Button, Input, Select } from "antd";
import { displayError, isApiError } from "../api/client";
import { listResources, type Resource } from "../api/resources";
import type {
  VirtualMachineFormErrors,
  VirtualMachineFormValues,
} from "./virtualMachine";

/**
 * 宿主候选列表加载状态（同 Cluster 未删除 BARE_METAL；分页上限 100，
 * Contract §4）。idle = create 模式尚未选择集群。
 */
type HostOptionsState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; hosts: Resource[]; total: number }
  | { kind: "error"; message: string };

interface VirtualMachineFieldsProps {
  /** 宿主候选所在 Cluster（create：当前所选集群；edit：资源所属集群，固定）。 */
  clusterId: string;
  /** 当前已登记宿主（edit 初始化；不在候选列表时仍展示为选项，不静默丢失）。 */
  currentHost: { id: string; hostname: string } | null;
  values: VirtualMachineFormValues;
  onChange: (patch: Partial<VirtualMachineFormValues>) => void;
  submitting: boolean;
  /** 本地校验错误（键为 virtual_machine 子字段）。 */
  localErrors: VirtualMachineFormErrors;
  /** 服务端 422 / 409 字段错误（含点路径 virtual_machine.<field>）。 */
  serverFields: Record<string, string>;
}

/**
 * 容量 / hypervisor 输入配置（Contract §2.5；渲染统一为文本输入，
 * 整数由本地校验 + 服务端严格校验）。
 */
const VM_INPUT_FIELDS: {
  key: "vcpu" | "memory_mb" | "disk_gb" | "hypervisor";
  label: string;
  placeholder: string;
}[] = [
  {
    key: "vcpu",
    label: "vcpu（vCPU 个数，可选，正整数）",
    placeholder: "如 8；留空 = 未知（null，不以 0 代替）",
  },
  {
    key: "memory_mb",
    label: "memory_mb（内存容量，可选，正整数，单位 MiB）",
    placeholder: "如 16384（= 16 GiB）；留空 = 未知；1 GiB = 1024 MiB",
  },
  {
    key: "disk_gb",
    label: "disk_gb（磁盘容量，可选，非负整数，单位 GiB）",
    placeholder: "如 100；填 0 = 明确无磁盘；留空 = 未知（null）",
  },
  {
    key: "hypervisor",
    label: "hypervisor（虚拟化管理程序，可选，无固定枚举）",
    placeholder: "如 VMware ESXi、KVM、QEMU；留空 = 未登记（null）",
  },
];

/**
 * virtual_machine 表单区（F006，Contract §2.5；仅 VIRTUAL_MACHINE 渲染）：
 * - Host 选择器：GET /resources?cluster_id=<所选集群>&type=BARE_METAL
 *   （未删除，默认 deleted=exclude；hostname 升序，分页上限 100），
 *   展示 hostname（同 Cluster 内 hostname 唯一，无需附加消歧）；
 * - Loading / Success / Empty / Error 显式区分：错误绝不伪装成空列表，
 *   可重试；空列表明确提示“需先登记物理机”；
 * - 宿主四条件（存在 / 未软删 / BARE_METAL / 同 Cluster）由服务端统一 422
 *   （field=virtual_machine.host_resource_id），前端选择器仅收敛候选；
 * - 容量字段整数严格校验（vcpu/memory_mb 正整数；disk_gb 非负，0 = 明确无
 *   磁盘）；hypervisor trim 非空 / ≤255；未知留空 = null，绝不以 0 代替；
 * - 服务端 422 点路径 virtual_machine.<field> 映射到对应输入。
 */
export default function VirtualMachineFields({
  clusterId,
  currentHost,
  values,
  onChange,
  submitting,
  localErrors,
  serverFields,
}: VirtualMachineFieldsProps) {
  const [hostOptions, setHostOptions] = useState<HostOptionsState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (clusterId === "") {
      // create 模式尚未选择集群：不发起请求，明确提示（不伪装成空列表）
      setHostOptions({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setHostOptions({ kind: "loading" });
    listResources({
      cluster_id: clusterId,
      type: "BARE_METAL",
      page_size: 100,
      sort: "hostname",
      order: "asc",
    })
      .then((data) => {
        if (!cancelled) {
          setHostOptions({ kind: "success", hosts: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setHostOptions({
            kind: "error",
            message: isApiError(error)
              ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
              : displayError(error),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [clusterId, reloadToken]);

  const hosts = hostOptions.kind === "success" ? hostOptions.hosts : [];
  const currentHostMissing =
    currentHost !== null && !hosts.some((host) => host.id === currentHost.id);

  // AntD Select 选项：保留 value="" 的占位选项，等价于原生 <option value="">
  // “请选择宿主机”，可被重新选中以清空选择（表单值仍为 "" 字符串）。
  const hostSelectOptions: { value: string; label: string }[] = [
    { value: "", label: "请选择宿主机" },
    ...(currentHostMissing && currentHost !== null
      ? [{ value: currentHost.id, label: `${currentHost.hostname}（当前宿主）` }]
      : []),
    ...hosts.map((host) => ({ value: host.id, label: host.hostname })),
  ];

  return (
    <>
      <h3 className="mt-4 text-base font-semibold text-slate-900">
        virtual_machine（虚拟机信息；仅 VIRTUAL_MACHINE）
      </h3>
      <p className="mt-1 text-sm leading-6 text-slate-500">
        host_resource_id 必填（同集群内未删除的 BARE_METAL）；容量字段可选：
        留空 = 未知（null，不以 0 代替；编辑时清空 = 清除登记）；
        disk_gb 填 0 表示明确无磁盘；memory_mb 单位 MiB、disk_gb 单位 GiB，原样存储不换算。
      </p>
      {serverFields.virtual_machine && (
        <p className="mb-1 text-sm text-red-600" role="alert">
          {serverFields.virtual_machine}
        </p>
      )}

      <div className="mb-4 flex flex-col gap-1.5">
        <label htmlFor="resource-vm-host" className="text-sm font-medium text-slate-700">
          host_resource_id（宿主机 Host，必填；同集群未删除的 BARE_METAL）
        </label>
        {hostOptions.kind === "idle" && (
          <p className="text-sm text-slate-500">请先选择所属集群，再选择宿主机。</p>
        )}
        {hostOptions.kind === "loading" && (
          <p className="text-sm text-blue-600">正在加载宿主机列表…</p>
        )}
        {hostOptions.kind === "error" && (
          <div
            className="flex flex-col items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
            role="alert"
          >
            <p>加载宿主机列表失败：{hostOptions.message}</p>
            <Button
              size="small"
              htmlType="button"
              onClick={() => setReloadToken((token) => token + 1)}
            >
              重试
            </Button>
          </div>
        )}
        {hostOptions.kind === "success" && hosts.length === 0 && (
          <p className="text-sm text-slate-500">
            该集群暂无未删除的 BARE_METAL 资源：需先登记物理机，才能创建虚拟机。
          </p>
        )}
        <Select
          id="resource-vm-host"
          className="w-full"
          placeholder="请选择宿主机"
          value={values.host_resource_id}
          onChange={(value) => onChange({ host_resource_id: value })}
          disabled={submitting || hostOptions.kind !== "success"}
          options={hostSelectOptions}
        />
        {hostOptions.kind === "success" && hostOptions.total > hosts.length && (
          <p className="text-sm text-slate-500">
            宿主机总数 {hostOptions.total} 台，下拉仅显示前 {hosts.length} 台
            （按 hostname 排序；列表分页上限 100）。
          </p>
        )}
        {(localErrors.host_resource_id ?? serverFields["virtual_machine.host_resource_id"]) && (
          <p className="text-sm text-red-600" role="alert">
            {localErrors.host_resource_id ?? serverFields["virtual_machine.host_resource_id"]}
          </p>
        )}
      </div>

      {VM_INPUT_FIELDS.map((field) => (
        <div className="mb-4 flex flex-col gap-1.5" key={field.key}>
          <label htmlFor={`resource-vm-${field.key}`} className="text-sm font-medium text-slate-700">
            {field.label}
          </label>
          <Input
            id={`resource-vm-${field.key}`}
            name={`virtual_machine.${field.key}`}
            value={values[field.key]}
            onChange={(event) => onChange({ [field.key]: event.target.value })}
            disabled={submitting}
            placeholder={field.placeholder}
          />
          {(localErrors[field.key] ?? serverFields[`virtual_machine.${field.key}`]) && (
            <p className="text-sm text-red-600" role="alert">
              {localErrors[field.key] ?? serverFields[`virtual_machine.${field.key}`]}
            </p>
          )}
        </div>
      ))}
    </>
  );
}
