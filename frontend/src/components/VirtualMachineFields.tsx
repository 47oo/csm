import { Input } from "./ui/controls";
import { InfoState } from "./ui/feedback";
import CandidateSelect from "./CandidateSelect";
import type {
  VirtualMachineFormErrors,
  VirtualMachineFormValues,
} from "./virtualMachine";

interface VirtualMachineFieldsProps {
  /** 宿主候选所在 Cluster（create：当前所选集群；edit：资源所属集群，固定）。 */
  clusterId: string;
  /** 当前已登记宿主（edit 初始化；不在候选页时仍展示为选项，不静默丢失）。 */
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
 * virtual_machine 表单区（F006，Contract §2.5；仅 VIRTUAL_MACHINE 渲染）+
 * F041 宿主候选完整性（docs/features/F041/architecture.md §1.4 改造点 ①）：
 * - Host 选择器改用 `CandidateSelect domain="host"`（F041）：候选由
 *   GET /resources 服务端检索提供（q · cluster_id · type=BARE_METAL ·
 *   page=1 · page_size=100 · sort=hostname · order=asc，未删除默认 exclude），
 *   第 101 位及之后的宿主机可通过检索词到达；四态 / 可重试 / 超限提示由
 *   ./candidateSelectModel 派生，不再是本地一次性加载 + 三态手写；
 * - 编辑态当前宿主以 `pinned` 传入：不在当前候选页、或候选加载失败时仍作为
 *   唯一选项展示并可原值提交（DR-F041-06 / A16）；切换所属集群时清空已选
 *   宿主（DR-F041-07，避免保留跨集群宿主导致 422）；
 * - 宿主四条件（存在 / 未软删 / BARE_METAL / 同 Cluster）仍由服务端统一 422
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
  return (
    <>
      <h3 className="detail-section-title">
        virtual_machine（虚拟机信息；仅 VIRTUAL_MACHINE）
      </h3>
      <InfoState message="host_resource_id 必填（同集群内未删除的 BARE_METAL）；容量字段可选：留空 = 未知（null，不以 0 代替；编辑时清空 = 清除登记）；disk_gb 填 0 表示明确无磁盘；memory_mb 单位 MiB、disk_gb 单位 GiB，原样存储不换算。" />
      {serverFields.virtual_machine && (
        <p className="field-error" role="alert">
          {serverFields.virtual_machine}
        </p>
      )}

      <div className="form-field">
        <label htmlFor="resource-vm-host">
          host_resource_id（宿主机 Host，必填；同集群未删除的 BARE_METAL）
        </label>
        <CandidateSelect
          clusterId={clusterId}
          domain="host"
          id="resource-vm-host"
          name="virtual_machine.host_resource_id"
          onChange={(next) => onChange({ host_resource_id: next })}
          onContextChange={() => onChange({ host_resource_id: "" })}
          pinned={
            currentHost === null
              ? null
              : { id: currentHost.id, label: `${currentHost.hostname}（当前宿主）` }
          }
          placeholder="输入 hostname 检索宿主机"
          disabled={submitting}
          value={values.host_resource_id}
        />
        {(localErrors.host_resource_id ?? serverFields["virtual_machine.host_resource_id"]) && (
          <p className="field-error" role="alert">
            {localErrors.host_resource_id ?? serverFields["virtual_machine.host_resource_id"]}
          </p>
        )}
      </div>

      {VM_INPUT_FIELDS.map((field) => (
        <div className="form-field" key={field.key}>
          <label htmlFor={`resource-vm-${field.key}`}>{field.label}</label>
          <Input
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
