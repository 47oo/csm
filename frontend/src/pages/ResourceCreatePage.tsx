import { Button } from "../components/ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState } from "../components/ui/feedback";
import { SurfaceCard } from "../components/ui/surfaces";
import { useEffect, useState } from "react";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import { listClusters, type Cluster } from "../api/clusters";
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

/** 集群下拉数据加载状态（仅未删除集群；分页上限 100，Contract §4）。 */
type ClusterOptionsState =
  | { kind: "loading" }
  | { kind: "success"; clusters: Cluster[]; total: number }
  | { kind: "error"; message: string };

/**
 * F004 资源创建页（Contract §6.2）+ F005 hardware（Contract v2 §2.4）：
 * - cluster / hostname / resource_type 必填；role 默认 OTHER、status 默认 UNKNOWN（可选）；
 * - cluster 下拉来自 GET /clusters（READ，全角色；仅未删除集群——已删集群创建必 422）；
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
  const [clusterOptions, setClusterOptions] = useState<ClusterOptionsState>({ kind: "loading" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ResourceActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setClusterOptions({ kind: "loading" });
    // page_size 上限 100（Contract §4）；集群超过 100 时下拉截断，下方提示
    listClusters({ page: 1, page_size: 100, sort: "code", order: "asc" })
      .then((data) => {
        if (!cancelled) {
          setClusterOptions({
            kind: "success",
            clusters: data.items,
            total: data.total,
          });
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setClusterOptions({
            kind: "error",
            message: isApiError(err)
              ? `${err.message}（${err.code ?? `HTTP ${err.status}`}）`
              : displayError(err),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

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

  const content = () => {
    if (!canWrite) {
      return <ErrorState message="当前账号没有创建资源的权限（WRITE，服务端鉴权为准）。" />;
    }
    if (clusterOptions.kind === "loading") {
      return <LoadingState label="正在加载可选集群…" />;
    }
    if (clusterOptions.kind === "error") {
      return (
        <ErrorState
          message={`加载集群列表失败（创建资源需选择所属集群）：${clusterOptions.message}`}
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      );
    }
    return (
      <>
        {clusterOptions.clusters.length === 0 && (
          <EmptyState description="当前没有可选集群：请先在 Clusters 中创建集群，再登记资源。" />
        )}
        {clusterOptions.total > clusterOptions.clusters.length && (
          <InfoState
            message={`集群总数 ${clusterOptions.total} 个，下拉仅显示前 ${clusterOptions.clusters.length} 个（按 code 排序；列表分页上限 100）。`}
          />
        )}
        <ResourceForm
          mode="create"
          clusters={clusterOptions.clusters}
          submitting={submitting}
          serverError={error}
          onSubmit={handleSubmit}
          onCancel={onCancel}
        />
      </>
    );
  };

  return (
    <SurfaceCard className="panel">
      <div className="table-toolbar">
        <h2>新建资源</h2>
        <Button type="button" onClick={onCancel} disabled={submitting}>
          返回列表
        </Button>
      </div>
      {content()}
    </SurfaceCard>
  );
}
