import { useEffect, useState, type FormEvent } from "react";
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
    <form onSubmit={handleSubmit} noValidate>
      <div className="form-field">
        <span className="field-label">resource（所属资源，创建后不可修改）</span>
        <p className="readonly-value mono">
          {resource.hostname}
          <span className="unset">（id: {resource.id}）</span>
        </p>
        {serverFields.resource && (
          <p className="field-error" role="alert">
            {serverFields.resource}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="interface-name">
          name（必填；区分大小写保留输入，同资源内未删除唯一；禁内部空白 / 控制字符，≤64）
        </label>
        <input
          id="interface-name"
          name="name"
          type="text"
          value={values.name}
          onChange={(event) => setField("name", event.target.value)}
          disabled={submitting}
          placeholder="如 eth0；eth0 与 ETH0 为不同名称；已软删接口不占用名称"
        />
        {fieldError("name") && (
          <p className="field-error" role="alert">
            {fieldError("name")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="interface-type">interface_type（类型，可选，默认 OTHER；不据名称推断）</label>
        <select
          id="interface-type"
          name="interface_type"
          value={values.interface_type}
          onChange={(event) => setField("interface_type", event.target.value as InterfaceTypeValue)}
          disabled={submitting}
        >
          {INTERFACE_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {serverFields.interface_type && (
          <p className="field-error" role="alert">
            {serverFields.interface_type}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="interface-parent">
          parent_interface（父接口，可选；须为本资源内未删除的其它接口，留空 = 根接口）
        </label>
        {parentOptions.kind === "loading" && (
          <p className="status status-loading">正在加载接口列表…</p>
        )}
        {parentOptions.kind === "error" && (
          <div className="status status-error" role="alert">
            <p>加载父接口候选失败：{parentOptions.message}</p>
            <button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </button>
          </div>
        )}
        {parentOptions.kind === "success" && parentItems.length === 0 && (
          <p className="status status-empty">
            本资源暂无其它未删除接口：留空即为根接口（首个接口无父）。
          </p>
        )}
        <select
          id="interface-parent"
          name="parent_interface"
          value={values.parent_interface}
          onChange={(event) => setField("parent_interface", event.target.value)}
          disabled={submitting || parentOptions.kind !== "success"}
        >
          <option value="">无（根接口）</option>
          {currentParentMissing && currentParent !== null && (
            <option value={currentParent.id}>{currentParent.name}（当前父接口）</option>
          )}
          {parentItems.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}（{item.interface_type}）
            </option>
          ))}
        </select>
        {parentOptions.kind === "success" && parentOptions.total > parentOptions.items.length && (
          <p className="status status-empty">
            接口总数 {parentOptions.total} 个，下拉仅显示前 {parentOptions.items.length} 个
            （按 name 排序；列表分页上限 100）。
          </p>
        )}
        {fieldError("parent_interface") && (
          <p className="field-error" role="alert">
            {fieldError("parent_interface")}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="interface-mac">
          mac_address（MAC 地址，可选；无格式校验、保留输入大小写，≤64）
        </label>
        <input
          id="interface-mac"
          name="mac_address"
          type="text"
          value={values.mac_address}
          onChange={(event) => setField("mac_address", event.target.value)}
          disabled={submitting}
          placeholder="如 00:1A:2B:3C:4D:5E；留空 = 未登记（null）；一期不做全局唯一"
        />
        {fieldError("mac_address") && (
          <p className="field-error" role="alert">
            {fieldError("mac_address")}
          </p>
        )}
      </div>

      {INTERFACE_INT_FIELDS.map((field) => (
        <div className="form-field" key={field.key}>
          <label htmlFor={`interface-${field.key}`}>{field.label}</label>
          <input
            id={`interface-${field.key}`}
            name={field.key}
            type="text"
            value={values[field.key]}
            onChange={(event) => setField(field.key, event.target.value)}
            disabled={submitting}
            placeholder={field.placeholder}
          />
          {fieldError(field.key) && (
            <p className="field-error" role="alert">
              {fieldError(field.key)}
            </p>
          )}
        </div>
      ))}

      <div className="form-field checkbox-field">
        <label htmlFor="interface-enabled">
          <input
            id="interface-enabled"
            name="enabled"
            type="checkbox"
            checked={values.enabled}
            onChange={(event) => setField("enabled", event.target.checked)}
            disabled={submitting}
          />
          enabled（启用状态；登记值非实时探测，默认开启）
        </label>
      </div>

      <div className="form-field">
        <label htmlFor="interface-description">description（描述，可选）</label>
        <textarea
          id="interface-description"
          name="description"
          rows={3}
          value={values.description}
          onChange={(event) => setField("description", event.target.value)}
          disabled={submitting}
          placeholder="可选；编辑时清空表示删除描述（显式置 null）"
        />
        {serverFields.description && (
          <p className="field-error" role="alert">
            {serverFields.description}
          </p>
        )}
      </div>

      <div className="form-field">
        <label htmlFor="interface-metadata">metadata（JSON 对象，可选；接口自有扩展，整值替换）</label>
        <textarea
          id="interface-metadata"
          name="metadata"
          rows={5}
          value={values.metadata}
          onChange={(event) => setField("metadata", event.target.value)}
          disabled={submitting}
          placeholder={'可选，例如 {"pci_slot": "3"}；留空视为 {}；与所属资源的 metadata 相互独立'}
        />
        {(metadataError ?? serverFields.metadata) && (
          <p className="field-error" role="alert">
            {metadataError ?? serverFields.metadata}
          </p>
        )}
      </div>

      {serverError && serverError.message && (
        <div className="form-error status status-error" role="alert">
          <p>
            {serverError.message}
            {serverError.code && !serverError.versionConflict ? `（${serverError.code}）` : ""}
          </p>
          {serverError.references.length > 0 && (
            <ul>
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
