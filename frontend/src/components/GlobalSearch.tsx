import { Button, Input, Select } from "./ui/controls";
import { EmptyState, ErrorState, InfoState, LoadingState } from "./ui/feedback";
import { ServerPagination, StatusTag, SurfaceCard, statusTone } from "./ui/surfaces";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import type { User } from "../api/auth";
import type { DeletedMode } from "../api/clusters";
import type { SearchResourceRef } from "../api/search";
import {
  describeSearchError,
  search,
  type SearchItem,
  type SearchLoadError,
  type SearchResponse,
} from "../api/search";
import {
  GLOBAL_SEARCH_TYPE_OPTIONS,
  buildSearchQuery,
  highlightSegments,
  parseGlobalSearchFormValues,
  searchFormFieldFromPath,
  type GlobalSearchTypeFilter,
} from "./globalSearchForm";
import {
  GLOBAL_SEARCH_FIELD_OPTIONS,
  effectiveGlobalSearchFields,
  fieldSelectionAppliesTo,
  hasRelatedFields,
  readGlobalSearchFieldPreference,
  relatedAvailable,
  relatedRowViews,
  relatedTotal,
  remainingRelatedCount,
  writeGlobalSearchFieldPreference,
  type GlobalSearchFieldKey,
} from "./globalSearchFields";

interface GlobalSearchProps {
  user: User;
  /** 结果跳转：打开 Resource Detail（携带 deleted 上下文）。 */
  onOpenResource: (id: string, deleted: boolean) => void;
  /** 结果跳转：打开 Cluster Detail（携带 deleted 上下文）。 */
  onOpenCluster: (id: string, deleted: boolean) => void;
  /**
   * 结果跳转：未绑定 IP 按所属 Network 定位（跳到 IP Addresses 列表并按
   * 该网络过滤；无独立 Network Detail 页，Contract §2.2/A5 不伪造归属）。
   */
  onOpenNetworkIps: (networkId: string) => void;
}

/** 结果加载状态：idle = 尚未搜索（与 Empty 显式区分，不互相伪装）。 */
type SearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; data: SearchResponse; highlightQuery: string; deletedFlag: boolean }
  | { kind: "error"; error: SearchLoadError };

/** 已应用的搜索（含分页 / 软删可见性；null = 尚未发起搜索）。 */
interface AppliedSearch {
  q: string;
  type: GlobalSearchTypeFilter;
  deleted: DeletedMode;
  page: number;
  pageSize: number;
}

const DEFAULT_PAGE_SIZE = 20;

/** 对象类型标签文案（结果列表类型标签，A10）。 */
const OBJECT_TYPE_LABELS: Record<SearchItem["object_type"], string> = {
  resource: "Resource",
  cluster: "Cluster",
  ip_address: "IP",
  service: "Service",
};

/** 按查询串高亮展示文本（ASCII 大小写不敏感子串；非子串的模糊命中不高亮，不伪造位置）。 */
function Highlighted({ text, query }: { text: string; query: string }) {
  const segments = highlightSegments(text, query);
  return (
    <>
      {segments.map((segment, index) =>
        segment.hit ? (
          <mark key={index}>{segment.text}</mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/**
 * F018 resource 行关联展开（Contract v2 §2.9）：按生效字段渲染 related 行
 * （interface name / interface_type、IP、Network，每个已绑定 IP 一行，
 * 服务端最多返回 10 行且已按固定全序排序）；超限时显式提示
 * 「还有 N 条」（N = related_total − 展示行数，DR-321/A6，不静默截断）；
 * 无关联行为空集合时显式空态（不伪造占位行，A5）；related 缺失 / 非数组
 * （旧后端 v1 响应 / 形状不符）时静默省略本区块（F8 安全回退，不阻断展示）。
 * 仅在选择了任一关联字段时展开（未选 = F013 展示，A12）。
 */
function RelatedSection({
  resource,
  fields,
}: {
  resource: SearchResourceRef;
  fields: readonly GlobalSearchFieldKey[];
}) {
  if (!hasRelatedFields(fields) || !relatedAvailable(resource)) {
    return null;
  }
  const rows = relatedRowViews(resource);
  const remaining = remainingRelatedCount(resource);
  return (
    <div className="search-related">
      <span className="search-related-label">关联（每已绑定 IP 一行，最多 10 行）：</span>
      {rows.length > 0 ? (
        <ul className="search-related-list">
          {rows.map((row, index) => (
            <li key={row.key === "" ? index : row.key}>
              {fields.includes("interface_name") && (
                <span>
                  interface：<span className="mono">{row.interfaceName ?? "—"}</span>
                </span>
              )}
              {fields.includes("interface_type") && (
                <span>
                  type：<span className="mono">{row.interfaceType ?? "—"}</span>
                </span>
              )}
              {fields.includes("ip_address") && (
                <span>
                  IP：<span className="mono">{row.ipAddress ?? "—"}</span>
                </span>
              )}
              {fields.includes("network_name") && (
                <span>
                  network：<span className="mono">{row.networkName ?? "—"}</span>
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <span className="unset">无已绑定 IP 关联</span>
      )}
      {remaining > 0 && (
        <span className="search-related-more">
          还有 {remaining} 条关联未展示（该资源关联共 {relatedTotal(resource)} 条，每台最多展示 10 行）
        </span>
      )}
    </div>
  );
}

/** 单条搜索结果行（typed 行，Contract §2.2/§2.3）：类型标签 + 高亮命中值 + 上下文 + 跳转。 */
function ResultRow({
  item,
  highlightQuery,
  deletedFlag,
  fields,
  onOpenResource,
  onOpenCluster,
  onOpenNetworkIps,
}: {
  item: SearchItem;
  highlightQuery: string;
  deletedFlag: boolean;
  /** F018 生效字段组合（仅作用 resource 行，DR-327；其余行不消费）。 */
  fields: readonly GlobalSearchFieldKey[];
  onOpenResource: (id: string, deleted: boolean) => void;
  onOpenCluster: (id: string, deleted: boolean) => void;
  onOpenNetworkIps: (networkId: string) => void;
}) {
  let main: ReactNode = null;
  let meta: ReactNode = null;
  let related: ReactNode = null;
  let actions: ReactNode = null;

  // 字段选择仅作用 resource 行（DR-327/F6）；cluster / ip_address / service
  // 行展示不因字段选择改变（F013 行为）
  if (fieldSelectionAppliesTo(item.object_type) && item.resource !== null) {
    // resource 行仅由 hostname 命中产生（matched_field 恒为 hostname，§2.3）；
    // F018：按生效字段组合展示（默认 = F013 既有展示，A12）
    const resource = item.resource;
    main =
      fields.includes("hostname") ? (
        <span className="mono search-result-value">
          <Highlighted text={resource.hostname} query={highlightQuery} />
        </span>
      ) : null;
    meta = (
      <>
        {fields.includes("resource_type") && (
          <span className="mono">{resource.resource_type}</span>
        )}
        {fields.includes("role") && <span>{resource.role}</span>}
        {fields.includes("status") && (
          <StatusTag tone={statusTone(resource.status)}>{resource.status}</StatusTag>
        )}
        {fields.includes("cluster") && (
          <span>
            cluster：<span className="mono">{resource.cluster.code}</span>
            <span className="unset">（{resource.cluster.name}）</span>
          </span>
        )}
      </>
    );
    related = <RelatedSection resource={resource} fields={fields} />;
    actions = (
      <Button type="button" onClick={() => onOpenResource(resource.id, deletedFlag)}>
        查看资源
      </Button>
    );
  } else if (item.object_type === "cluster" && item.cluster !== null) {
    // matched_field = code | name：仅高亮实际命中的那个展示值（§2.2 判定规则）
    const cluster = item.cluster;
    main =
      item.matched_field === "code" ? (
        <span className="mono search-result-value">
          <Highlighted text={cluster.code} query={highlightQuery} />
          <span className="unset">（{cluster.name}）</span>
        </span>
      ) : (
        <span className="search-result-value">
          <Highlighted text={cluster.name} query={highlightQuery} />
          <span className="unset">（</span>
          <span className="mono">{cluster.code}</span>
          <span className="unset">）</span>
        </span>
      );
    meta = (
      <>
        <StatusTag tone={statusTone(cluster.status)}>{cluster.status}</StatusTag>
        <span className="unset">Cluster 不展开其下 Resources，详情见 Cluster Detail（I-12）</span>
      </>
    );
    actions = (
      <Button type="button" onClick={() => onOpenCluster(cluster.id, deletedFlag)}>
        查看集群
      </Button>
    );
  } else if (item.object_type === "ip_address" && item.ip_address !== null) {
    // IP 精确匹配命中（§2.4）：address 即 matched_value，整值高亮
    const ip = item.ip_address;
    const boundResource = item.resource;
    main = (
      <span className="mono search-result-value">
        <Highlighted text={ip.address} query={highlightQuery} />
      </span>
    );
    meta = (
      <>
        <span>
          network：<span className="mono">{ip.network.name}</span>
        </span>
        {ip.interface !== null ? (
          <span>
            interface：<span className="mono">{ip.interface.name}</span>
          </span>
        ) : (
          <span className="unset">未绑定接口</span>
        )}
        {boundResource !== null ? (
          <span>
            所属资源：<span className="mono">{boundResource.hostname}</span>
          </span>
        ) : (
          // 未绑定 IP 无 Resource 归属（A5/I-6）：不伪造，按所属网络定位
          <span className="unset">未绑定资源（按所属网络定位）</span>
        )}
      </>
    );
    actions =
      boundResource !== null ? (
        <Button type="button" onClick={() => onOpenResource(boundResource.id, deletedFlag)}>
          查看所属资源
        </Button>
      ) : (
        <Button type="button" onClick={() => onOpenNetworkIps(ip.network.id)}>
          查看所属网络 IP
        </Button>
      );
  } else if (item.object_type === "service" && item.service !== null && item.resource !== null) {
    // service 行嵌入承载 Resource（§2.2）；matched_field 恒为 name
    const service = item.service;
    const carrier = item.resource;
    main = (
      <span className="search-result-value">
        <Highlighted text={service.name} query={highlightQuery} />
      </span>
    );
    meta = (
      <>
        <StatusTag tone={statusTone(service.status)}>{service.status}</StatusTag>
        <span>
          承载资源：<span className="mono">{carrier.hostname}</span>
        </span>
        <span className="unset">
          （<span className="mono">{carrier.resource_type}</span>）
        </span>
      </>
    );
    actions = (
      <Button type="button" onClick={() => onOpenResource(carrier.id, deletedFlag)}>
        查看所属资源
      </Button>
    );
  } else {
    // 防御：契约 typed 行保证 object_type 与嵌套对象对应（§2.2）；形状不符原样呈现
    main = <span className="mono search-result-value">{item.matched_value}</span>;
    meta = <span className="unset">服务器返回的行结构与契约不符（object_type={item.object_type}）</span>;
    actions = null;
  }

  return (
    <li className="search-result-item">
      <StatusTag tone="blue">{OBJECT_TYPE_LABELS[item.object_type]}</StatusTag>
      <div className="search-result-main">
        {main}
        <div className="search-result-meta">{meta}</div>
        {related}
      </div>
      <div className="search-result-actions">{actions}</div>
    </li>
  );
}

/**
 * F013 全局搜索（Contract §2；§17/§33/A1–A12）：
 * - 首页统一搜索入口：hostname / IP（精确）/ Cluster code·name / Service name
 *   模糊匹配；q 与类型下拉均允许输入（类型下拉 input + datalist，可输入筛选）；
 * - 空输入不发请求（I-13/DR-177：本地提示，不发起空 q 调用）；
 * - 结果为 typed 行：类型标签 + 命中值高亮（ASCII 大小写不敏感子串；模糊
 *   命中但非子串时不高亮、不伪造位置）+ 跳转（Resource→Resource Detail、
 *   Cluster→Cluster Detail、IP→所属 Resource / 未绑定→所属 Network、
 *   Service→承载 Resource；deleted=include/only 时跳转携带 deleted=true，
 *   详情端点 include_deleted 语义对已删 / 未删对象均可见）；
 * - Loading / Success / Empty / Error（含未知 reason）显式区分，错误绝不
 *   伪装为空结果；软删可见性开关仅对具 VIEW_DELETED 的角色显示（服务端
 *   仍鉴权，隐藏不替代）；
 * - 只读：无任何新增 / 修改 / 删除 / 恢复入口（A21）；
 * - F018 字段组合（Contract v2 §2.9）：Resource 行九字段可选展示（选择器仅
 *   作用 resource 行，DR-327）+ 关联每已绑定 IP 一行展开（≤ 10 行，超限
 *   显式提示「还有 N 条」）；偏好仅存浏览器本地（localStorage），读写失败
 *   静默回退默认展示（= F013，A11/A12）；字段选择不改变查询参数与结果集
 *   （A9/F7）。
 */
export default function GlobalSearch({
  user,
  onOpenResource,
  onOpenCluster,
  onOpenNetworkIps,
}: GlobalSearchProps) {
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const [draft, setDraft] = useState<{ q: string; type: GlobalSearchTypeFilter }>({
    q: "",
    type: "",
  });
  const [formErrors, setFormErrors] = useState<{ q?: string; type?: string }>({});
  const [deletedMode, setDeletedMode] = useState<DeletedMode>("exclude");
  const [applied, setApplied] = useState<AppliedSearch | null>(null);
  const [state, setState] = useState<SearchState>({ kind: "idle" });
  const [reloadToken, setReloadToken] = useState(0);
  // F018 字段偏好：null = 无已存偏好（未使用选择器 / 存储不可用 / 偏好损坏），
  // 展示默认组合；仅在挂载时读取一次（DR-326）
  const [fieldPreference, setFieldPreference] = useState<GlobalSearchFieldKey[] | null>(() =>
    readGlobalSearchFieldPreference(),
  );
  const selectedFields = effectiveGlobalSearchFields(fieldPreference);

  useEffect(() => {
    if (applied === null) {
      return;
    }
    // 空输入不发请求（buildSearchQuery 对空 q 返回 null；提交入口已本地拦截）
    const query = buildSearchQuery(applied);
    if (query === null) {
      setState({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setState({ kind: "loading" });
    search(query)
      .then((data) => {
        if (!cancelled) {
          setState({
            kind: "success",
            data,
            highlightQuery: query.q,
            deletedFlag: applied.deleted !== "exclude",
          });
        }
      })
      .catch((error: unknown) => {
        // 401 已由 client 全局处理器回登录页；403 / 422 / 500 / 网络错误显式呈现
        if (!cancelled) {
          setState({ kind: "error", error: describeSearchError(error) });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [applied, reloadToken]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = parseGlobalSearchFormValues(draft);
    if (!parsed.ok) {
      // 本地快速反馈（空 q / 超长 / 非法 type）：不发请求（I-13）
      setFormErrors(parsed.errors);
      return;
    }
    setFormErrors({});
    setApplied({
      q: parsed.fields.q,
      type: parsed.fields.type,
      deleted: deletedMode,
      page: 1,
      pageSize: applied?.pageSize ?? DEFAULT_PAGE_SIZE,
    });
  }

  function resetSearch() {
    setDraft({ q: "", type: "" });
    setFormErrors({});
    setDeletedMode("exclude");
    setApplied(null);
    setState({ kind: "idle" });
  }

  /** 软删可见性变化：立即重查（回到第 1 页）；未搜索时仅记录，供下次搜索生效。 */
  function changeDeleted(deleted: DeletedMode) {
    setDeletedMode(deleted);
    setApplied((current) =>
      current === null ? current : { ...current, deleted, page: 1 },
    );
  }

  function gotoPage(page: number) {
    setApplied((current) => (current === null ? current : { ...current, page }));
  }

  function changePageSize(pageSize: number) {
    setApplied((current) =>
      current === null ? current : { ...current, pageSize, page: 1 },
    );
  }

  /**
   * F018 字段选择：仅改变 resource 行展示（DR-327），不进入查询参数与
   * applied（A9/F7）；偏好写入 localStorage，失败静默（会话内仍生效，
   * DR-326）；至少保留一个字段（空选择 = 默认组合，A12，选择器不产生
   * 无字段状态：最后一个勾选字段禁用取消）。
   */
  function changeField(field: GlobalSearchFieldKey, checked: boolean) {
    const next = checked
      ? [...selectedFields, field]
      : selectedFields.filter((key) => key !== field);
    if (next.length === 0) {
      return;
    }
    setFieldPreference(next);
    writeGlobalSearchFieldPreference(next);
  }

  // 服务端 422 字段错误：q/type 落到输入框下方；其余（deleted/page/page_size/
  // 未知路径）在错误区逐条呈现，不静默丢弃
  const serverInlineErrors: { q?: string; type?: string } = {};
  const serverGeneralErrors: string[] = [];
  if (state.kind === "error") {
    for (const [path, message] of Object.entries(state.error.fields)) {
      const key = searchFormFieldFromPath(path);
      if (key === "q" || key === "type") {
        serverInlineErrors[key] = message;
      } else {
        serverGeneralErrors.push(`${path}：${message}`);
      }
    }
  }

  return (
    <SurfaceCard className="panel" aria-label="全局搜索">
      <h2>全局搜索</h2>
      <form className="filter-form" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="global-search-q">
            搜索（hostname / IP / Cluster / Service，模糊匹配；IP 为整址精确匹配）
          </label>
          <Input
            id="global-search-q"
            type="text"
            value={draft.q}
            onChange={(event) => setDraft({ ...draft, q: event.target.value })}
            placeholder="如 gpu07、10.10.1.50、N96P、slurmd"
          />
          {formErrors.q && <p className="field-error">{formErrors.q}</p>}
          {state.kind === "error" && serverInlineErrors.q && (
            <p className="field-error">{serverInlineErrors.q}</p>
          )}
        </div>
        <div className="form-field">
          <label htmlFor="global-search-type">类型（可输入筛选，留空 = 全部）</label>
          <Input
            id="global-search-type"
            type="text"
            list="global-search-type-options"
            value={draft.type}
            onChange={(event) =>
              setDraft({ ...draft, type: event.target.value as GlobalSearchTypeFilter })
            }
            placeholder="resource / cluster / ip_address / service"
          />
          <datalist id="global-search-type-options">
            {GLOBAL_SEARCH_TYPE_OPTIONS.filter((option) => option.value !== "").map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </datalist>
          {formErrors.type && <p className="field-error">{formErrors.type}</p>}
          {state.kind === "error" && serverInlineErrors.type && (
            <p className="field-error">{serverInlineErrors.type}</p>
          )}
        </div>
        <div className="filter-actions">
          <Button type="submit">搜索</Button>
          <Button type="button" onClick={resetSearch}>
            重置
          </Button>
        </div>
      </form>

      {canViewDeleted && (
        <div className="form-field deleted-toggle">
          <label htmlFor="global-search-deleted">软删可见性（需 VIEW_DELETED 权限）</label>
          <Select
            id="global-search-deleted"
            value={deletedMode}
            onChange={(event) => changeDeleted(event.target.value as DeletedMode)}
          >
            <option value="exclude">未删除（默认）</option>
            <option value="include">全部（含已删除）</option>
            <option value="only">仅已删除</option>
          </Select>
        </div>
      )}

      {/* F018 字段选择器：九字段多选，仅作用 resource 结果行（DR-327）；
          偏好仅浏览器本地，读写失败静默回退（DR-326）。
          F033 DR-F033-07：fieldset/legend → details/summary，默认折叠
          （不写 open、不持久化展开态）；selectedFields、localStorage
          键/值、changeField、buildSearchQuery 与请求参数零变化。 */}
      <details className="search-fields-toggle">
        <summary>Resource 行展示字段（仅作用 resource 结果行）</summary>
        <div className="search-fields-options" role="group" aria-label="Resource 行展示字段">
          {GLOBAL_SEARCH_FIELD_OPTIONS.map((option) => {
            const checked = selectedFields.includes(option.value);
            return (
              <label key={option.value} htmlFor={`global-search-field-${option.value}`}>
                <Input
                  id={`global-search-field-${option.value}`}
                  type="checkbox"
                  checked={checked}
                  disabled={checked && selectedFields.length === 1}
                  onChange={(event) => changeField(option.value, event.target.checked)}
                />
                {option.label}
              </label>
            );
          })}
        </div>
        <p className="unset search-fields-note">
          偏好仅保存在本浏览器（localStorage），刷新后沿用；未选择时保持默认展示
          （hostname / 类型 / 角色 / 状态 / 集群）。存储不可用时仅当前会话生效，不影响搜索。
        </p>
      </details>

      {state.kind === "idle" && (
        <InfoState message="输入关键字后点击「搜索」：hostname / Service name 模糊匹配，IP 整址精确匹配，Cluster code / name 匹配（大小写不敏感，归一化与唯一性同口径）。" />
      )}

      {state.kind === "loading" && <LoadingState label="正在搜索…" />}

      {state.kind === "error" && (
        <ErrorState
          message={
            <>
              <p>搜索失败：{state.error.message}</p>
              {serverGeneralErrors.length > 0 && (
                <ul>
                  {serverGeneralErrors.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              )}
            </>
          }
          action={
            <Button type="button" onClick={() => setReloadToken((token) => token + 1)}>
              重试
            </Button>
          }
        />
      )}

      {state.kind === "success" &&
        (state.data.items.length === 0 ? (
          <EmptyState description="没有匹配的结果（当前关键字与过滤条件下无数据，非错误）。" />
        ) : (
          <>
            <ul className="search-results">
              {state.data.items.map((item) => (
                <ResultRow
                  key={`${item.object_type}-${item.id}`}
                  item={item}
                  highlightQuery={state.highlightQuery}
                  deletedFlag={state.deletedFlag}
                  fields={selectedFields}
                  onOpenResource={onOpenResource}
                  onOpenCluster={onOpenCluster}
                  onOpenNetworkIps={onOpenNetworkIps}
                />
              ))}
            </ul>
            <ServerPagination
              page={state.data.page}
              pageSize={state.data.page_size}
              total={state.data.total}
              appliedPageSize={applied?.pageSize ?? DEFAULT_PAGE_SIZE}
              onGotoPage={gotoPage}
              onChangePageSize={changePageSize}
            />
          </>
        ))}
    </SurfaceCard>
  );
}
