import { Button } from "../components/ui/controls";
import { ErrorState } from "../components/ui/feedback";
import { SurfaceCard } from "../components/ui/surfaces";
import { Descriptions, Tag } from "antd";
import { AppstoreOutlined, ClusterOutlined, DatabaseOutlined, DeploymentUnitOutlined, HddOutlined, HistoryOutlined, LogoutOutlined, SafetyCertificateOutlined, SettingOutlined, UserOutlined, CloudServerOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import { logout, type User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import type { Cluster } from "../api/clusters";
import type { Resource } from "../api/resources";
import HealthPanel from "../components/HealthPanel";
import GlobalSearch from "../components/GlobalSearch";
import DashboardPanel from "../components/DashboardPanel";
import ClustersPage from "./ClustersPage";
import ClusterCreatePage from "./ClusterCreatePage";
import ClusterDetailPage from "./ClusterDetailPage";
import ResourcesPage from "./ResourcesPage";
import ResourceCreatePage from "./ResourceCreatePage";
import ResourceDetailPage from "./ResourceDetailPage";
import NetworksPage from "./NetworksPage";
import IpPoolsPage from "./IpPoolsPage";
import IpAddressesPage from "./IpAddressesPage";
import ServicesPage from "./ServicesPage";
import AuditPage from "./AuditPage";
import SystemPage from "./SystemPage";

interface HomePageProps {
  user: User;
  /** 登出完成（或会话已失效），由应用壳切回登录页。 */
  onLoggedOut: () => void;
}

/** 已登录后的内容区（最小状态切换，不引入路由库 / 状态管理库）。 */
type Section =
  | { name: "overview" }
  | { name: "clusters" }
  | { name: "cluster-create" }
  | { name: "cluster-detail"; id: string; deleted: boolean }
  | { name: "resources" }
  | { name: "resource-create" }
  | { name: "resource-detail"; id: string; deleted: boolean }
  | { name: "networks" }
  | { name: "ip-pools" }
  | { name: "ip-addresses"; networkId?: string }
  | { name: "services" }
  | { name: "audit" }
  | { name: "system" };

/**
 * F002 已登录视图 + F003/F004/F008 导航壳（架构 §1.8，不追求复杂视觉效果）：
 * 概览（F013 首页统一全局搜索 + Dashboard 汇总 / 当前用户 / 后端健康）/ Clusters
 * （列表 / 新建 / 详情）/ Resources（列表 / 新建 / 详情）/ Networks（列表 /
 * 新建 / 编辑，F008）/ IP Pools（列表 / 新建 / 编辑，F009）/ IP Addresses
 * （分配 / 绑定 / 释放 / 恢复，F010；可从 F013 搜索按所属网络定位）/ Services
 * （服务登记：列表 / 创建 / 编辑 / 删除 / 恢复 / Activity，F011）/ Audit
 * （完整审计查询，F015；仅 AUDIT_READ）/ System（账号管理 + 已删对象管理，
 * F015；需 USER_ADMIN 或 VIEW_DELETED）。
 * 各入口对
 * 全部已登录角色可见
 * （READ 全角色）；写 / 删 / 恢复 / 已删可见性仅按服务端返回的 permissions
 * 显示对应控件——隐藏不替代鉴权，服务端仍按 §23 矩阵执行（越权请求 403
 * 由页面明确呈现）。Audit / System 导航同样仅对具备对应权限的角色显示。
 */
export default function HomePage({ user, onLoggedOut }: HomePageProps) {
  const [section, setSection] = useState<Section>({ name: "overview" });
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const contentRef = useRef<HTMLElement>(null);
  const previousSection = useRef(section);

  useEffect(() => {
    if (previousSection.current !== section) {
      contentRef.current?.focus({ preventScroll: true });
      window.scrollTo({ top: 0, behavior: "instant" });
      previousSection.current = section;
    }
  }, [section]);

  async function handleLogout() {
    if (loggingOut) {
      return;
    }
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await logout(); // 204：服务端已删除会话行并清除 Cookie
      onLoggedOut();
    } catch (err: unknown) {
      if (isApiError(err) && err.status === 401) {
        // 会话已失效（过期 / 用户停用），与登出等效；
        // client 的全局 401 处理器也已同时清登录态回登录页
        onLoggedOut();
      } else {
        // 403（CSRF）等：明确呈现错误，不静默重试
        setLogoutError(displayError(err));
      }
    } finally {
      setLoggingOut(false);
    }
  }

  const inClusters =
    section.name === "clusters" ||
    section.name === "cluster-create" ||
    section.name === "cluster-detail";
  const inResources =
    section.name === "resources" ||
    section.name === "resource-create" ||
    section.name === "resource-detail";
  const inNetworks = section.name === "networks";
  const inIpPools = section.name === "ip-pools";
  const inIpAddresses = section.name === "ip-addresses";
  const inServices = section.name === "services";
  const inAudit = section.name === "audit";
  const inSystem = section.name === "system";
  const inOverview = section.name === "overview";
  // F015：Audit 仅 AUDIT_READ；System 需 USER_ADMIN（账号管理）或
  // VIEW_DELETED（已删对象管理）之一（DR-224）；按服务端返回的 permissions
  // 显示 / 隐藏导航入口，不替代服务端鉴权
  const canAudit = user.permissions.includes("AUDIT_READ");
  const canSystem =
    user.permissions.includes("USER_ADMIN") || user.permissions.includes("VIEW_DELETED");

  const navigation = [
    { name: "overview", label: "概览", description: "资源概览", active: inOverview, icon: <AppstoreOutlined />, group: "工作空间" },
    { name: "clusters", label: "Clusters", description: "集群管理", active: inClusters, icon: <ClusterOutlined />, group: "资源管理" },
    { name: "resources", label: "Resources", description: "资源台账", active: inResources, icon: <HddOutlined /> },
    { name: "networks", label: "Networks", description: "网络管理", active: inNetworks, icon: <DeploymentUnitOutlined /> },
    { name: "ip-pools", label: "IP Pools", description: "地址池管理", active: inIpPools, icon: <DatabaseOutlined /> },
    { name: "ip-addresses", label: "IP Addresses", description: "IP 地址管理", active: inIpAddresses, icon: <CloudServerOutlined /> },
    { name: "services", label: "Services", description: "服务登记", active: inServices, icon: <AppstoreOutlined /> },
    ...(canAudit ? [{ name: "audit", label: "Audit", description: "审计查询", active: inAudit, icon: <HistoryOutlined />, group: "平台管理" }] : []),
    ...(canSystem ? [{ name: "system", label: "System", description: "系统管理", active: inSystem, icon: <SettingOutlined />, group: canAudit ? undefined : "平台管理" }] : []),
  ];
  const currentPage = navigation.find((item) => item.active)!;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#workspace-content">跳转到主要内容</a>
      <aside className="app-sidebar" aria-label="工作空间导航">
        <div className="app-brand">
          <span className="brand-symbol" aria-hidden="true"><ClusterOutlined /></span>
          <div><strong>CSM</strong><span>Cluster Source Manager</span></div>
        </div>
        <nav className="app-nav" aria-label="主导航">
          {navigation.map((item) => (
            <div className="nav-entry" key={item.name}>
              {item.group && <p className="nav-group-label">{item.group}</p>}
              <Button
                type="button"
                variant="text"
                className={item.active ? "nav-link nav-link-active" : "nav-link"}
                aria-current={item.active ? "page" : undefined}
                icon={<span aria-hidden="true">{item.icon}</span>}
                onClick={() => setSection({ name: item.name } as Section)}
              >
                {item.label}
              </Button>
            </div>
          ))}
        </nav>
        <div className="sidebar-note"><SafetyCertificateOutlined aria-hidden="true" /><span>资源事实数据源</span></div>
      </aside>

      <div className="app-workspace">
      <header className="app-header">
        <div className="workspace-location"><span>工作空间</span><span aria-hidden="true">/</span><strong>{currentPage.description}</strong></div>
        <div className="user-box">
          <span className="user-avatar" aria-hidden="true"><UserOutlined /></span>
          <span className="user-name">{user.username}</span>
          <span className="user-role">{user.role}</span>
          <Button type="button" variant="text" icon={<LogoutOutlined aria-hidden="true" />} onClick={handleLogout} disabled={loggingOut}>
            {loggingOut ? "正在登出…" : "登出"}
          </Button>
        </div>
      </header>

      <main className="workspace-content" id="workspace-content" ref={contentRef} tabIndex={-1} aria-label={currentPage.description}>
      <div className="page-heading">
        <div><p className="page-eyebrow">CLUSTER SOURCE MANAGER</p><h1>{currentPage.description}</h1></div>
        <p className="subtitle">统一登记、查询与维护集群资源</p>
      </div>
      {logoutError && <ErrorState message={`登出失败：${logoutError}`} />}

      {section.name === "overview" && (
        <>
          <GlobalSearch
            user={user}
            onOpenResource={(id, deleted) =>
              setSection({ name: "resource-detail", id, deleted })
            }
            onOpenCluster={(id, deleted) =>
              setSection({ name: "cluster-detail", id, deleted })
            }
            onOpenNetworkIps={(networkId) =>
              setSection({ name: "ip-addresses", networkId })
            }
          />

          <DashboardPanel />

          <SurfaceCard className="panel" title="当前用户">
            <Descriptions
              column={{ xs: 1, sm: 3 }}
              items={[
                { key: "username", label: "用户名", children: user.username },
                { key: "role", label: "角色", children: user.role },
                { key: "status", label: "状态", children: user.status },
              ]}
              size="small"
            />
            <p className="permissions-note">
              权限（由服务端按角色返回，仅用于界面显示，不构成安全边界）：
            </p>
            <div className="permissions">
              {user.permissions.length > 0 ? (
                user.permissions.map((permission) => (
                  <Tag key={permission}>{permission}</Tag>
                ))
              ) : (
                <Tag>无</Tag>
              )}
            </div>
          </SurfaceCard>

          <HealthPanel />
        </>
      )}

      {section.name === "clusters" && (
        <ClustersPage
          user={user}
          onOpenCluster={(cluster: Cluster) =>
            setSection({
              name: "cluster-detail",
              id: cluster.id,
              deleted: cluster.deleted_at !== null,
            })
          }
          onCreate={() => setSection({ name: "cluster-create" })}
        />
      )}

      {section.name === "cluster-create" && (
        <ClusterCreatePage
          user={user}
          onCancel={() => setSection({ name: "clusters" })}
          onCreated={(cluster) =>
            setSection({ name: "cluster-detail", id: cluster.id, deleted: false })
          }
        />
      )}

      {section.name === "cluster-detail" && (
        <ClusterDetailPage
          key={section.id}
          clusterId={section.id}
          initialDeleted={section.deleted}
          user={user}
          onBack={() => setSection({ name: "clusters" })}
        />
      )}

      {section.name === "resources" && (
        <ResourcesPage
          user={user}
          onOpenResource={(resource: Resource) =>
            setSection({
              name: "resource-detail",
              id: resource.id,
              deleted: resource.deleted_at !== null,
            })
          }
          onCreate={() => setSection({ name: "resource-create" })}
        />
      )}

      {section.name === "resource-create" && (
        <ResourceCreatePage
          user={user}
          onCancel={() => setSection({ name: "resources" })}
          onCreated={(resource) =>
            setSection({ name: "resource-detail", id: resource.id, deleted: false })
          }
        />
      )}

      {section.name === "resource-detail" && (
        <ResourceDetailPage
          key={section.id}
          resourceId={section.id}
          initialDeleted={section.deleted}
          user={user}
          onBack={() => setSection({ name: "resources" })}
          onOpenResource={(id, deleted) =>
            setSection({ name: "resource-detail", id, deleted })
          }
        />
      )}

      {section.name === "networks" && <NetworksPage user={user} />}

      {section.name === "ip-pools" && <IpPoolsPage user={user} />}

      {section.name === "ip-addresses" && (
        <IpAddressesPage
          key={section.networkId ?? "all"}
          user={user}
          initialNetworkId={section.networkId}
        />
      )}

      {section.name === "services" && <ServicesPage user={user} />}

      {section.name === "audit" && <AuditPage user={user} />}

      {section.name === "system" && <SystemPage user={user} />}
      </main>
      </div>
    </div>
  );
}
