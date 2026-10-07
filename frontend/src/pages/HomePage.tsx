import { useState } from "react";
import { logout, type User } from "../api/auth";
import { displayError, isApiError } from "../api/client";
import HealthPanel from "../components/HealthPanel";

interface HomePageProps {
  user: User;
  /** 登出完成（或会话已失效），由应用壳切回登录页。 */
  onLoggedOut: () => void;
}

/**
 * F002 已登录视图（最小应用壳，不追求复杂视觉效果）：
 * 当前用户信息 + 登出按钮 + F001 后端健康状态展示。
 * permissions 仅展示服务端返回值（前端不复制权限矩阵，不作为安全边界）。
 */
export default function HomePage({ user, onLoggedOut }: HomePageProps) {
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

  return (
    <main>
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
    </main>
  );
}
