import { useState } from "react";
import { logout, type User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import type { Cluster } from "../api/clusters";
import type { Resource } from "../api/resources";
import HealthPanel from "../components/HealthPanel";
import ClustersPage from "./ClustersPage";
import ClusterCreatePage from "./ClusterCreatePage";
import ClusterDetailPage from "./ClusterDetailPage";
import ResourcesPage from "./ResourcesPage";
import ResourceCreatePage from "./ResourceCreatePage";
import ResourceDetailPage from "./ResourceDetailPage";
import NetworksPage from "./NetworksPage";

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
  | { name: "networks" };

/**
 * F002 已登录视图 + F003/F004/F008 导航壳（架构 §1.8，不追求复杂视觉效果）：
 * 概览（当前用户 + 后端健康）/ Clusters（列表 / 新建 / 详情）/ Resources
 * （列表 / 新建 / 详情）/ Networks（列表 / 新建 / 编辑，F008）。各入口对
 * 全部已登录角色可见
 * （READ 全角色）；写 / 删 / 恢复 / 已删可见性仅按服务端返回的 permissions
 * 显示对应控件——隐藏不替代鉴权，服务端仍按 §23 矩阵执行（越权请求 403
 * 由页面明确呈现）。
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
  const wide = inClusters || inResources || inNetworks;

  return (
    <main className={wide ? "main-wide" : undefined}>
      <header className="app-header">
        <div>
          <h1>CSM</h1>
          <p className="subtitle">Cluster Source Manager · 资源事实数据源</p>
        </div>
        <div className="user-box">
          <span className="user-name">{user.username}</span>
          <span className="user-role">{user.role}</span>
          <button type="button" onClick={handleLogout} disabled={loggingOut}>
            {loggingOut ? "正在登出…" : "登出"}
          </button>
        </div>
      </header>

      {logoutError && (
        <p className="status status-error" role="alert">
          登出失败：{logoutError}
        </p>
      )}

      <nav className="app-nav" aria-label="主导航">
        <button
          type="button"
          className={section.name === "overview" ? "nav-link nav-link-active" : "nav-link"}
          onClick={() => setSection({ name: "overview" })}
        >
          概览
        </button>
        <button
          type="button"
          className={inClusters ? "nav-link nav-link-active" : "nav-link"}
          onClick={() => setSection({ name: "clusters" })}
        >
          Clusters
        </button>
        <button
          type="button"
          className={inResources ? "nav-link nav-link-active" : "nav-link"}
          onClick={() => setSection({ name: "resources" })}
        >
          Resources
        </button>
        <button
          type="button"
          className={inNetworks ? "nav-link nav-link-active" : "nav-link"}
          onClick={() => setSection({ name: "networks" })}
        >
          Networks
        </button>
      </nav>

      {section.name === "overview" && (
        <>
          <section className="panel">
            <h2>当前用户</h2>
            <p className="status">
              用户名：{user.username}　角色：{user.role}　状态：{user.status}
            </p>
            <p className="permissions-note">
              权限（由服务端按角色返回，仅用于界面显示，不构成安全边界）：
            </p>
            <p className="permissions">
              {user.permissions.length > 0 ? (
                user.permissions.map((permission) => (
                  <span key={permission} className="permission-badge">
                    {permission}
                  </span>
                ))
              ) : (
                <span className="permission-badge">无</span>
              )}
            </p>
          </section>

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
    </main>
  );
}
