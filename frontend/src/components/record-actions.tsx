import "@/styles/record-actions.css";
import { Pencil, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

export function RecordActions({
  count,
  busy,
  error,
  onEdit,
  onDelete,
  onClear,
}: {
  count: number;
  busy?: boolean;
  error?: Error | null;
  onEdit: () => void;
  onDelete: () => void;
  onClear: () => void;
}) {
  if (!count) return null;
  return (
    <div className="record-actions">
      <div className="record-actions-row">
        <strong className="record-actions-count">已选择 {count} 条</strong>
        <Button variant="ghost" disabled={busy} onClick={onClear}>
          取消选择
        </Button>
        <Button variant="outline" disabled={busy} onClick={onEdit}>
          <Pencil size={15} />
          {count > 1 ? "批量编辑" : "编辑"}
        </Button>
        <Button variant="danger" disabled={busy} onClick={onDelete}>
          <Trash2 size={15} />
          {busy ? "处理中…" : count > 1 ? "批量删除" : "删除"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="action-error">
          {error.message}
        </p>
      )}
    </div>
  );
}

export function BulkFieldToggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="bulk-field-toggle">
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onChange(Boolean(value))}
      />
      {label}
    </label>
  );
}

export function EditorFooter({ children }: { children: ReactNode }) {
  return <div className="editor-footer">{children}</div>;
}
