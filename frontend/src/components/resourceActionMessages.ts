/**
 * 资源写操作错误明细的呈现文案（F021；docs/features/F021/architecture.md
 * DR-371/DR-380）。
 *
 * 纯逻辑模块（无 JSX / React / API 依赖）：scripts/smoke-client.mjs 以 Node
 * type stripping 直接加载本模块做机制级冒烟（同 src/api/*.ts、
 * ./confirmDialogState.ts；ResourceDetailPage.tsx / ResourcesPage.tsx 含 JSX
 * 无法被 Node 加载，故文案函数独立成本模块）。
 *
 * 两个函数自 ResourceDetailPage 逐字抽取（F021 纯重构，调用点与渲染行为
 * 不变）：详情页删除 / 恢复对话框与 ResourcesPage 行内删除对话框共用同一
 * 文案，不在页面内形成第二套规范。本模块不归一错误、不构造请求，仅把单条
 * 引用 / 冲突对象映射为可读文案；未知 object_type 原样 / 通用呈现，不伪装
 * 成已知类型。
 */

/**
 * CONFLICT reference_exists 单条引用的呈现文案（F006 DR-62：Resource 的
 * 引用来源为未删除的虚拟机，object_type="resource"，label=VM hostname）。
 * 未知 object_type 原样展示，不伪装成已知类型。
 */
export function referenceItemText(reference: {
  object_type: string;
  label: string | null;
}): string {
  const typeText =
    reference.object_type === "resource" ? "虚拟机（VM）" : reference.object_type;
  return reference.label ? `${typeText}：${reference.label}` : typeText;
}

/**
 * CONFLICT dependency_deleted 单条冲突的呈现文案（按 object_type 区分：
 * F004 所属 Cluster 仍软删；F006 恢复 VM 时宿主机 Host 仍软删 / 缺失，DR-63）。
 * 恢复均不覆盖新对象；未知 object_type 用通用文案。
 */
export function conflictItemText(conflict: { object_type: string; object_id: string }): string {
  if (conflict.object_type === "cluster") {
    return `所属集群（${conflict.object_id}）仍处于已删除状态，需先恢复该集群后再恢复资源。`;
  }
  if (conflict.object_type === "resource") {
    return `宿主机（Host，${conflict.object_id}）仍处于已删除状态或已不存在；需先恢复宿主机后再恢复该虚拟机（恢复不会覆盖宿主机或其上新对象）。`;
  }
  return `依赖对象 ${conflict.object_type}（${conflict.object_id}）仍处于已删除状态，需先恢复该依赖对象。`;
}
