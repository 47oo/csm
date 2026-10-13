import { useEffect, useState, type FormEvent } from "react";
import { Button, Checkbox, Input, Select } from "antd";
import { displayError, isApiError } from "../api/client";
import { listInterfaces, type Interface, type InterfaceActionError, type InterfaceTypeValue } from "../api/interfaces";
import { parseMetadataText } from "./ClusterForm";
import {
  emptyInterfaceFormValues,
  interfaceFormValuesFromInterface,
  parseInterfaceFormValues,
  type InterfaceFormErrors,
  type InterfaceFormValues,
} from "./interfaceForm";

/** parent 候选列表加载状态（同 Resource 未删 Interface；分页上限 100，Contract §4）。 */
type ParentOptionsState =
  | { kind: "loading" }
  | { kind: "success"; items: Interface[]; total: number }
  | { kind: "error"; message: string };

interface InterfaceFormProps {
  mode: "create" | "edit";
  /** 所属 Resource（只读展示，创建后不可改 DR-79；parent 候选来源）。 */
  resource: { id: string; hostname: string };
  /** edit 模式：被编辑的 Interface（resource / id / 只读字段不上送）。 */
  iface?: Interface;
  /** 提交中（禁用全部输入与按钮）。 */
  submitting: boolean;
  /** 服务端错误（父组件经 describeInterfaceActionError 解析后传入）。 */
  serverError: InterfaceActionError | null;
  onSubmit: (values: InterfaceFormValues) => void;
  onCancel: () => void;
  /**
   * 版本冲突（409 VERSION_CONFLICT）时的“刷新最新数据”入口，仅 edit 模式传入。
   * 刷新 = 重置表单为服务器最新值，本地未保存修改需重做（不静默重试）。
   */
  onRefresh?: () => void;
}

/** interface_type 下拉选项（Contract §2.2：7 值，默认 OTHER，不据 name 推断）。 */
const INTERFACE_TYPE_OPTIONS: { value: InterfaceTypeValue; label: string }[] = [
  { value: "PHYSICAL", label: "PHYSICAL（物理接口）" },
  { value: "VIRTUAL", label: "VIRTUAL（虚拟接口）" },
  { value: "BOND", label: "BOND（链路聚合）" },
  { value: "BRIDGE", label: "BRIDGE（网桥）" },
  { value: "VLAN", label: "VLAN（VLAN 子接口）" },
  { value: "LOOPBACK", label: "LOOPBACK（回环接口）" },
  { value: "OTHER", label: "OTHER（其它，默认）" },
];

/** 数值输入字段配置（正整数，本地校验 + 服务端严格校验）。 */
const INTERFACE_INT_FIELDS: {
  key: "speed_mbps" | "mtu";
  label: string;
  placeholder: string;
}[] = [
  {
    key: "speed_mbps",
    label: "speed_mbps（标称速率，可选，正整数，单位 Mbps）",
    placeholder: "如 25000；留空 = 未知（null，不以 0 代替）；登记值非实时探测",
  },
  {
    key: "mtu",
    label: "mtu（MTU，可选，正整数，单位字节）",
    placeholder: "如 9000；留空 = 未知（null，不以 0 代替）",
  },
];

/** Tailwind 工具类（F017：替代原 form-field / field-label / field-error / status 样式）。 */
const FIELD_CLASS = "flex flex-col gap-1.5";
const LABEL_CLASS = "text-sm font-medium text-gray-700";
const FIELD_ERROR_CLASS = "text-sm text-red-600";
const STATUS_CLASS = "text-sm text-gray-500";
const STATUS_ERROR_CLASS =
  "flex flex-col items-start gap-2 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700";

/**
 * Interface 创建 / 编辑表单（F007，Contract §2/§6.2/§6.4）：
 * - resource 只读展示（创建必填、创建后不可改，DR-79；值来自 Resource 详情
 *   上下文，不上送 resource 键——编辑载荷永不携带，服务端出现即 422）；
 * - interface_type 下拉 7 值（默认 OTHER，不据 name 推断，DR-74）；
 * - parent 选择器：GET /interfaces?resource_id=<所属资源>（未删，默认
 *   deleted=exclude；name 升序，分页上限 100），edit 模式排除自身（禁自
 *   引用）；当前父接口不在候选（如已被软删）时仍展示为选项，不静默丢失；
 *   跨 Resource / 成环由服务端 422 field="parent_interface" 承载（DR-85），
 *   前端不预判环；
 * - enabled 开关（登记状态非实时探测，默认 true）；
 * - mac/speed_mbps/mtu 口径见 ./interfaceForm（未知 = null 绝不以 0 代替）；
 * - 422 点路径（顶层字段）映射到对应输入；409 unique_conflict{field:"name"}
 *   → name 字段级错误；409 VERSION_CONFLICT → 提示刷新后重改（不静默重试）。
 */
export default function InterfaceForm({
  mode,
  resource,
  iface,
  submitting,
  serverError,
  onSubmit,
  onCancel,
  onRefresh,
}: InterfaceFormProps) {
  const isCreate = mode === "create";
  const [values, setValues] = useState<InterfaceFormValues>(() =>
    isCreate ? emptyInterfaceFormValues() : interfaceFormValuesFromInterface(iface ?? null),
  );
  const [localErrors, setLocalErrors] = useState<InterfaceFormErrors>({});
  // metadata 本地校验错误单独存放（InterfaceFormErrors 不含 metadata 键，
  // 服务端 422 field="metadata" 直接经 serverFields 呈现）
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [parentOptions, setParentOptions] = useState<ParentOptionsState>({ kind: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  // parent 候选：同 Resource 未删 Interface（默认 deleted=exclude），name 升序
  useEffect(() => {
    let cancelled = false;
    setParentOptions({ kind: "loading" });
    listInterfaces({
      resource_id: resource.id,
      page_size: 100,
      sort: "name",
      order: "asc",
    })
      .then((data) => {
        if (!cancelled) {
          setParentOptions({ kind: "success", items: data.items, total: data.total });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setParentOptions({
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
  }, [resource.id, reloadToken]);

  function setField<K extends keyof InterfaceFormValues>(key: K, value: InterfaceFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    // 本地校验（快速反馈；服务端校验仍是权威，422 会再呈现字段错误）
    const parsed = parseInterfaceFormValues(values);
    const errors: InterfaceFormErrors = parsed.ok ? {} : parsed.errors;
    const metadata = parseMetadataText(values.metadata);
    if (!metadata.ok) {
      // metadata 为 JSON 文本（复用 ClusterForm 解析）；错误呈现于 metadata 输入
      setLocalErrors(errors);
      setMetadataError(metadata.message);
      return;
    }
    setMetadataError(null);
    setLocalErrors(errors);
    if (!parsed.ok || Object.keys(errors).length > 0) {
      return;
    }
    onSubmit(values);
  }

  const serverFields = serverError?.fields ?? {};
  // edit 模式排除自身（parent 禁自引用，§2.2）；create 无自身
  const selfId = isCreate ? null : (iface?.id ?? null);
  const parentItems =
    parentOptions.kind === "success"
      ? parentOptions.items.filter((item) => item.id !== selfId)
      : [];
  const currentParent = isCreate || !iface ? null : iface.parent_interface;
  const currentParentMissing =
    currentParent !== null && !parentItems.some((item) => item.id === currentParent.id);

  function fieldError(key: keyof InterfaceFormErrors): string | undefined {
    return localErrors[key] ?? serverFields[key];
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-5">
      <div className={FIELD_CLASS}>
        <span className={LABEL_CLASS}>resource（所属资源，创建后不可修改）</span>
        <p className="font-mono text-sm text-gray-900">
          {resource.hostname}
          <span className="text-gray-400">（id: {resource.id}）</span>
        </p>
        {serverFields.resource && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {serverFields.resource}
          </p>
        )}
      </div>

      <div className={FIELD_CLASS}>
        <label htmlFor="interface-name" className={LABEL_CLASS}>
          name（必填；区分大小写保留输入，同资源内未删除唯一；禁内部空白 / 控制字符，≤64）
        </label>
        <Input
          id="interface-name"
          name="name"
          value={values.name}
          onChange={(event) => setField("name", event.target.value)}
          disabled={submitting}
          status={fieldError("name") ? "error" : undefined}
          placeholder="如 eth0；eth0 与 ETH0 为不同名称；已软删接口不占用名称"
        />
        {fieldError("name") && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {fieldError("name")}
          </p>
        )}
      </div>

      <div className={FIELD_CLASS}>
        <label htmlFor="interface-type" className={LABEL_CLASS}>
          interface_type（类型，可选，默认 OTHER；不据名称推断）
        </label>
        <Select
          id="interface-type"
          value={values.interface_type}
          onChange={(value) => setField("interface_type", value as InterfaceTypeValue)}
          disabled={submitting}
          status={serverFields.interface_type ? "error" : undefined}
          options={INTERFACE_TYPE_OPTIONS}
        />
        {serverFields.interface_type && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {serverFields.interface_type}
          </p>
        )}
      </div>

      <div className={FIELD_CLASS}>
        <label htmlFor="interface-parent" className={LABEL_CLASS}>
          parent_interface（父接口，可选；须为本资源内未删除的其它接口，留空 = 根接口）
        </label>
        {parentOptions.kind === "loading" && (
          <p className={STATUS_CLASS}>正在加载接口列表…</p>
        )}
        {parentOptions.kind === "error" && (
          <div className={STATUS_ERROR_CLASS} role="alert">
            <p>加载父接口候选失败：{parentOptions.message}</p>
            <Button size="small" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          </div>
        )}
        {parentOptions.kind === "success" && parentItems.length === 0 && (
          <p className={STATUS_CLASS}>
            本资源暂无其它未删除接口：留空即为根接口（首个接口无父）。
          </p>
        )}
        <Select
          id="interface-parent"
          value={values.parent_interface}
          onChange={(value) => setField("parent_interface", value as string)}
          disabled={submitting || parentOptions.kind !== "success"}
          status={fieldError("parent_interface") ? "error" : undefined}
          options={[
            { value: "", label: "无（根接口）" },
            ...(currentParentMissing && currentParent !== null
              ? [{ value: currentParent.id, label: `${currentParent.name}（当前父接口）` }]
              : []),
            ...parentItems.map((item) => ({
              value: item.id,
              label: `${item.name}（${item.interface_type}）`,
            })),
          ]}
        />
        {parentOptions.kind === "success" && parentOptions.total > parentOptions.items.length && (
          <p className={STATUS_CLASS}>
            接口总数 {parentOptions.total} 个，下拉仅显示前 {parentOptions.items.length} 个
            （按 name 排序；列表分页上限 100）。
          </p>
        )}
        {fieldError("parent_interface") && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {fieldError("parent_interface")}
          </p>
        )}
      </div>

      <div className={FIELD_CLASS}>
        <label htmlFor="interface-mac" className={LABEL_CLASS}>
          mac_address（MAC 地址，可选；无格式校验、保留输入大小写，≤64）
        </label>
        <Input
          id="interface-mac"
          name="mac_address"
          value={values.mac_address}
          onChange={(event) => setField("mac_address", event.target.value)}
          disabled={submitting}
          status={fieldError("mac_address") ? "error" : undefined}
          placeholder="如 00:1A:2B:3C:4D:5E；留空 = 未登记（null）；一期不做全局唯一"
        />
        {fieldError("mac_address") && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {fieldError("mac_address")}
          </p>
        )}
      </div>

      {INTERFACE_INT_FIELDS.map((field) => (
        <div className={FIELD_CLASS} key={field.key}>
          <label htmlFor={`interface-${field.key}`} className={LABEL_CLASS}>
            {field.label}
          </label>
          <Input
            id={`interface-${field.key}`}
            name={field.key}
            value={values[field.key]}
            onChange={(event) => setField(field.key, event.target.value)}
            disabled={submitting}
            status={fieldError(field.key) ? "error" : undefined}
            placeholder={field.placeholder}
          />
          {fieldError(field.key) && (
            <p className={FIELD_ERROR_CLASS} role="alert">
              {fieldError(field.key)}
            </p>
          )}
        </div>
      ))}

      <div className={FIELD_CLASS}>
        <Checkbox
          id="interface-enabled"
          checked={values.enabled}
          onChange={(event) => setField("enabled", event.target.checked)}
          disabled={submitting}
        >
          enabled（启用状态；登记值非实时探测，默认开启）
        </Checkbox>
      </div>

      <div className={FIELD_CLASS}>
        <label htmlFor="interface-description" className={LABEL_CLASS}>
          description（描述，可选）
        </label>
        <Input.TextArea
          id="interface-description"
          name="description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          status={serverFields.description ? "error" : undefined}
          placeholder="可选；编辑时清空表示删除描述（显式置 null）"
        />
        {serverFields.description && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {serverFields.description}
          </p>
        )}
      </div>

      <div className={FIELD_CLASS}>
        <label htmlFor="interface-metadata" className={LABEL_CLASS}>
          metadata（JSON 对象，可选；接口自有扩展，整值替换）
        </label>
        <Input.TextArea
          id="interface-metadata"
          name="metadata"
          rows={5}
          value={values.metadata}
          onChange={(event) => setField("metadata", event.target.value)}
          disabled={submitting}
          status={metadataError ?? serverFields.metadata ? "error" : undefined}
          placeholder={'可选，例如 {"pci_slot": "3"}；留空视为 {}；与所属资源的 metadata 相互独立'}
        />
        {(metadataError ?? serverFields.metadata) && (
          <p className={FIELD_ERROR_CLASS} role="alert">
            {metadataError ?? serverFields.metadata}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div className={STATUS_ERROR_CLASS} role="alert">
          <p>
            {serverError.message}
            {serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}
          </p>
          {serverError.references.length > 0 && (
            <ul className="list-disc pl-5">
              {serverError.references.map((reference) => (
                <li key={`${reference.object_type}-${reference.object_id}`}>
                  {reference.object_type}
                  {reference.label ? `：${reference.label}` : ""}（{reference.object_id}）
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
          {submitting ? (isCreate ? "正在创建…" : "正在保存…") : isCreate ? "创建" : "保存修改"}
        </Button>
        <Button onClick={onCancel} disabled={submitting}>
          取消
        </Button>
      </div>
    </form>
  );
}
