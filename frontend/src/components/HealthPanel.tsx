import { useEffect, useState } from "react";
import { Alert } from "antd";
import { getHealth, type Health } from "../api/client";
import { ErrorState, LoadingState } from "./ui/feedback";
import { SurfaceCard } from "./ui/surfaces";

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
    <SurfaceCard className="panel" title="后端健康状态">
      {health.kind === "loading" && (
        <LoadingState label="正在检查后端服务…" />
      )}
      {health.kind === "ok" && (
        <Alert
          message={`后端服务正常（status: ${health.data.status}，service: ${health.data.service}）`}
          showIcon
          type="success"
        />
      )}
      {health.kind === "error" && (
        <ErrorState message={`后端服务不可用：${health.message}`} />
      )}
    </SurfaceCard>
  );
}
