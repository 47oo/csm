import { Card, Pagination, Tag } from "antd";
import type { ReactNode } from "react";

export function SurfaceCard({
  title,
  extra,
  children,
  className,
  "aria-label": ariaLabel,
}: {
  title?: ReactNode;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
}) {
  const semanticTitle =
    typeof title === "string" ? (
      <h2 style={{ fontSize: "inherit", fontWeight: "inherit", margin: 0 }}>{title}</h2>
    ) : (
      title
    );

  return (
    <Card
      aria-label={ariaLabel}
      className={className}
      extra={extra}
      size="small"
      title={semanticTitle}
    >
      {children}
    </Card>
  );
}

export function StatusTag({ children, tone = "default" }: { children: ReactNode; tone?: string }) {
  return <Tag color={tone}>{children}</Tag>;
}

export function statusTone(value: string): string {
  switch (value) {
    case "ACTIVE":
    case "IDLE":
    case "RUNNING":
      return "success";
    case "ALLOC":
    case "AUTO":
      return "processing";
    case "DOWN":
    case "STOPPED":
    case "DELETED":
      return "error";
    case "RESERVED":
      return "warning";
    default:
      return "default";
  }
}

/** Shared adapter for the server-driven pagination contract used by list pages. */
export function ServerPagination({
  page,
  pageSize,
  total,
  appliedPageSize,
  onGotoPage,
  onChangePageSize,
}: {
  page: number;
  pageSize: number;
  total: number;
  appliedPageSize: number;
  onGotoPage: (page: number) => void;
  onChangePageSize: (pageSize: number) => void;
}) {
  return (
    <div className="pagination">
      <Pagination
        current={page}
        onChange={(nextPage, nextPageSize) => {
          if (nextPageSize !== appliedPageSize) {
            onChangePageSize(nextPageSize);
            return;
          }
          onGotoPage(nextPage);
        }}
        pageSize={pageSize}
        pageSizeOptions={["20", "50", "100"]}
        showSizeChanger
        showTotal={(count) => `共 ${count} 项`}
        size="small"
        total={total}
      />
    </div>
  );
}
