import {
  Button as AntButton,
  Checkbox,
  Input as AntInput,
  Select as AntSelect,
  Table as AntTable,
  type TableColumnsType,
} from "antd";
import {
  Children,
  isValidElement,
  type ButtonHTMLAttributes,
  type ComponentProps,
  type ChangeEvent,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

type ButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> & {
  type?: "button" | "submit" | "reset";
  danger?: boolean;
};

/**
 * HTML-compatible Ant button used while preserving the existing event contract.
 * The visual variant is inferred from the existing semantic class names so page
 * business logic does not need to know about Ant Design.
 */
export function Button({ type, className, children, danger = false, disabled, ...props }: ButtonProps) {
  const classes = className ?? "";
  const visualType =
    type === "submit" ? "primary" : classes.includes("link-button") ? "link" : "default";
  const antProps = props as unknown as ComponentProps<typeof AntButton>;
  return (
    <AntButton
      {...antProps}
      className={className}
      danger={danger}
      disabled={disabled}
      htmlType={type ?? "submit"}
      type={visualType}
    >
      {children}
    </AntButton>
  );
}

export function Input({ type, checked, onChange, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  if (type === "checkbox") {
    return (
      <Checkbox
        aria-label={props["aria-label"]}
        checked={checked}
        disabled={props.disabled}
        id={props.id}
        name={props.name}
        onChange={(event) => onChange?.(event as unknown as ChangeEvent<HTMLInputElement>)}
      />
    );
  }

  const antProps = props as unknown as ComponentProps<typeof AntInput>;
  return (
    <AntInput
      {...antProps}
      style={{ width: "100%", ...antProps.style }}
      type={type}
      onChange={onChange}
    />
  );
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <AntInput.TextArea
      {...props}
      autoSize={{ minRows: props.rows ?? 3, maxRows: 10 }}
      style={{ width: "100%", ...props.style }}
    />
  );
}

type OptionShape = { label: ReactNode; value: string; disabled?: boolean };

function optionList(children: ReactNode): OptionShape[] {
  return Children.toArray(children).flatMap((child) => {
    if (!isValidElement(child) || child.type !== "option") {
      return [];
    }
    const props = child.props as {
      children?: ReactNode;
      value?: string | number;
      disabled?: boolean;
    };
    return [
      {
        label: props.children,
        value: String(props.value ?? ""),
        disabled: props.disabled,
      },
    ];
  });
}

/** Ant Select adapter that preserves the existing DOM-change callback shape. */
export function Select({
  children,
  value,
  onChange,
  className,
  id,
  name,
  disabled,
  required,
  style,
  "aria-label": ariaLabel,
  "aria-describedby": ariaDescribedBy,
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const options = optionList(children);
  return (
    <AntSelect
      aria-describedby={ariaDescribedBy}
      aria-label={ariaLabel}
      className={className}
      disabled={disabled}
      id={id}
      optionFilterProp="label"
      options={options}
      popupMatchSelectWidth
      showSearch
      status={required && (value === "" || value === undefined) ? undefined : undefined}
      style={{ width: "100%", ...style }}
      value={value === undefined ? undefined : String(value)}
      onChange={(nextValue) => {
        const target = { value: String(nextValue), name: name ?? "" } as HTMLSelectElement;
        onChange?.({ target, currentTarget: target } as unknown as React.ChangeEvent<HTMLSelectElement>);
      }}
    />
  );
}

type ParsedCell = { className?: string; content: ReactNode };
type ParsedRow = { key: string; className?: string; cells: ParsedCell[] };

function elementChildren(element: ReactElement): ReactNode[] {
  return Children.toArray((element.props as { children?: ReactNode }).children);
}

function findSection(children: ReactNode, tag: "thead" | "tbody"): ReactElement | null {
  return (
    Children.toArray(children).find(
      (child): child is ReactElement => isValidElement(child) && child.type === tag,
    ) ?? null
  );
}

function parseCells(row: ReactElement, expectedTag: "th" | "td"): ParsedCell[] {
  return elementChildren(row)
    .filter((cell): cell is ReactElement => isValidElement(cell) && cell.type === expectedTag)
    .map((cell) => {
      const props = cell.props as { children?: ReactNode; className?: string };
      return { className: props.className, content: props.children };
    });
}

/**
 * Converts the project's existing declarative table markup to Ant Table at the
 * shared boundary. Sorting, paging and row actions remain server-driven.
 */
export function DataTable({
  children,
  className,
  "aria-label": ariaLabel,
}: {
  children?: ReactNode;
  className?: string;
  "aria-label"?: string;
}) {
  const head = findSection(children, "thead");
  const body = findSection(children, "tbody");
  const headerRow = head
    ? elementChildren(head).find(
        (child): child is ReactElement => isValidElement(child) && child.type === "tr",
      )
    : undefined;
  const headings = headerRow ? parseCells(headerRow, "th") : [];
  const rows: ParsedRow[] = body
    ? elementChildren(body)
        .filter((child): child is ReactElement => isValidElement(child) && child.type === "tr")
        .map((row, rowIndex) => ({
          key: row.key === null ? String(rowIndex) : String(row.key),
          className: (row.props as { className?: string }).className,
          cells: parseCells(row, "td"),
        }))
    : [];

  const columnCount = Math.max(headings.length, ...rows.map((row) => row.cells.length), 1);
  const columns: TableColumnsType<ParsedRow> = Array.from({ length: columnCount }, (_, index) => ({
    key: String(index),
    title: headings[index]?.content ?? null,
    className: headings[index]?.className,
    onCell: (row) => ({ className: row.cells[index]?.className }),
    render: (_value, row) => row.cells[index]?.content ?? null,
  }));

  return (
    <AntTable<ParsedRow>
      aria-label={ariaLabel}
      className={className}
      columns={columns}
      dataSource={rows}
      locale={{ emptyText: "暂无数据" }}
      pagination={false}
      rowClassName={(row) => row.className ?? ""}
      rowKey="key"
      scroll={{ x: "max-content" }}
      size="small"
    />
  );
}
