import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App as AntApp, ConfigProvider, theme } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./index.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("找不到 #root 挂载点");
}

createRoot(container).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: [theme.defaultAlgorithm, theme.compactAlgorithm],
        token: {
          colorPrimary: "#2563eb",
          colorInfo: "#2563eb",
          colorSuccess: "#16a34a",
          colorWarning: "#d97706",
          colorError: "#dc2626",
          colorText: "#172b4d",
          colorTextSecondary: "#52637a",
          colorBgLayout: "#f4f6fa",
          colorBorderSecondary: "#e5eaf1",
          borderRadius: 10,
          controlHeight: 40,
          fontSize: 16,
          colorTextPlaceholder: "#6b7280",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
        },
        components: {
          Card: { headerHeightSM: 48, headerFontSizeSM: 17, bodyPaddingSM: 24, headerPaddingSM: 24 },
          Button: { borderRadius: 6, fontWeight: 500, primaryShadow: "none", defaultShadow: "none" },
          Input: { borderRadius: 6 },
          Select: { borderRadius: 6 },
          Table: { cellPaddingBlockSM: 12, cellPaddingInlineSM: 16, headerBg: "#f5f7fb", headerColor: "#52637a", rowHoverBg: "#f3f7ff" },
          Statistic: { contentFontSize: 30, titleFontSize: 13 },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </StrictMode>
);
