import { useState } from "react";
import { Alert, Button, Card, Menu, Tag } from "antd";
import type { MenuProps } from "antd";
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
  const wide =
    inOverview ||
    inClusters ||
    inResources ||
    inNetworks ||
    inIpPools ||
    inIpAddresses ||
    inServices ||
    inAudit ||
    inSystem;

  // F015：Audit 仅 AUDIT_READ；System 需 USER_ADMIN（账号管理）或
  // VIEW_DELETED（已删对象管理）之一（DR-224）；按服务端返回的 permissions
  // 显示 / 隐藏导航入口，不替代服务端鉴权
  const canAudit = user.permissions.includes("AUDIT_READ");
  const canSystem =
    user.permissions.includes("USER_ADMIN") || user.permissions.includes("VIEW_DELETED");

  const activeNavKey = inOverview
    ? "overview"
    : inClusters
      ? "clusters"
      : inResources
        ? "resources"
        : inNetworks
          ? "networks"
          : inIpPools
            ? "ip-pools"
            : inIpAddresses
              ? "ip-addresses"
              : inServices
                ? "services"
                : inAudit
                  ? "audit"
                  : inSystem
                    ? "system"
                    : "overview";

  const navItems: MenuProps["items"] = [
    { key: "overview", label: "概览" },
    { key: "clusters", label: "Clusters" },
    { key: "resources", label: "Resources" },
    { key: "networks", label: "Networks" },
    { key: "ip-pools", label: "IP Pools" },
    { key: "ip-addresses", label: "IP Addresses" },
    { key: "services", label: "Services" },
    ...(canAudit ? [{ key: "audit", label: "Audit" }] : []),
    ...(canSystem ? [{ key: "system", label: "System" }] : []),
  ];

  function handleNav(key: string) {
    switch (key) {
      case "clusters":
        setSection({ name: "clusters" });
        break;
      case "resources":
        setSection({ name: "resources" });
        break;
      case "networks":
        setSection({ name: "networks" });
        break;
      case "ip-pools":
        setSection({ name: "ip-pools" });
        break;
      case "ip-addresses":
        setSection({ name: "ip-addresses" });
        break;
      case "services":
        setSection({ name: "services" });
        break;
      case "audit":
        setSection({ name: "audit" });
        break;
      case "system":
        setSection({ name: "system" });
        break;
      default:
        setSection({ name: "overview" });
    }
  }

  return (
    <main className={wide ? "mx-auto max-w-6xl px-6 py-8" : "mx-auto max-w-2xl px-6 py-12"}>
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="m-0 text-2xl font-semibold">CSM</h1>
          <p className="mt-1 text-gray-500">Cluster Source Manager · 资源事实数据源</p>
        </div>
        <div className="flex items-center gap-3 pt-1 whitespace-nowrap">
          <span className="font-semibold">{user.username}</span>
          <span className="text-sm text-gray-500">{user.role}</span>
          <Button type="default" onClick={handleLogout} disabled={loggingOut}>
            {loggingOut ? "正在登出…" : "登出"}
          </Button>
        </div>
      </header>

      {logoutError && (
        <Alert
          className="mt-4"
          type="error"
          role="alert"
          message={`登出失败：${logoutError}`}
        />
      )}

      <Menu
        className="mt-6"
        mode="horizontal"
        aria-label="主导航"
        selectedKeys={[activeNavKey]}
        items={navItems}
        onClick={({ key }) => handleNav(key)}
      />

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

          <Card className="mt-6" title="当前用户">
            <p className="m-0">
              用户名：{user.username}　角色：{user.role}　状态：{user.status}
            </p>
            <p className="mb-1 mt-3 text-sm text-gray-500">
              权限（由服务端按角色返回，仅用于界面显示，不构成安全边界）：
            </p>
            <p className="m-0">
              {user.permissions.length > 0 ? (
                user.permissions.map((permission) => (
                  <Tag key={permission} className="mr-1 mt-1">
                    {permission}
                  </Tag>
                ))
              ) : (
                <Tag className="mr-1 mt-1">无</Tag>
              )}
            </p>
          </Card>

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
  );
}