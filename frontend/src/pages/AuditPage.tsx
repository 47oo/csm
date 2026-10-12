import type { User } from "../api/auth";
import AuditQueryPanel from "../components/AuditQueryPanel";

interface AuditPageProps {
  user: User;
}

/**
 * F015 Audit 页（§28；DR-224/O-1：完整 Audit 独立页，不入 System）。
 * 仅 AUDIT_READ（ADMIN）可见：导航入口按 permissions 隐藏，页面再做一次
 * 本地呈现门控；两者都不替代服务端鉴权（§23/I-11，越权请求由服务端 403）。
 * 页面本身只读（A8/A30：无修改 / 删除 / 清空 Audit 入口）。
 */
export default function AuditPage({ user }: AuditPageProps) {
  const canAudit = user.permissions.includes("AUDIT_READ");

  return (
    <section className="panel">
      <h2>Audit（完整审计查询）</h2>
      {canAudit ? (
        <AuditQueryPanel />
      ) : (
        <p className="status status-error" role="alert">
          没有权限查询完整审计（需 AUDIT_READ 权限）。导航入口对无权限角色隐藏，
          服务端仍按权限矩阵拒绝越权请求（FORBIDDEN）。
        </p>
      )}
    </section>
  );
}
