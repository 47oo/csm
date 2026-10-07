import { useEffect, useState } from "react";
import { getHealth, type Health } from "../api/client";

type HealthState =
  | { kind: "loading" }
  | { kind: "ok"; data: Health }
  | { kind: "error"; message: string };

/**
 * F001 后端健康状态面板（GET /api/v1/health，liveness 端点，架构 §1.4）。
 * Loading / 成功 / 失败三态显式区分，错误不得伪装为正常。
 * F002 起整合进登录态页面（应用壳）展示，不改变 F001 验收口径。
 */
export default function HealthPanel() {
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
  );
}
