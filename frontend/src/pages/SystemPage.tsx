import { useState } from "react";
import type { User } from "../api/auth";
import AccountManagementPanel from "../components/AccountManagementPanel";
import DeletedObjectsPanel from "../components/DeletedObjectsPanel";

interface SystemPageProps {
  user: User;
}

/** System 页 Tab（O-1/O-2：账号管理 + 已删对象管理，DR-224）。 */
type SystemTab = "account" | "deleted";

/**
 * F015 System 页（§28；DR-224；O-1/O-2 裁定）：
 * - 承载账号管理（USER_ADMIN：创建 / 角色 / 停用 / 启用）与已删对象管理
 *   （VIEW_DELETED：跨 8 类已删对象查看 + 按域恢复）两个 Tab；
 * - 完整 Audit 查询为独立 Audit 页（O-1），不入 System；不新增系统设置项；
 * - Tab 可见性按服务端返回的 permissions 显示 / 隐藏（前端隐藏不替代服务端
 *   鉴权，§23/I-11）；两者皆无时导航入口本身不显示，此处再做本地呈现门控。
 */
export default function SystemPage({ user }: SystemPageProps) {
  const canUserAdmin = user.permissions.includes("USER_ADMIN");
  const canViewDeleted = user.permissions.includes("VIEW_DELETED");

  const [tab, setTab] = useState<SystemTab>(canUserAdmin ? "account" : "deleted");
  // 防御：permissions 变化后 tab 指向已无权限的区域时回落到仍有权限的 Tab
  const activeTab: SystemTab = tab === "account" && !canUserAdmin ? "deleted" : tab;

  if (!canUserAdmin && !canViewDeleted) {
    return (
      <section className="panel">
        <h2>System（系统管理）</h2>
        <p className="status status-error" role="alert">
          没有权限访问系统管理（账号管理需 USER_ADMIN、已删对象管理需 VIEW_DELETED）。
          导航入口对无权限角色隐藏，服务端仍按权限矩阵拒绝越权请求（FORBIDDEN）。
        </p>
      </section>
    );
  }

  return (
    <section className="panel">
      <h2>System（系统管理）</h2>
      <div className="system-tabs" role="tablist" aria-label="系统管理分区">
        {canUserAdmin && (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "account"}
            className={activeTab === "account" ? "nav-link nav-link-active" : "nav-link"}
            onClick={() => setTab("account")}
          >
            账号管理
          </button>
        )}
        {canViewDeleted && (
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "deleted"}
            className={activeTab === "deleted" ? "nav-link nav-link-active" : "nav-link"}
            onClick={() => setTab("deleted")}
          >
            已删对象管理
          </button>
        )}
      </div>

      {activeTab === "account" && canUserAdmin && <AccountManagementPanel />}
      {activeTab === "deleted" && canViewDeleted && <DeletedObjectsPanel user={user} />}
    </section>
  );
}
