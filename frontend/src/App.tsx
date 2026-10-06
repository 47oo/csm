import { useEffect, useState } from "react";
import { getHealth, type Health } from "./api/client";

/**
 * F001 运维可见性页面（非业务页面）：
 * 展示应用名与后端健康状态（GET /api/v1/health，架构 §1.4 liveness 端点）。
 * Loading / 成功 / 失败三态显式区分，错误不得伪装为正常。
 */
type HealthState =
  | { kind: "loading" }
  | { kind: "ok"; data: Health }
  | { kind: "error"; message: string };

export default function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;

    getHealth()
      .then((data) => {
        if (!cancelled) {
          setHealth({ kind: "ok", data });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : String(error);
          setHealth({ kind: "error", message });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main>
      <h1>CSM</h1>
      <p className="subtitle">Cluster Source Manager · 资源事实数据源</p>

      <section className="panel">
        <h2>后端健康状态</h2>
        {health.kind === "loading" && (
          <p className="status status-loading">正在检查后端服务…</p>
        )}
        {health.kind === "ok" && (
          <p className="status status-ok">
            后端服务正常（status: {health.data.status}，service: {health.data.service}）
          </p>
        )}
        {health.kind === "error" && (
          <p className="status status-error">后端服务不可用：{health.message}</p>
        )}
      </section>
    </main>
  );
}
