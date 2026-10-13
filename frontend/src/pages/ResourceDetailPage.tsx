import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Modal,
  Spin,
  Table,
  Tag,
  type DescriptionsProps,
  type TableProps,
} from "antd";
import type { User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import {
  deleteResource,
  describeResourceActionError,
  getResource,
  listResources,
  restoreResource,
  updateResource,
  type Hardware,
  type Resource,
  type ResourceActionError,
  type ResourceListResponse,
  type ResourceStatus,
  type UpdateResourcePayload,
  type VirtualMachine,
} from "../api/resources";
import ResourceForm, { type ResourceFormValues } from "../components/ResourceForm";
import InterfacesPanel from "../components/InterfacesPanel";
import ServicesPanel from "../components/ServicesPanel";
import { parseMetadataText } from "../components/ClusterForm";
import { buildHardwarePatch, parseHardwareFormValues } from "../components/hardware";
import {
  buildVirtualMachinePatch,
  parseVirtualMachineFormValues,
} from "../components/virtualMachine";

interface ResourceDetailPageProps {
  resourceId: string;
  /** 入口上下文是否为已删除对象（已删详情需显式 deleted=true，Contract §5）。 */
  initialDeleted: boolean;
  user: User;
  onBack: () => void;
  /** 关系跳转：打开另一资源详情（VM ↔ Host；携带 deleted 上下文）。 */
  onOpenResource: (id: string, deleted: boolean) => void;
}

/** 资源状态徽标配色（沿用旧版 badge-idle/alloc/down/unknown 的绿/蓝/红/灰）。 */
const STATUS_TAG_COLOR: Record<ResourceStatus, string> = {
  IDLE: "success",
  ALLOC: "processing",
  DOWN: "error",
  UNKNOWN: "default",
};

/** F017：详情区块标题（Tailwind 替代旧 .detail-section-title；首个区块不加 mt-6）。 */
function SectionTitle({ children, first = false }: { children: ReactNode; first?: boolean }) {
  return (
    <h3 className={`${first ? "" : "mt-6"} mb-1 text-base font-semibold text-gray-900`}>
      {children}
    </h3>
  );
}

/** F017：JSON 展示块（Tailwind 替代旧 .json-block）。 */
function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="m-0 max-w-full overflow-x-auto rounded-md border border-gray-200 bg-gray-50 px-3 py-2 font-mono text-sm">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

type DetailState =
  | { kind: "loading" }
  | { kind: "success"; resource: Resource }
  | { kind: "error"; message: string };

/** 详情加载失败文案（404 不泄露存在性细节，Contract §1.2/§5）。 */
function detailLoadErrorMessage(error: unknown): string {
  if (isApiError(error)) {
    if (error.status === 404) {
      return "资源不存在，或已删除且您无权查看（NOT_FOUND）。";
    }
    if (error.status === 403) {
      return "没有权限查看该资源（可能缺少查看已删除对象的权限，FORBIDDEN）。";
    }
    return displayError(error);
  }
  return "无法连接服务器，请稍后重试";
}

/**
 * CONFLICT reference_exists 单条引用的呈现文案（F006 DR-62：Resource 的
 * 引用来源为未删除的虚拟机，object_type="resource"，label=VM hostname）。
 * 未知 object_type 原样展示，不伪装成已知类型。
 */
function referenceItemText(reference: {
  object_type: string;
  label: string | null;
}): string {
  const typeText =
    reference.object_type === "resource" ? "虚拟机（VM）" : reference.object_type;
  return reference.label ? `${typeText}：${reference.label}` : typeText;
}

/**
 * CONFLICT dependency_deleted 单条冲突的呈现文案（按 object_type 区分：
 * F004 所属 Cluster 仍软删；F006 恢复 VM 时宿主机 Host 仍软删 / 缺失，DR-63）。
 * 恢复均不覆盖新对象；未知 object_type 用通用文案。
 */
function conflictItemText(conflict: { object_type: string; object_id: string }): string {
  if (conflict.object_type === "cluster") {
    return `所属集群（${conflict.object_id}）仍处于已删除状态，需先恢复该集群后再恢复资源。`;
  }
  if (conflict.object_type === "resource") {
    return `宿主机（Host，${conflict.object_id}）仍处于已删除状态或已不存在；需先恢复宿主机后再恢复该虚拟机（恢复不会覆盖宿主机或其上新对象）。`;
  }
  return `依赖对象 ${conflict.object_type}（${conflict.object_id}）仍处于已删除状态，需先恢复该依赖对象。`;
}

/**
 * 构造 PATCH body（Contract §6.4）：仅携带变化字段（省略 = 保持原值不重置）。
 * description 变化时：空文本 → 显式 null（清空）；metadata 整值替换。
 * cluster / resource_type 不可改（表单只读展示，不上送）。
 * hardware（F005，仅 BARE_METAL）：子字段级 exclude_unset 镜像——
 * 省略 = 保持原值；清空输入 → 显式 null（清空该子字段）；VM 不携带 hardware 键。
 * virtual_machine（F006，仅 VIRTUAL_MACHINE）：子字段级 exclude_unset 镜像——
 * 容量 / hypervisor 清空输入 → 显式 null；host_resource_id 变化 = 换 Host
 * （服务端校验同 Cluster 未删除 BARE_METAL）；BARE_METAL 不携带该键。
 * 无任何变化返回 null（由调用方提示，不发起空更新）。
 */
function buildUpdatePayload(
  resource: Resource,
  values: ResourceFormValues,
): UpdateResourcePayload | null {
  const payload: UpdateResourcePayload = { version: resource.version };
  let changed = false;

  if (values.hostname !== resource.hostname) {
    payload.hostname = values.hostname;
    changed = true;
  }
  if (values.role !== resource.role) {
    payload.role = values.role;
    changed = true;
  }
  if (values.status !== resource.status) {
    payload.status = values.status;
    changed = true;
  }
  if (values.description !== (resource.description ?? "")) {
    payload.description = values.description === "" ? null : values.description;
    changed = true;
  }
  const metadata = parseMetadataText(values.metadata);
  // 表单提交前已本地校验为合法 JSON / 空；此处再解析一次并整值比较
  if (metadata.ok && JSON.stringify(metadata.value) !== JSON.stringify(resource.metadata)) {
    payload.metadata = metadata.value;
    changed = true;
  }
  if (resource.resource_type === "BARE_METAL") {
    // VM 不携带 hardware 键（出现即 422，DR-51）；表单本地校验已拦截非法输入
    const hardwareParsed = parseHardwareFormValues(values.hardware);
    const hardwareMetadata = parseMetadataText(values.hardware.metadata);
    if (hardwareParsed.ok && hardwareMetadata.ok) {
      const hardwarePatch = buildHardwarePatch(resource.hardware, {
        ...hardwareParsed.fields,
        metadata: hardwareMetadata.value,
      });
      if (hardwarePatch !== null) {
        payload.hardware = hardwarePatch;
        changed = true;
      }
    }
  }
  if (resource.resource_type === "VIRTUAL_MACHINE") {
    // BARE_METAL 不携带 virtual_machine 键（互斥 422）；表单本地校验已拦截非法输入
    const vmParsed = parseVirtualMachineFormValues(values.virtual_machine);
    if (vmParsed.ok) {
      const vmPatch = buildVirtualMachinePatch(resource.virtual_machine, vmParsed.fields);
      if (vmPatch !== null) {
        payload.virtual_machine = vmPatch;
        changed = true;
      }
    }
  }

  return changed ? payload : null;
}

/** hardware 未知值占位（Contract §2.4：未知存 null，不以 0 代替）。 */
function hardwareUnknown(): ReactNode {
  return <span className="text-gray-400">—（未知）</span>;
}

/** 字符串字段：null / 缺失 → 占位，绝不伪装成空串。 */
function hardwareText(value: string | null | undefined): ReactNode {
  return value ?? hardwareUnknown();
}

/** 数值字段：null / 缺失 → 占位，绝不以 0 代替（gpu_count=0 另有专门文案）。 */
function hardwareNumber(
  value: number | null | undefined,
  render: (value: number) => string = (n) => String(n),
): ReactNode {
  if (value === null || value === undefined) {
    return hardwareUnknown();
  }
  return render(value);
}

/**
 * memory_mb 展示：标注 MiB 单位并给出 GiB 换算（1 GiB = 1024 MiB，
 * d01 §3；原样存储不换算，仅展示层换算）。整除用 “=”，非整除为约数用 “≈”。
 */
function formatMemoryMiB(memoryMb: number): string {
  const gib = memoryMb / 1024;
  if (Number.isInteger(gib)) {
    return `${memoryMb} MiB（= ${gib} GiB）`;
  }
  const rounded = parseFloat(gib.toFixed(2));
  const gibText = rounded > 0 ? String(rounded) : gib.toFixed(3);
  return `${memoryMb} MiB（≈ ${gibText} GiB）`;
}

/**
 * Hardware 区域（F005，§18；Contract §2.4/§3）：Manufacturer / Model /
 * Serial Number / CPU Model / CPU Sockets / CPU Cores / Memory / GPU Model /
 * GPU Count + hardware.metadata 扩展。仅 BARE_METAL 渲染（VM 不渲染，
 * 由调用方保证）；未知子字段（null）显示占位，gpu_count=0 显示
 * 「0（明确无 GPU）」与 null=未知可区分；cpu_cores 文案体现物理核语义。
 */
function HardwarePanel({ hardware }: { hardware: Hardware | null }) {
  const metadataEmpty =
    hardware === null || Object.keys(hardware.metadata).length === 0;
  const items: DescriptionsProps["items"] = [
    { key: "manufacturer", label: "manufacturer（厂商）", children: hardwareText(hardware?.manufacturer) },
    { key: "model", label: "model（型号）", children: hardwareText(hardware?.model) },
    { key: "serial_number", label: "serial_number（序列号）", children: hardwareText(hardware?.serial_number) },
    { key: "cpu_model", label: "cpu_model（CPU 型号）", children: hardwareText(hardware?.cpu_model) },
    { key: "cpu_sockets", label: "cpu_sockets（CPU 插槽数）", children: hardwareNumber(hardware?.cpu_sockets) },
    {
      key: "cpu_cores",
      label: "cpu_cores（物理核心总数，不含超线程）",
      children: hardwareNumber(hardware?.cpu_cores),
    },
    {
      key: "memory_mb",
      label: "memory_mb（内存容量）",
      children: hardwareNumber(hardware?.memory_mb, formatMemoryMiB),
    },
    { key: "gpu_model", label: "gpu_model（GPU 型号）", children: hardwareText(hardware?.gpu_model) },
    {
      key: "gpu_count",
      label: "gpu_count（GPU 数量）",
      children: hardwareNumber(hardware?.gpu_count, (n) =>
        n === 0 ? "0（明确无 GPU）" : String(n),
      ),
    },
    {
      key: "hardware_metadata",
      label: "hardware.metadata（厂商特有扩展）",
      children: metadataEmpty ? (
        <span className="text-gray-400">—（无扩展数据）</span>
      ) : (
        <JsonBlock value={hardware?.metadata} />
      ),
    },
  ];
  return (
    <>
      <SectionTitle>Hardware（硬件信息）</SectionTitle>
      <Descriptions column={1} items={items} contentStyle={{ overflowWrap: "anywhere" }} />
    </>
  );
}

/** F008+ 交付的 Detail 区域（Contract §9：Hardware 随 F005、Virtual Machines 随 F006、Interfaces 随 F007、Services 随 F011 交付，其余占位）。 */
const PLACEHOLDER_AREAS: { title: string; note: string }[] = [
  { title: "IP 地址（IP）", note: "IP 地址与分配明细，后续 Feature 提供" },
];

/**
 * disk_gb 展示（Contract §2.5 / D01 §5.5）：标注 GiB 单位；0 = 明确无磁盘，
 * 与 null=未知可区分；原样展示不换算。
 */
function formatDiskGb(diskGb: number): string {
  return diskGb === 0 ? "0 GiB（明确无磁盘）" : `${diskGb} GiB`;
}

/** VM 容量 / hypervisor 字段：null → 占位，绝不以 0 代替（vcpu 同个显示）。 */
function vmNumber(
  value: number | null,
  render: (value: number) => string = (n) => String(n),
): ReactNode {
  if (value === null) {
    return <span className="text-gray-400">—（未知）</span>;
  }
  return render(value);
}

/**
 * Virtual Machine 区域（F006，§18 A16；Contract §2.5/§3）：仅 VIRTUAL_MACHINE
 * 渲染。展示宿主 Host（hostname + id；活跃 VM 的宿主必然未删，提供跳转；
 * 已删 VM 的宿主可能已删，仅展示不跳转）；容量字段标注 MiB/GiB、未知显
 * 占位非 0、disk_gb=0 显示「明确无磁盘」；hypervisor 无枚举。
 * 不含独立 metadata 键（归 Resource 公共 metadata，DR-69）。
 */
function VirtualMachinePanel({
  virtualMachine,
  resourceDeleted,
  onOpenResource,
}: {
  virtualMachine: VirtualMachine;
  resourceDeleted: boolean;
  onOpenResource: (id: string, deleted: boolean) => void;
}) {
  const items: DescriptionsProps["items"] = [
    {
      key: "host",
      label: "host（宿主机）",
      children: (
        <span>
          <span className="font-mono">{virtualMachine.host.hostname}</span>
          {!resourceDeleted && (
            <Button
              type="link"
              size="small"
              className="px-0"
              onClick={() => onOpenResource(virtualMachine.host_resource_id, false)}
            >
              查看宿主机
            </Button>
          )}
        </span>
      ),
    },
    {
      key: "host_resource_id",
      label: "host_resource_id",
      children: <span className="font-mono">{virtualMachine.host_resource_id}</span>,
    },
    { key: "vcpu", label: "vcpu（vCPU 个数）", children: vmNumber(virtualMachine.vcpu) },
    {
      key: "memory_mb",
      label: "memory_mb（内存容量）",
      children: vmNumber(virtualMachine.memory_mb, formatMemoryMiB),
    },
    {
      key: "disk_gb",
      label: "disk_gb（磁盘容量）",
      children: vmNumber(virtualMachine.disk_gb, formatDiskGb),
    },
    {
      key: "hypervisor",
      label: "hypervisor（虚拟化管理程序）",
      children: virtualMachine.hypervisor ?? <span className="text-gray-400">—（未知）</span>,
    },
  ];
  return (
    <>
      <SectionTitle>Virtual Machine（虚拟机信息）</SectionTitle>
      <Descriptions column={1} items={items} contentStyle={{ overflowWrap: "anywhere" }} />
    </>
  );
}

/** Host 下 VM 列表加载状态（分页上限 100，Contract §4）。 */
type HostVmsState =
  | { kind: "loading" }
  | { kind: "success"; data: ResourceListResponse }
  | { kind: "error"; message: string };

/**
 * Virtual Machines 区域（F006，§18 A16 / DR-67）：仅 BARE_METAL 渲染。
 * GET /resources?type=VIRTUAL_MACHINE&host_resource_id=<本资源 id>（未删除
 * VM，默认 deleted=exclude；hostname 升序）；Loading / Empty / Error 显式
 * 区分，错误可重试、绝不伪装成空列表；未知容量显占位非 0，
 * disk_gb=0 显示「明确无磁盘」；分页上限 100，超出提示总数。
 */
function HostVirtualMachinesPanel({
  hostId,
  onOpenResource,
}: {
  hostId: string;
  onOpenResource: (id: string, deleted: boolean) => void;
}) {
  const [state, setState] = useState<HostVmsState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    listResources({
      type: "VIRTUAL_MACHINE",
      host_resource_id: hostId,
      page_size: 100,
      sort: "hostname",
      order: "asc",
    })
      .then((data) => {
        if (!cancelled) {
          setState({ kind: "success", data });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        setState({
          kind: "error",
          message: isApiError(error)
            ? `${error.message}（${error.code ?? `HTTP ${error.status}`}）`
            : displayError(error),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [hostId, reloadToken]);

  /** 列定义（文案与数据口径同旧版 data-table；排序由服务端 hostname 升序保证）。 */
  const columns: TableProps<Resource>["columns"] = [
    {
      title: "hostname",
      dataIndex: "hostname",
      key: "hostname",
      render: (value: string) => <span className="font-mono">{value}</span>,
    },
    { title: "角色", dataIndex: "role", key: "role" },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: ResourceStatus) => <Tag color={STATUS_TAG_COLOR[value]}>{value}</Tag>,
    },
    {
      title: "vcpu",
      key: "vcpu",
      render: (_, vm) => vmNumber(vm.virtual_machine?.vcpu ?? null),
    },
    {
      title: "memory_mb",
      key: "memory_mb",
      render: (_, vm) =>
        vmNumber(vm.virtual_machine?.memory_mb ?? null, (n) => `${n} MiB`),
    },
    {
      title: "disk_gb",
      key: "disk_gb",
      render: (_, vm) =>
        vmNumber(vm.virtual_machine?.disk_gb ?? null, (n) =>
          n === 0 ? "0 GiB（明确无磁盘）" : `${n} GiB`,
        ),
    },
    {
      title: "hypervisor",
      key: "hypervisor",
      render: (_, vm) =>
        vm.virtual_machine?.hypervisor ?? <span className="text-gray-400">—</span>,
    },
    {
      title: "操作",
      key: "actions",
      render: (_, vm) => (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() => onOpenResource(vm.id, false)}
        >
          查看
        </Button>
      ),
    },
  ];

  return (
    <>
      <SectionTitle>Virtual Machines（虚拟机）</SectionTitle>
      {state.kind === "loading" && (
        <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
          <Spin />
          <span>正在加载该宿主机上的虚拟机…</span>
        </div>
      )}
      {state.kind === "error" && (
        <Alert
          type="error"
          showIcon
          message={`加载虚拟机列表失败：${state.message}`}
          action={
            <Button size="small" danger onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}
      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <Empty
            className="py-8"
            description="该宿主机上暂无未删除的虚拟机（非错误）。"
          />
        ) : (
          <>
            {state.data.total > state.data.items.length && (
              <Alert
                className="mb-3"
                type="info"
                showIcon
                message={`虚拟机总数 ${state.data.total} 台，仅显示前 ${state.data.items.length} 台（按 hostname 排序；列表分页上限 100）。`}
              />
            )}
            <Table<Resource>
              rowKey="id"
              size="middle"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={state.data.items}
              columns={columns}
            />
          </>
        ))}
    </>
  );
}

/** Overview 六要素（§18）：Hostname / Cluster / Type / Role / Status / Description。 */
function overviewItems(resource: Resource): DescriptionsProps["items"] {
  return [
    {
      key: "hostname",
      label: "hostname",
      children: <span className="font-mono">{resource.hostname}</span>,
    },
    {
      key: "cluster",
      label: "cluster",
      children: (
        <span>
          <span className="font-mono">{resource.cluster.code}</span> — {resource.cluster.name}
          <span className="text-gray-400">（id: {resource.cluster.id}）</span>
        </span>
      ),
    },
    {
      key: "type",
      label: "type",
      children: <span className="font-mono">{resource.resource_type}</span>,
    },
    { key: "role", label: "role", children: resource.role },
    {
      key: "status",
      label: "status",
      children: (
        <span>
          <Tag color={STATUS_TAG_COLOR[resource.status]}>{resource.status}</Tag>
          {resource.deleted_at !== null && (
            <Tag color="red" className="ml-2">
              已删除
            </Tag>
          )}
        </span>
      ),
    },
    {
      key: "description",
      label: "description",
      children: resource.description ?? <span className="text-gray-400">未设置（null）</span>,
    },
  ];
}

/** 系统信息（metadata / version / created_at / updated_at / deleted_at）。 */
function systemItems(resource: Resource): DescriptionsProps["items"] {
  return [
    { key: "metadata", label: "metadata", children: <JsonBlock value={resource.metadata} /> },
    { key: "version", label: "version", children: resource.version },
    {
      key: "created_at",
      label: "created_at",
      children: <span className="font-mono">{resource.created_at}</span>,
    },
    {
      key: "updated_at",
      label: "updated_at",
      children: <span className="font-mono">{resource.updated_at}</span>,
    },
    {
      key: "deleted_at",
      label: "deleted_at",
      children:
        resource.deleted_at !== null ? (
          <span className="font-mono">{resource.deleted_at}</span>
        ) : (
          <span className="text-gray-400">未删除（null）</span>
        ),
    },
  ];
}

/**
 * F004 资源详情页（Contract §3/§5/§6.3–§6.6，§9 业务边界）+ F005 Hardware 区域
 * + F006 Virtual Machines 区域 + F007 Interfaces 区域：
 * - Overview 六要素：Hostname / Cluster / Type / Role / Status / Description
 *   （§18）；Hardware 区域仅 BARE_METAL 渲染（F005；VM 不渲染），
 *   Virtual Machines 区域：VM 详情展示其 Host（F006 A16）、BARE_METAL 详情
 *   经 host_resource_id 过滤列出其 VM（DR-67，Loading/Empty/Error）；
 *   Interfaces 区域（F007，A19）：GET /api/v1/interfaces?resource_id=<id>
 *   列出接口（name/type/mac/speed/mtu/enabled，未知「—」非 0）+ 创建/编辑/
 *   删除/恢复（DR-84）；Services 区域（F011，§18）：GET /api/v1/
 *   services?resource_id=<id> 只读列出该资源的服务登记（管理入口在 Services
 *   页面）；IP 区域占位（F008+；IP/Network 聚合列归 F013）；
 * - 编辑：PATCH 带 version；仅变化字段；cluster / resource_type 不可改（只读展示）；
 *   409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）；
 * - 删除（软删，DELETE_OBJECT）：需确认，409 VERSION_CONFLICT / reference_exists
 *   （宿主机被未删除 VM 引用，DR-62）明确呈现；
 * - 恢复（RESTORE）：需确认，带 version；409 not_deleted / unique_conflict /
 *   dependency_deleted（所属 Cluster 仍软删或宿主机 Host 仍软删 / 缺失，DR-63）
 *   明确呈现；
 * - 操作按钮按服务端返回的 permissions 显示，隐藏不替代鉴权（服务端仍 403/404）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用与参数 / 详情各区域 /
 * 编辑与删除恢复流程 / 软删 / 权限门控 / 四态 / 文案均保持不变）。原行内二次确认
 * 改为 Modal：确认框开启期间错误（含引用列表、依赖冲突列表、版本冲突刷新按钮）
 * 在框内呈现，取消后仍保留在操作区，行为口径同迁移前（失败后确认框保持待确认状态）。
 */
export default function ResourceDetailPage({
  resourceId,
  initialDeleted,
  user,
  onBack,
  onOpenResource,
}: ResourceDetailPageProps) {
  const canWrite = user.permissions.includes("WRITE");
  const canDelete = user.permissions.includes("DELETE_OBJECT");
  const canRestore = user.permissions.includes("RESTORE");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  // 已删对象的详情必须显式 deleted=true（Contract §5）；删除成功后切换为 true
  const [deletedFlag, setDeletedFlag] = useState(initialDeleted);
  const [state, setState] = useState<DetailState>({ kind: "loading" });
  const [mode, setMode] = useState<"view" | "edit">("view");
  const [formKey, setFormKey] = useState(0); // 版本冲突刷新后重置表单（载入最新数据）
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<ResourceActionError | null>(null);
  const [action, setAction] = useState<"delete" | "restore" | null>(null); // 二次确认中
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<ResourceActionError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    getResource(resourceId, { deleted: deletedFlag })
      .then(({ resource }) => {
        if (!cancelled) {
          setState({ kind: "success", resource });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ kind: "error", message: detailLoadErrorMessage(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [resourceId, deletedFlag, reloadToken]);

  // ---- 编辑（PATCH，Contract §6.4）----

  function handleEditSubmit(values: ResourceFormValues) {
    if (state.kind !== "success") {
      return;
    }
    const payload = buildUpdatePayload(state.resource, values);
    if (payload === null) {
      setFormError({
        message: "没有检测到修改内容：请修改至少一个字段后再保存。",
        code: null,
        versionConflict: false,
        currentVersion: null,
        fields: {},
        references: [],
        conflicts: [],
      });
      return;
    }
    setSubmitting(true);
    setFormError(null);
    updateResource(state.resource.id, payload)
      .then(({ resource: updated }) => {
        setMode("view"); // Success：展示新版本数据（version+1）
        setState({ kind: "success", resource: updated });
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT → 表单内提示刷新后重改；409/422/403/404 明确呈现
        setFormError(describeResourceActionError(error));
      })
      .finally(() => {
        setSubmitting(false);
      });
  }

  /** 版本冲突后的“刷新最新数据”：重载详情并重置表单（放弃本地未保存修改，重做）。 */
  function refreshAfterConflict() {
    setFormError(null);
    setReloadToken((token) => token + 1);
    setFormKey((key) => key + 1);
  }

  // ---- 删除（软删，Contract §6.5）----

  function requestDelete() {
    setActionError(null);
    setAction("delete");
  }

  function confirmDelete() {
    if (state.kind !== "success") {
      return;
    }
    const resource = state.resource;
    setActionBusy(true);
    setActionError(null);
    deleteResource(resource.id, resource.version)
      .then(() => {
        // 204：软删成功（不级联）。若具 VIEW_DELETED 则切到已删视图展示结果
        setAction(null);
        setMode("view");
        if (canViewDeleted) {
          setDeletedFlag(true);
          setReloadToken((token) => token + 1);
        } else {
          onBack();
        }
      })
      .catch((error: unknown) => {
        // 409 VERSION_CONFLICT → 刷新后重试；409 CONFLICT reference_exists → 展示引用
        setActionError(describeResourceActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // ---- 恢复（Contract §6.6）----

  function requestRestore() {
    setActionError(null);
    setAction("restore");
  }

  function confirmRestore() {
    if (state.kind !== "success") {
      return;
    }
    const resource = state.resource;
    setActionBusy(true);
    setActionError(null);
    restoreResource(resource.id, resource.version)
      .then(({ resource: restored }) => {
        // 200：deleted_at=null、version+1；仅恢复自身不级联
        setAction(null);
        setDeletedFlag(false);
        setState({ kind: "success", resource: restored });
      })
      .catch((error: unknown) => {
        // 409 not_deleted / VERSION_CONFLICT / unique_conflict / dependency_deleted
        setActionError(describeResourceActionError(error));
      })
      .finally(() => {
        setActionBusy(false);
      });
  }

  // 操作错误提示（AntD Alert 自带 role="alert"）：确认框开启期间渲染在 Modal 内，
  // 取消确认后保留在操作区展示（同迁移前的呈现位置与文案）
  const actionErrorAlert = actionError ? (
    <Alert
      type="error"
      showIcon
      message={actionError.message}
      description={
        actionError.references.length > 0 ||
        actionError.conflicts.length > 0 ||
        actionError.versionConflict ? (
          <>
            {actionError.references.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.references.map((reference) => (
                  <li key={`${reference.object_type}-${reference.object_id}`}>
                    {referenceItemText(reference)}（{reference.object_id}）
                  </li>
                ))}
              </ul>
            )}
            {actionError.conflicts.length > 0 && (
              <ul className="mt-1 list-disc pl-5">
                {actionError.conflicts.map((conflict) => (
                  <li key={`${conflict.object_type}-${conflict.object_id}`}>
                    {conflictItemText(conflict)}
                  </li>
                ))}
              </ul>
            )}
            {actionError.versionConflict && (
              <Button
                className="mt-2"
                onClick={() => {
                  setActionError(null);
                  setReloadToken((token) => token + 1);
                }}
                disabled={actionBusy}
              >
                刷新最新数据
              </Button>
            )}
          </>
        ) : undefined
      }
    />
  ) : null;

  // 二次确认框的可见口径同迁移前的行内确认块：仅 Success + 查看模式渲染
  const confirmVisible = state.kind === "success" && mode === "view";

  // 删除确认文案（BARE_METAL 追加 VM 引用拒绝说明，口径同迁移前行内确认块）
  const deleteConfirmTitle = `确认软删除该资源？（不级联删除关联对象；软删后同集群 hostname 可被新资源复用${
    state.kind === "success" && state.resource.resource_type === "BARE_METAL"
      ? "；若仍有未删除的虚拟机（VM）引用本宿主机，将被拒绝并到引用列表）"
      : ")"
  }`;

  return (
    <>
      <Card
        className="mt-6"
        title="资源详情"
        extra={
          <Button htmlType="button" onClick={onBack}>
            返回列表
          </Button>
        }
      >
        {state.kind === "loading" && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
            <Spin />
            <span>正在加载资源详情…</span>
          </div>
        )}

        {state.kind === "error" && (
          <Alert
            type="error"
            showIcon
            message={`加载资源详情失败：${state.message}`}
            action={
              <Button size="small" danger onClick={() => setReloadToken((token) => token + 1)}>
                重试
              </Button>
            }
          />
        )}

        {state.kind === "success" && mode === "view" && (
          <>
            <SectionTitle first>Overview</SectionTitle>
            <Descriptions
              column={1}
              items={overviewItems(state.resource)}
              contentStyle={{ overflowWrap: "anywhere" }}
            />

            {state.resource.resource_type === "BARE_METAL" && (
              <HardwarePanel hardware={state.resource.hardware} />
            )}

            {state.resource.resource_type === "BARE_METAL" && (
              <HostVirtualMachinesPanel hostId={state.resource.id} onOpenResource={onOpenResource} />
            )}

            {state.resource.resource_type === "VIRTUAL_MACHINE" &&
              (state.resource.virtual_machine !== null ? (
                <VirtualMachinePanel
                  virtualMachine={state.resource.virtual_machine}
                  resourceDeleted={state.resource.deleted_at !== null}
                  onOpenResource={onOpenResource}
                />
              ) : (
                // 防御：契约 VM 响应必含 virtual_machine（§3）；null 仅在旧版后端出现
                <div className="mt-6">
                  <Alert
                    type="warning"
                    showIcon
                    message="该资源为虚拟机，但服务器未返回 virtual_machine 明细（可能后端版本过旧，Contract v3+）。"
                  />
                </div>
              ))}

            <div className="mt-6">
              <InterfacesPanel resource={state.resource} user={user} />
            </div>

            <div className="mt-6">
              <ServicesPanel resource={state.resource} user={user} />
            </div>

            <SectionTitle>系统信息</SectionTitle>
            <Descriptions
              column={1}
              items={systemItems(state.resource)}
              contentStyle={{ overflowWrap: "anywhere" }}
            />

            <SectionTitle>明细区域</SectionTitle>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-3">
              {PLACEHOLDER_AREAS.map((area) => (
                <div
                  key={area.title}
                  className="rounded-md border border-dashed border-gray-300 bg-gray-50 px-3.5 py-3 text-gray-500"
                >
                  <strong className="text-sm text-gray-700">{area.title}</strong>
                  <p className="mt-1 text-sm">{area.note}</p>
                </div>
              ))}
            </div>

            <div className="mt-6 flex flex-col gap-4">
              {action === null && actionErrorAlert}

              {action === null && (
                <div className="flex flex-wrap gap-3">
                  {canWrite && state.resource.deleted_at === null && (
                    <Button
                      onClick={() => {
                        setFormError(null);
                        setMode("edit");
                      }}
                    >
                      编辑
                    </Button>
                  )}
                  {canDelete && state.resource.deleted_at === null && (
                    <Button danger onClick={requestDelete}>
                      删除资源
                    </Button>
                  )}
                  {canRestore && state.resource.deleted_at !== null && (
                    <Button onClick={requestRestore}>恢复资源</Button>
                  )}
                </div>
              )}
            </div>
          </>
        )}

        {state.kind === "success" && mode === "edit" && (
          <ResourceForm
            key={formKey}
            mode="edit"
            resource={state.resource}
            submitting={submitting}
            serverError={formError}
            onSubmit={handleEditSubmit}
            onCancel={() => setMode("view")}
            onRefresh={refreshAfterConflict}
          />
        )}
      </Card>

      {/* 删除二次确认（软删，Contract §6.5）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action === "delete" && confirmVisible}
        title={deleteConfirmTitle}
        okText={actionBusy ? "正在删除…" : "确认删除"}
        okButtonProps={{ danger: true }}
        cancelText="取消"
        cancelButtonProps={{ disabled: actionBusy }}
        confirmLoading={actionBusy}
        maskClosable={false}
        keyboard={false}
        onOk={confirmDelete}
        onCancel={() => {
          if (!actionBusy) {
            setAction(null);
          }
        }}
      >
        {actionErrorAlert}
      </Modal>

      {/* 恢复二次确认（RESTORE，Contract §6.6）：失败不自动关闭，错误在框内呈现 */}
      <Modal
        open={action === "restore" && confirmVisible}
        title="确认恢复该资源？（恢复自身，不级联；将重检同集群 hostname 唯一性与所属集群有效性；version 递增）"
        okText={actionBusy ? "正在恢复…" : "确认恢复"}
        cancelText="取消"
        cancelButtonProps={{ disabled: actionBusy }}
        confirmLoading={actionBusy}
        maskClosable={false}
        keyboard={false}
        onOk={confirmRestore}
        onCancel={() => {
          if (!actionBusy) {
            setAction(null);
          }
        }}
      >
        {actionErrorAlert}
      </Modal>
    </>
  );
}
