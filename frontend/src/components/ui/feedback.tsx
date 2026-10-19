import { Alert, Empty, Skeleton, Spin } from "antd";
import type { ReactNode } from "react";

export function LoadingState({ label = "加载中…" }: { label?: string }) {
  return (
    <div className="flex min-h-24 items-center justify-center gap-3" role="status">
      <Spin size="small" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorState({ message, action }: { message: ReactNode; action?: ReactNode }) {
  return <Alert action={action} description={message} role="alert" showIcon type="error" />;
}

export function InfoState({ message }: { message: ReactNode }) {
  return <Alert description={message} role="note" showIcon type="info" />;
}

export function SuccessState({ message }: { message: ReactNode }) {
  return <Alert description={message} role="status" showIcon type="success" />;
}

export function WarningState({ message }: { message: ReactNode }) {
  return <Alert description={message} role="alert" showIcon type="warning" />;
}

export function EmptyState({ description = "暂无数据" }: { description?: ReactNode }) {
  return <Empty description={description} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
}

export function ContentSkeleton() {
  return <Skeleton active paragraph={{ rows: 3 }} title={false} />;
}
