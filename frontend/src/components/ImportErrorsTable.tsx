import { DataTable } from "./ui/controls";
import type { ImportValidationResult } from "../api/imports";

/**
 * 行错误表（导入预校验结果与写入整批失败共用；F014 与 F023 的 RowError 同形状，
 * Contract F014 §1.2/§3、F023 §1.2/§3）：行号 / 字段 / 原因 / 关联行，
 * 区域内滚动（errors 可能被服务端截断至 import_error_preview_limit 预览上限）。
 * 自 F014 ResourceImportPanel 逐字抽取（行为不变），供两套导入面板共用。
 */
export function ImportErrorsTable({ result }: { result: ImportValidationResult }) {
  return (
    <div className="import-errors-wrap">
      <DataTable className="data-table">
        <thead>
          <tr>
            <th>行号</th>
            <th>字段</th>
            <th>原因</th>
            <th>关联行</th>
          </tr>
        </thead>
        <tbody>
          {result.errors.map((rowError, index) => (
            <tr key={`${rowError.row}-${rowError.field}-${index}`}>
              <td className="mono">{rowError.row}</td>
              <td className="mono">{rowError.field}</td>
              <td className="import-error-reason">{rowError.reason}</td>
              <td className="mono">{rowError.related_row === null ? "—" : rowError.related_row}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </div>
  );
}
