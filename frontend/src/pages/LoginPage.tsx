import { Button, Input } from "../components/ui/controls";
import { ErrorState } from "../components/ui/feedback";
import { SurfaceCard } from "../components/ui/surfaces";
import { useState, type FormEvent } from "react";
import { login, type User } from "../api/auth";
import { isApiError, type ApiErrorDetails } from "../api/client";

/** 从 422 信封 details.fields 提取字段级错误（Contract §1.2 VALIDATION_ERROR）。 */
function fieldErrors(details: ApiErrorDetails | null): string[] {
  if (details === null) {
    return [];
  }
  const fields = details["fields"];
  if (!Array.isArray(fields)) {
    return [];
  }
  const messages: string[] = [];
  for (const item of fields) {
    if (
      typeof item === "object" &&
      item !== null &&
      typeof (item as Record<string, unknown>)["field"] === "string" &&
      typeof (item as Record<string, unknown>)["message"] === "string"
    ) {
      const field = item as { field: string; message: string };
      messages.push(`${field.field}：${field.message}`);
    }
  }
  return messages;
}

/** 登录错误（展示消息来自统一信封，后端保证不泄露凭据 / 账号存在性）。 */
interface LoginError {
  message: string;
  /** 信封错误码（如 AUTH_INVALID_CREDENTIALS）；网络错误为 null。 */
  code: string | null;
  /** 422 字段级错误明细（可为空）。 */
  fields: string[];
}

interface LoginPageProps {
  /** 登录成功（服务端已 Set-Cookie）；user 来自 login 响应。 */
  onLoginSuccess: (user: User) => void;
}

/**
 * F002 最小登录页：username / password → POST /auth/login（credentials include）。
 * Loading（提交中，表单禁用）/ Success（回调切换到已登录视图）/ Error（信封消息）
 * 三态显式区分；错误文案不回显输入的凭据内容，不伪装成空结果。
 */
export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<LoginError | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { user } = await login(username, password);
      onLoginSuccess(user); // Success
    } catch (err: unknown) {
      setPassword(""); // 失败后清空密码输入，不保留敏感内容
      if (isApiError(err)) {
        // 401 AUTH_INVALID_CREDENTIALS / 403 CSRF / 422 校验 / 500 等：
        // 消息与错误码均来自信封，明确呈现，不静默重试
        setError({ message: err.message, code: err.code, fields: fieldErrors(err.details) });
      } else {
        // 网络层错误（fetch reject）：不伪装成业务错误
        setError({ message: "无法连接服务器，请稍后重试", code: null, fields: [] });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-main">
      <h1>CSM</h1>
      <p className="subtitle">Cluster Source Manager · 资源事实数据源</p>

      <SurfaceCard className="panel" title="登录">
        <form onSubmit={handleSubmit}>
          <div className="form-field">
            <label htmlFor="login-username">用户名</label>
            <Input
              id="login-username"
              name="username"
              type="text"
              autoComplete="username"
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="form-field">
            <label htmlFor="login-password">密码</label>
            <Input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              disabled={submitting}
            />
          </div>

          {error && (
            <ErrorState
              message={
                <div className="form-error">
                  <p>
                    登录失败：{error.message}
                    {error.code ? `（${error.code}）` : ""}
                  </p>
                  {error.fields.length > 0 && (
                    <ul>
                      {error.fields.map((fieldMessage) => (
                        <li key={fieldMessage}>{fieldMessage}</li>
                      ))}
                    </ul>
                  )}
                </div>
              }
            />
          )}

          <Button type="submit" disabled={submitting}>
            {submitting ? "正在登录…" : "登录"}
          </Button>
        </form>
      </SurfaceCard>
    </main>
  );
}
