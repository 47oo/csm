import { Button } from "./components/ui/controls";
import { ErrorState, LoadingState } from "./components/ui/feedback";
import { SurfaceCard } from "./components/ui/surfaces";
import { useEffect, useState } from "react";
import { me, type User } from "./api/auth";
import { displayError, isApiError, setUnauthorizedHandler } from "./api/client";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";

/**
 * F002 应用壳（架构 §1.8 前端最小接入，不引入路由库 / 状态管理库）：
 * 1. 启动 GET /auth/me 恢复登录态：Loading → 已登录 / 未认证（登录页）/
 *    恢复失败（非 401，显式错误 + 重试，不把服务错误伪装成未登录）；
 * 2. 任意请求 401（会话过期 / 无效 / 用户停用）→ 清登录态回登录页；
 * 3. 登录成功 → 已登录视图；登出 POST /auth/logout 成功后回登录页。
 */
type Phase =
  | { kind: "boot-loading" } // 正在 GET /auth/me
  | { kind: "boot-error"; message: string } // 恢复登录态失败（非 401），可重试
  | { kind: "login" } // 未认证 → 登录页
  | { kind: "authenticated"; user: User }; // 已登录

export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "boot-loading" });
  const [bootAttempt, setBootAttempt] = useState(0);

  // 全局 401 处理：任意 API 请求收到 401 即清登录态回登录页。
  // 登录页自身收到 401（凭据错误）时已在目标页面，重复触发无副作用。
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setPhase({ kind: "login" });
    });
    return () => {
      setUnauthorizedHandler(null);
    };
  }, []);

  // 启动恢复登录态；bootAttempt 变化时重试（重试按钮触发）。
  useEffect(() => {
    let cancelled = false;

    me()
      .then(({ user }) => {
        if (!cancelled) {
          setPhase({ kind: "authenticated", user });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) {
          return;
        }
        if (isApiError(error) && error.status === 401) {
          // 未认证 / 会话过期 / 用户停用：正常路径，显示登录页而非错误
          setPhase({ kind: "login" });
        } else {
          // 网络 / 服务端错误：显式呈现，允许重试，不伪装成未登录
          setPhase({ kind: "boot-error", message: displayError(error) });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [bootAttempt]);

  if (phase.kind === "boot-loading") {
    return (
      <main className="boot-main">
        <h1>CSM</h1>
        <p className="subtitle">Cluster Source Manager · 资源事实数据源</p>
        <SurfaceCard className="panel">
          <LoadingState label="正在恢复登录态…" />
        </SurfaceCard>
      </main>
    );
  }

  if (phase.kind === "boot-error") {
    return (
      <main className="boot-main">
        <h1>CSM</h1>
        <p className="subtitle">Cluster Source Manager · 资源事实数据源</p>
        <SurfaceCard className="panel">
          <ErrorState
            message={`恢复登录态失败：${phase.message}`}
            action={
              <Button type="button" onClick={() => setBootAttempt((attempt) => attempt + 1)}>
                重试
              </Button>
            }
          />
        </SurfaceCard>
      </main>
    );
  }

  if (phase.kind === "login") {
    return <LoginPage onLoginSuccess={(user) => setPhase({ kind: "authenticated", user })} />;
  }

  return <HomePage user={phase.user} onLoggedOut={() => setPhase({ kind: "login" })} />;
}
