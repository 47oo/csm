import { Modal } from "antd";
import { useEffect, useRef, type ReactNode } from "react";
import { createConfirmCommitGuard } from "../confirmDialogState.ts";

/**
 * F020 二次确认模态对话框（docs/features/F020/architecture.md DR-346–DR-354；
 * 样式基准：既有「吊销 API Key」Modal）。
 *
 * 纯展示原语：基于 AntD Modal，仅接收受控 props；不持业务状态、不构造请求、
 * 不 import ../api/*（onConfirm / onCancel 透传既有 confirm* / 关闭函数，
 * DR-349）。内部派生（DR-348/DR-353/DR-359）：
 * - maskClosable / keyboard = !confirmLoading：非提交态可 Esc / 遮罩关闭且不
 *   发请求；提交中两者失效、取消按钮禁用；
 * - okButtonProps.danger：删除 / 释放等危险操作红色确认键（恢复为普通）；
 * - confirmLoading：提交中确认按钮 loading（不可重复提交）；
 * - width 固定 520。
 *
 * 一次性提交守卫（DR-354，confirmDialogState.ts）：确认派发后、confirmLoading
 * 回落前，重复 onConfirm（双击 / 回车连发）被守卫忽略；提交结束（settle）或
 * 取消 / 关闭（reset）后可再次提交，均不自动重试。
 */
export function ConfirmDialog({
  open,
  title,
  children,
  okText = "确定",
  cancelText = "取消",
  danger = false,
  confirmLoading = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: ReactNode;
  children?: ReactNode;
  okText?: string;
  cancelText?: string;
  danger?: boolean;
  confirmLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // 实例级一次性提交守卫（每个对话框实例独立，T06d）
  const guardRef = useRef(createConfirmCommitGuard());
  const wasLoadingRef = useRef(false);

  // confirmLoading true → false：提交已结束（成功或失败）→ 释放守卫（T06c；
  // 失败时保持对话框打开由父组件控制，此处仅允许用户再次手动触发，不自动重试）
  useEffect(() => {
    if (wasLoadingRef.current && !confirmLoading) {
      guardRef.current.settle();
    }
    wasLoadingRef.current = confirmLoading;
  }, [confirmLoading]);

  // 对话框关闭（取消 / 成功后关闭）→ 重置守卫（T06b；重开可再次提交）
  useEffect(() => {
    if (!open) {
      guardRef.current.reset();
    }
  }, [open]);

  return (
    <Modal
      open={open}
      title={title}
      onOk={() => {
        if (!guardRef.current.tryBegin()) {
          return; // confirmLoading 回落前的重复派发（双击 / 回车连发）：忽略
        }
        onConfirm();
      }}
      onCancel={() => {
        guardRef.current.reset();
        onCancel();
      }}
      okText={okText}
      cancelText={cancelText}
      okButtonProps={{ danger }}
      confirmLoading={confirmLoading}
      cancelButtonProps={{ disabled: confirmLoading }}
      maskClosable={!confirmLoading}
      keyboard={!confirmLoading}
      width={520}
    >
      {children}
    </Modal>
  );
}
