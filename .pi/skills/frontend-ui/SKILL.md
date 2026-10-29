---
name: frontend-ui
description: 在 CSM 前端设计、实现、测试或 Review 涉及 React 页面、交互组件、表单、列表或样式时，按现有 Ant Design 与 Tailwind CSS 基线选择组件、布局、主题和验证方式。不用于纯后端或数据库任务。
---

# 前端 UI 实现

先读取 `docs/project/implementation-rules.md`、当前 Feature 的验收与 Contract，再核对 `frontend/package.json`、`frontend/src/main.tsx`、`frontend/vite.config.ts`、`frontend/src/index.css` 和 `frontend/src/components/ui/`。依赖版本与插件接线以当前文件为准，不凭记忆使用其它大版本 API。

## 组件与样式边界

1. 交互和语义组件优先复用 `frontend/src/components/ui/` 的项目适配层；现有适配层不能表达需求时，先判断应扩展共享适配层还是直接使用 Ant Design，避免各页面重复封装。
2. 表单控件、按钮、表格、分页、反馈、空态、加载态、卡片、描述和图标优先使用 Ant Design / `@ant-design/icons`，保留 Contract 要求的受控值、事件、校验、权限和错误语义。不要为相同能力再造一套基础组件。
3. Tailwind CSS 用于页面布局、间距、尺寸、响应式和少量组合样式；重复的语义样式可在 `index.css` 中用 `@apply` 集中。避免用大量任意值、`!important` 或全局 `.ant-*` 覆盖与 Ant Design 内部实现竞争。
4. Ant Design 的颜色、字号、圆角、密度等全局视觉通过 `ConfigProvider` token/component token 维护；局部业务状态优先使用语义组件属性和项目共享组件，不复制主题常量。
5. 保留现有 CSS class 和适配层的兼容路径；当前任务只迁移受影响区域，不借单个 Feature 全量重写页面或删除旧样式。

## 交互检查

- Loading / Success / Empty / Error、未知值、禁用态和提交中状态均显式呈现，错误不伪装为空数据。
- 服务端权限、版本冲突和 Contract 校验仍是权威；组件隐藏、本地校验或 Ant Design 表单状态不替代服务端保证。
- 表格分页、排序和过滤继续遵循服务端契约；不要让 Ant Design 默认客户端行为静默改变查询语义。
- 保持可访问名称、标签关联、键盘操作、焦点和必要的 `aria-*`；响应式布局需覆盖窄屏，不以桌面视觉通过代替交互验证。

## 验证

按影响选择验证命令，不默认跑全套（`build` 已包含 TypeScript 检查，仅 TS / 类型改动时 `typecheck` 已覆盖）：

```bash
cd frontend
npm run typecheck        # 纯类型 / 逻辑改动
npm run build            # 构建产物 / 分包 / 入口改动
npm run smoke:client     # 客户端请求、状态机与业务规则改动
```

改动同时涉及类型与客户端逻辑时，两者都跑并记录真实输出；不要把 `typecheck` 与 `build` 当成互不相关的两道保证重复执行。交互回归（弹层、焦点、第 101 条候选、401、409 刷新、载体切换、危险操作取消等）需有**可重复执行**的断言入口；本仓库当前以 `smoke:client` 与组件 / 逻辑级测试承载，未安装浏览器 E2E 依赖时，浏览器专项验证属环境侧验证，必须标为未入库、未重复执行，不得当作仓库保证。

交付时说明复用或新增的 Ant Design 组件、Tailwind/CSS 变更、主题影响、兼容处理及验证证据；新 UI 约定应落到共享组件或权威实现文档，不在页面内形成第二套规范。
