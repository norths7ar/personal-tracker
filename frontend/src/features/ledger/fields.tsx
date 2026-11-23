import { type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { selectClass } from "./utils";

export function Info({ children }: { children: ReactNode }) {
  return <div className="editor-note">{children}</div>;
}

export function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter-field">
      <span>{label}</span>
      <select
        className={selectClass}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option>全部</option>
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

export function FormField({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="form-field">
      <span>{label}</span>
      {children}
      {error && <span className="field-error">{error}</span>}
    </label>
  );
}

export function TableMessage({
  columns,
  danger,
  children,
}: {
  columns: number;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <tr>
      <td colSpan={columns} className={cn("ledger-empty", danger && "ledger-error")}>
        {children}
      </td>
    </tr>
  );
}
