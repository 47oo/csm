import { Button } from "../components/ui/controls";
import { ErrorState } from "../components/ui/feedback";
import { SurfaceCard } from "../components/ui/surfaces";
import { useState } from "react";
import type { User } from "../api/auth";
import {
  createResource,
  describeResourceActionError,
  type HardwareInput,
  type Resource,
  type ResourceActionError,
  type VirtualMachineInput,
} from "../api/resources";
import ResourceForm, { type ResourceFormValues } from "../components/ResourceForm";
import { parseMetadataText } from "../components/ClusterForm";
import { buildHardwareCreateInput, parseHardwareFormValues } from "../components/hardware";
import {
  buildVirtualMachineCreateInput,
  parseVirtualMachineFormValues,
} from "../components/virtualMachine";

interface ResourceCreatePageProps {
  user: User;
  onCancel: () => void;
  /** 创建成功（201），跳转到新资源详情。 */
  onCreated: (resource: Resource) => void;
}

/**
 * F004 资源创建页（Contract §6.2）+ F005 hardware（Contract v2 §2.4）：
 * - cluster / hostname / resource_type 必填；role 默认 OTHER、status 默认 UNKNOWN（可选）；
 * - cluster 候选取自 GET /clusters（READ，全角色；仅未删除集群——已删集群创建
 *   必 422）。F041 起由 `<CandidateSelect domain="cluster">` 在字段内完成服务端
 *   检索与分页（q / page / page_size / sort / order），加载中 / 失败 / 空结果的
 *   四态与可重试、超限提示均下沉到字段级（DR-F041-04），本页不再预加载集群列表、
 *   也不再整页门控（表单常渲染）；权限门控与提交语义不变；
 * - hardware（仅 BARE_METAL）：仅携带已登记子字段（省略 → null，无默认 0）；
 *   全部留空 → 整体省略 hardware 键；VM 不提交 hardware（出现即 422，DR-51）；
 * - virtual_machine（仅 VIRTUAL_MACHINE，F006 Contract v3 §2.5）：必须携带且
 *   host_resource_id 必填（宿主选择器收敛候选，服务端校验四条件）；容量 /
 *   hypervisor 仅携带已登记值；BARE_METAL 不提交 virtual_machine（互斥 422）；
 * - 409 CONFLICT{unique_conflict} → hostname 字段级错误（软删资源不占用 hostname）；
 * - 422 VALIDATION_ERROR → details.fields 字段级错误（cluster 缺失/不存在/软删固定
 *   落 field="cluster"；hardware / virtual_machine 为点路径 <对象>.<field>）；
 *   403 → 明确提示。
 * 入口按钮已按 WRITE 隐藏；此处再显式拦截（服务端仍是权威）。
 */
export default function ResourceCreatePage({ user, onCancel, onCreated }: ResourceCreatePageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ResourceActionError | null>(null);

  function handleSubmit(values: ResourceFormValues) {
    if (!canWrite) {
      // 防御：权限数据过期等情况下明确提示，不发起注定失败的请求
      setError({
        message: "当前账号没有创建资源的权限（WRITE）。",
        code: "FORBIDDEN",
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
        conflicts: [],
      });
      return;
    }
    const metadata = parseMetadataText(values.metadata);
    if (!metadata.ok) {
      return; // 表单本地校验已拦截，防御性返回
    }
    // hardware（F005）：仅 BARE_METAL 构造；全部留空 → 省略键（等效全 null）。
    // 表单本地校验已拦截非法输入；此处再解析一次作防御。
    let hardware: HardwareInput | undefined;
    if (values.resource_type === "BARE_METAL") {
      const hardwareParsed = parseHardwareFormValues(values.hardware);
      const hardwareMetadata = parseMetadataText(values.hardware.metadata);
      if (!hardwareParsed.ok || !hardwareMetadata.ok) {
        return;
      }
      hardware = buildHardwareCreateInput({
        ...hardwareParsed.fields,
        metadata: hardwareMetadata.value,
      });
    }
    // virtual_machine（F006，Contract v3 §2.5）：仅 VIRTUAL_MACHINE 构造，且必
    // 须携带（host_resource_id 必填）；BARE_METAL 载荷不携带 virtual_machine
    // 键（互斥 422）。表单本地校验已拦截非法输入；此处再解析一次作防御。
    let virtualMachine: VirtualMachineInput | undefined;
    if (values.resource_type === "VIRTUAL_MACHINE") {
      const vmParsed = parseVirtualMachineFormValues(values.virtual_machine);
      if (!vmParsed.ok) {
        return;
      }
      virtualMachine = buildVirtualMachineCreateInput(vmParsed.fields);
    }
    setSubmitting(true);
    setError(null);
    createResource({
      cluster: values.cluster,
      hostname: values.hostname,
      resource_type: values.resource_type,
      role: values.role,
      status: values.status,
      ...(values.description.trim() === "" ? {} : { description: values.description }),
      ...(values.metadata.trim() === "" ? {} : { metadata: metadata.value }),
      ...(hardware !== undefined ? { hardware } : {}),
      ...(virtualMachine !== undefined ? { virtual_machine: virtualMachine } : {}),
    })
      .then(({ resource }) => {
        onCreated(resource); // 201 Success → 跳转详情
      })
      .catch((err: unknown) => {
        // 409 CONFLICT unique_conflict / 422（cluster / hostname 等）/ 403：明确呈现，不静默重试
        setError(describeResourceActionError(err));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  return (
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>新建资源</h2>
        <Button type="button" onClick={onCancel} disabled={submitting}>
          返回列表
        </Button>
      </div>
      {canWrite ? (
        <ResourceForm
          mode="create"
          submitting={submitting}
          serverError={error}
          onSubmit={handleSubmit}
          onCancel={onCancel}
        />
      ) : (
        <ErrorState message="当前账号没有创建资源的权限（WRITE，服务端鉴权为准）。" />
      )}
    </SurfaceCard>
  );
}
