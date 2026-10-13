import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Select,
  Spin,
  Tag,
} from "antd";
import type { User } from "../api/auth";
import type { DeletedMode } from "../api/clusters";
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

/** 类型下拉候选（“全部”为留空而非选项；可输入筛选 + 自由输入，语义同 datalist）。 */
const TYPE_OPTIONS = GLOBAL_SEARCH_TYPE_OPTIONS.filter((option) => option.value !== "");

/** 按查询串高亮展示文本（ASCII 大小写不敏感子串；非子串的模糊命中不高亮，不伪造位置）。 */
function Highlighted({ text, query }: { text: string; query: string }) {
  const segments = highlightSegments(text, query);
  return (
    <>
      {segments.map((segment, index) =>
        segment.hit ? (
          <mark key={index} className="rounded bg-yellow-200 px-0.5 text-inherit">
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/**
 * status 徽标（Tag 颜色沿用迁移前徽标口径）：IDLE / ACTIVE / RUNNING 绿、
 * ALLOC 蓝、DOWN / STOPPED 红、其余（UNKNOWN / INACTIVE 等）灰。
 */
function statusTag(status: string): ReactNode {
  if (status === "IDLE" || status === "ACTIVE" || status === "RUNNING") {
    return <Tag color="success">{status}</Tag>;
  }
  if (status === "ALLOC") {
    return <Tag color="processing">{status}</Tag>;
  }
  if (status === "DOWN" || status === "STOPPED") {
    return <Tag color="error">{status}</Tag>;
  }
  return <Tag color="default">{status}</Tag>;
}

/** 单条搜索结果行（typed 行，Contract §2.2/§2.3）：类型标签 + 高亮命中值 + 上下文 + 跳转。 */
function ResultRow({
  item,
  highlightQuery,
  deletedFlag,
  onOpenResource,
  onOpenCluster,
  onOpenNetworkIps,
}: {
  item: SearchItem;
  highlightQuery: string;
  deletedFlag: boolean;
  onOpenResource: (id: string, deleted: boolean) => void;
  onOpenCluster: (id: string, deleted: boolean) => void;
  onOpenNetworkIps: (networkId: string) => void;
}) {
  let main: ReactNode = null;
  let meta: ReactNode = null;
  let actions: ReactNode = null;

  if (item.object_type === "resource" && item.resource !== null) {
    // resource 行仅由 hostname 命中产生（matched_field 恒为 hostname，§2.3）
    const resource = item.resource;
    main = (
      <span className="break-words font-mono">
        <Highlighted text={resource.hostname} query={highlightQuery} />
      </span>
    );
    meta = (
      <>
        <span className="font-mono">{resource.resource_type}</span>
        <span>{resource.role}</span>
        {statusTag(resource.status)}
        <span>
          cluster：<span className="font-mono">{resource.cluster.code}</span>
          <span className="text-gray-400">（{resource.cluster.name}）</span>
        </span>
      </>
    );
    actions = (
      <Button
        type="link"
        size="small"
        className="px-0"
        onClick={() => onOpenResource(resource.id, deletedFlag)}
      >
        查看资源
      </Button>
    );
  } else if (item.object_type === "cluster" && item.cluster !== null) {
    // matched_field = code | name：仅高亮实际命中的那个展示值（§2.2 判定规则）
    const cluster = item.cluster;
    main =
      item.matched_field === "code" ? (
        <span className="break-words font-mono">
          <Highlighted text={cluster.code} query={highlightQuery} />
          <span className="text-gray-400">（{cluster.name}）</span>
        </span>
      ) : (
        <span className="break-words">
          <Highlighted text={cluster.name} query={highlightQuery} />
          <span className="text-gray-400">（</span>
          <span className="font-mono">{cluster.code}</span>
          <span className="text-gray-400">）</span>
        </span>
      );
    meta = (
      <>
        {statusTag(cluster.status)}
        <span className="text-gray-400">
          Cluster 不展开其下 Resources，详情见 Cluster Detail（I-12）
        </span>
      </>
    );
    actions = (
      <Button
        type="link"
        size="small"
        className="px-0"
        onClick={() => onOpenCluster(cluster.id, deletedFlag)}
      >
        查看集群
      </Button>
    );
  } else if (item.object_type === "ip_address" && item.ip_address !== null) {
    // IP 精确匹配命中（§2.4）：address 即 matched_value，整值高亮
    const ip = item.ip_address;
    const boundResource = item.resource;
    main = (
      <span className="break-words font-mono">
        <Highlighted text={ip.address} query={highlightQuery} />
      </span>
    );
    meta = (
      <>
        <span>
          network：<span className="font-mono">{ip.network.name}</span>
        </span>
        {ip.interface !== null ? (
          <span>
            interface：<span className="font-mono">{ip.interface.name}</span>
          </span>
        ) : (
          <span className="text-gray-400">未绑定接口</span>
        )}
        {boundResource !== null ? (
          <span>
            所属资源：<span className="font-mono">{boundResource.hostname}</span>
          </span>
        ) : (
          // 未绑定 IP 无 Resource 归属（A5/I-6）：不伪造，按所属网络定位
          <span className="text-gray-400">未绑定资源（按所属网络定位）</span>
        )}
      </>
    );
    actions =
      boundResource !== null ? (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() => onOpenResource(boundResource.id, deletedFlag)}
        >
          查看所属资源
        </Button>
      ) : (
        <Button
          type="link"
          size="small"
          className="px-0"
          onClick={() => onOpenNetworkIps(ip.network.id)}
        >
          查看所属网络 IP
        </Button>
      );
  } else if (item.object_type === "service" && item.service !== null && item.resource !== null) {
    // service 行嵌入承载 Resource（§2.2）；matched_field 恒为 name
    const service = item.service;
    const carrier = item.resource;
    main = (
      <span className="break-words">
        <Highlighted text={service.name} query={highlightQuery} />
      </span>
    );
    meta = (
      <>
        {statusTag(service.status)}
        <span>
          承载资源：<span className="font-mono">{carrier.hostname}</span>
        </span>
        <span className="text-gray-400">
          （<span className="font-mono">{carrier.resource_type}</span>）
        </span>
      </>
    );
    actions = (
      <Button
        type="link"
        size="small"
        className="px-0"
        onClick={() => onOpenResource(carrier.id, deletedFlag)}
      >
        查看所属资源
      </Button>
    );
  } else {
    // 防御：契约 typed 行保证 object_type 与嵌套对象对应（§2.2）；形状不符原样呈现
    main = <span className="break-words font-mono">{item.matched_value}</span>;
    meta = (
      <span className="text-gray-400">
        服务器返回的行结构与契约不符（object_type={item.object_type}）
      </span>
    );
    actions = null;
  }

  return (
    <List.Item>
      <div className="flex w-full flex-wrap items-start gap-x-3 gap-y-2">
        <Tag>{OBJECT_TYPE_LABELS[item.object_type]}</Tag>
        <div className="min-w-0 flex-[1_1_320px]">
          {main}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500">
            {meta}
          </div>
        </div>
        <div className="shrink-0">{actions}</div>
      </div>
    </List.Item>
  );
}

/**
 * F013 全局搜索（Contract §2；§17/§33/A1–A12）：
 * - 首页统一搜索入口：hostname / IP（精确）/ Cluster code·name / Service name
 *   模糊匹配；q 与类型下拉均允许输入（类型下拉为可输入筛选的 AutoComplete，
 *   自由输入的非法值本地报错，不静默归一化）；
 * - 空输入不发请求（I-13/DR-177：本地提示，不发起空 q 调用）；
 * - 结果为 typed 行：类型标签 + 命中值高亮（ASCII 大小写不敏感子串；模糊
 *   命中但非子串时不高亮、不伪造位置）+ 跳转（Resource→Resource Detail、
 *   Cluster→Cluster Detail、IP→所属 Resource / 未绑定→所属 Network、
 *   Service→承载 Resource；deleted=include/only 时跳转携带 deleted=true，
 *   详情端点 include_deleted 语义对已删 / 未删对象均可见）；
 * - Loading / Success / Empty / Error（含未知 reason）显式区分，错误绝不
 *   伪装为空结果；软删可见性开关仅对具 VIEW_DELETED 的角色显示（服务端
 *   仍鉴权，隐藏不替代）；
 * - 只读：无任何新增 / 修改 / 删除 / 恢复入口（A21）。
 *
 * F017：控件层迁移 Ant Design + Tailwind（props / API 调用 / 搜索类型与结果
 * 高亮 / 跳转回调 / 四态 / 全部文案保持不变；datalist → AutoComplete）。
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

  /** 提交搜索（AntD Form onFinish 接管提交时机与默认行为拦截）。 */
  function handleSubmit() {
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
    <section aria-label="全局搜索">
      <Card title="全局搜索" className="mt-8 mb-6">
        <Form layout="vertical" onFinish={handleSubmit}>
          <div className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label
                htmlFor="global-search-q"
                className="mb-1 block text-sm text-gray-700"
              >
                搜索（hostname / IP / Cluster / Service，模糊匹配；IP 为整址精确匹配）
              </label>
              <Input
                id="global-search-q"
                value={draft.q}
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
                placeholder="如 gpu07、10.10.1.50、N96P、slurmd"
                status={formErrors.q || serverInlineErrors.q ? "error" : undefined}
              />
              {formErrors.q && <p className="mt-1 text-xs text-red-500">{formErrors.q}</p>}
              {state.kind === "error" && serverInlineErrors.q && (
                <p className="mt-1 text-xs text-red-500">{serverInlineErrors.q}</p>
              )}
            </div>
            <div>
              <label
                htmlFor="global-search-type"
                className="mb-1 block text-sm text-gray-700"
              >
                类型（可输入筛选，留空 = 全部）
              </label>
              <AutoComplete
                id="global-search-type"
                className="w-full"
                value={draft.type}
                onChange={(value) =>
                  setDraft({ ...draft, type: value as GlobalSearchTypeFilter })
                }
                options={TYPE_OPTIONS}
                filterOption={(input, option) => {
                  const lowered = input.toLowerCase();
                  return (
                    String(option?.value ?? "").toLowerCase().includes(lowered) ||
                    String(option?.label ?? "").toLowerCase().includes(lowered)
                  );
                }}
                placeholder="resource / cluster / ip_address / service"
                status={formErrors.type || serverInlineErrors.type ? "error" : undefined}
              />
              {formErrors.type && (
                <p className="mt-1 text-xs text-red-500">{formErrors.type}</p>
              )}
              {state.kind === "error" && serverInlineErrors.type && (
                <p className="mt-1 text-xs text-red-500">{serverInlineErrors.type}</p>
              )}
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <Button type="primary" htmlType="submit">
              搜索
            </Button>
            <Button onClick={resetSearch}>重置</Button>
          </div>
        </Form>

        {canViewDeleted && (
          <div className="mt-4">
            <label
              htmlFor="global-search-deleted"
              className="mb-1 block text-sm text-gray-700"
            >
              软删可见性（需 VIEW_DELETED 权限）
            </label>
            <Select<DeletedMode>
              id="global-search-deleted"
              className="w-56"
              value={deletedMode}
              onChange={(value) => changeDeleted(value)}
              options={[
                { value: "exclude", label: "未删除（默认）" },
                { value: "include", label: "全部（含已删除）" },
                { value: "only", label: "仅已删除" },
              ]}
            />
          </div>
        )}

        {state.kind === "idle" && (
          <p className="mt-4 text-sm leading-6 text-gray-500">
            输入关键字后点击「搜索」：hostname / Service name 模糊匹配，IP 整址精确匹配，
            Cluster code / name 匹配（大小写不敏感，归一化与唯一性同口径）。
          </p>
        )}

        {state.kind === "loading" && (
          <div className="mt-4 flex items-center gap-3 py-4 text-gray-500">
            <Spin />
            <span>正在搜索…</span>
          </div>
        )}

        {state.kind === "error" && (
          <Alert
            className="mt-4"
            type="error"
            showIcon
            message={`搜索失败：${state.error.message}`}
            description={
              <>
                {serverGeneralErrors.length > 0 && (
                  <ul className="list-disc pl-5">
                    {serverGeneralErrors.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                )}
                <Button
                  className="mt-2"
                  onClick={() => setReloadToken((token) => token + 1)}
                >
                  重试
                </Button>
              </>
            }
          />
        )}

        {state.kind === "success" &&
          (state.data.items.length === 0 ? (
            <Empty
              className="mt-8"
              description="没有匹配的结果（当前关键字与过滤条件下无数据，非错误）。"
            />
          ) : (
            <>
              <List<SearchItem>
                className="mt-4"
                dataSource={state.data.items}
                rowKey={(item) => `${item.object_type}-${item.id}`}
                renderItem={(item) => (
                  <ResultRow
                    item={item}
                    highlightQuery={state.highlightQuery}
                    deletedFlag={state.deletedFlag}
                    onOpenResource={onOpenResource}
                    onOpenCluster={onOpenCluster}
                    onOpenNetworkIps={onOpenNetworkIps}
                  />
                )}
              />
              <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-gray-600">
                <span>
                  共 {state.data.total} 条 · 第 {state.data.page} /{" "}
                  {Math.max(1, Math.ceil(state.data.total / state.data.page_size))} 页
                </span>
                <Button
                  disabled={state.data.page <= 1}
                  onClick={() => gotoPage(state.data.page - 1)}
                >
                  上一页
                </Button>
                <Button
                  disabled={
                    state.data.page >=
                    Math.max(1, Math.ceil(state.data.total / state.data.page_size))
                  }
                  onClick={() => gotoPage(state.data.page + 1)}
                >
                  下一页
                </Button>
                <label className="flex items-center gap-2">
                  每页
                  <Select<number>
                    className="w-20"
                    value={applied?.pageSize ?? DEFAULT_PAGE_SIZE}
                    onChange={(value) => changePageSize(value)}
                    options={[
                      { value: 20, label: "20" },
                      { value: 50, label: "50" },
                      { value: 100, label: "100" },
                    ]}
                  />
                  条
                </label>
              </div>
            </>
          ))}
      </Card>
    </section>
  );
}
