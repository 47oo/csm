import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import { StyleProvider } from "@ant-design/cssinjs";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./index.css";

// F017：Ant Design 主题唯一权威（seed token），与 index.css 的 @theme 共享最小集。
const fontStack =
  'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

const container = document.getElementById("root");
if (!container) {
  throw new Error("找不到 #root 挂载点");
}

createRoot(container).render(
  <StrictMode>
    <StyleProvider layer>
      <ConfigProvider
        locale={zhCN}
        theme={{ token: { colorPrimary: "#2563eb", borderRadius: 6, fontFamily: fontStack } }}
      >
        <AntApp>
          <App />
        </AntApp>
      </ConfigProvider>
    </StyleProvider>
  </StrictMode>
);