import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// F001 工程底座：仅脚手架接线。
// API 通过同源相对路径 /api/v1 由入口 Nginx 代理（架构 §1.2），
// 此处不配置任何代理目标或硬编码主机地址。
// F017：接入 Tailwind CSS v4（@tailwindcss/vite，D04-2 / D04-4）。
export default defineConfig({
  plugins: [react(), tailwindcss()],
});