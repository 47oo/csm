import { useState } from "react";
import { Alert, Button, Card, Form, Input } from "antd";
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

/** Ant Design Form 管理的登录表单值（对应原生受控 state username / password）。 */
interface LoginFormValues {
  username: string;
  password: string;
}

/**
 * F002 最小登录页：username / password → POST /auth/login（credentials include）。
 * Loading（提交中，表单禁用）/ Success（回调切换到已登录视图）/ Error（信封消息）
 * 三态显式区分；错误文案不回显输入的凭据内容，不伪装成空结果。
 */
export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [form] = Form.useForm<LoginFormValues>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<LoginError | null>(null);

  async function handleSubmit(values: LoginFormValues) {
    if (submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const { user } = await login(values.username, values.password);
      onLoginSuccess(user); // Success
    } catch (err: unknown) {
      form.setFieldsValue({ password: "" }); // 失败后清空密码输入，不保留敏感内容
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
    <main className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <h1 className="text-3xl font-bold tracking-tight text-gray-900">CSM</h1>
      <p className="mt-2 text-sm text-gray-500">Cluster Source Manager · 资源事实数据源</p>

      <Card title="登录" className="mt-8 w-full max-w-sm">
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          disabled={submitting}
          requiredMark={false}
        >
          <Form.Item
            label="用户名"
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            label="密码"
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input type="password" autoComplete="current-password" />
          </Form.Item>

          {error && (
            // Ant Design Alert 自带 role="alert"，保留无障碍错误语义
            <Alert
              className="mb-6"
              type="error"
              showIcon
              message={`登录失败：${error.message}${error.code ? `（${error.code}）` : ""}`}
              description={
                error.fields.length > 0 ? (
                  <ul className="mb-0 list-disc pl-5">
                    {error.fields.map((fieldMessage) => (
                      <li key={fieldMessage}>{fieldMessage}</li>
                    ))}
                  </ul>
                ) : undefined
              }
            />
          )}

          <Button type="primary" htmlType="submit" block disabled={submitting}>
            {submitting ? "正在登录…" : "登录"}
          </Button>
        </Form>
      </Card>
    </main>
  );
}
