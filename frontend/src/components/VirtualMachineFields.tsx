import { useEffect, useState } from "react";
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

  return (
    <>
      <h3 className="detail-section-title">
        virtual_machine（虚拟机信息；仅 VIRTUAL_MACHINE）
      </h3>
      <p className="status status-empty">
        host_resource_id 必填（同集群内未删除的 BARE_METAL）；容量字段可选：
        留空 = 未知（null，不以 0 代替；编辑时清空 = 清除登记）；
        disk_gb 填 0 表示明确无磁盘；memory_mb 单位 MiB、disk_gb 单位 GiB，原样存储不换算。
      </p>
      {serverFields.virtual_machine && (
        <p className="field-error" role="alert">
          {serverFields.virtual_machine}
        </p>
      )}

      <div className="form-field">
        <label htmlFor="resource-vm-host">
          host_resource_id（宿主机 Host，必填；同集群未删除的 BARE_METAL）
        </label>
        {hostOptions.kind === "idle" && (
          <p className="status status-empty">请先选择所属集群，再选择宿主机。</p>
        )}
        {hostOptions.kind === "loading" && (
          <p className="status status-loading">正在加载宿主机列表…</p>
        )}
        {hostOptions.kind === "error" && (
          <div className="status status-error" role="alert">
            <p>加载宿主机列表失败：{hostOptions.message}</p>
            <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </button>
          </div>
        )}
        {hostOptions.kind === "success" && hosts.length === 0 && (
          <p className="status status-empty">
            该集群暂无未删除的 BARE_METAL 资源：需先登记物理机，才能创建虚拟机。
          </p>
        )}
        <select
          id="resource-vm-host"
          name="virtual_machine.host_resource_id"
          value={values.host_resource_id}
          onChange={(event) => onChange({ host_resource_id: event.target.value })}
          disabled={submitting || hostOptions.kind !== "success"}
        >
          <option value="">请选择宿主机</option>
          {currentHostMissing && currentHost !== null && (
            <option value={currentHost.id}>{currentHost.hostname}（当前宿主）</option>
          )}
          {hosts.map((host) => (
            <option key={host.id} value={host.id}>
              {host.hostname}
            </option>
          ))}
        </select>
        {hostOptions.kind === "success" && hostOptions.total > hosts.length && (
          <p className="status status-empty">
            宿主机总数 {hostOptions.total} 台，下拉仅显示前 {hosts.length} 台
            （按 hostname 排序；列表分页上限 100）。
          </p>
        )}
        {(localErrors.host_resource_id ?? serverFields["virtual_machine.host_resource_id"]) && (
          <p className="field-error" role="alert">
            {localErrors.host_resource_id ?? serverFields["virtual_machine.host_resource_id"]}
          </p>
        )}
      </div>

      {VM_INPUT_FIELDS.map((field) => (
        <div className="form-field" key={field.key}>
          <label htmlFor={`resource-vm-${field.key}`}>{field.label}</label>
          <input
            id={`resource-vm-${field.key}`}
            name={`virtual_machine.${field.key}`}
            type="text"
            value={values[field.key]}
            onChange={(event) => onChange({ [field.key]: event.target.value })}
            disabled={submitting}
            placeholder={field.placeholder}
          />
          {(localErrors[field.key] ?? serverFields[`virtual_machine.${field.key}`]) && (
            <p className="field-error" role="alert">
              {localErrors[field.key] ?? serverFields[`virtual_machine.${field.key}`]}
            </p>
          )}
        </div>
      ))}
    </>
  );
}
