import { Pencil, Trash2 } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";

export function RecordActions({ count, busy, error, onEdit, onDelete, onClear }: {
  count: number; busy?: boolean; error?: Error | null;
  onEdit: () => void; onDelete: () => void; onClear: () => void;
}) {
  if (!count) return null;
  return <div className="sticky bottom-4 z-20 rounded-lg border border-neutral-300 bg-white p-3 shadow-lg">
    <div className="flex flex-wrap items-center gap-3">
      <strong className="mr-auto text-sm">已选择 {count} 条</strong>
      <Button variant="ghost" disabled={busy} onClick={onClear}>取消选择</Button>
      <Button variant="outline" disabled={busy} onClick={onEdit}><Pencil size={15} />{count > 1 ? "批量编辑" : "编辑"}</Button>
      <Button variant="danger" disabled={busy} onClick={onDelete}><Trash2 size={15} />{busy ? "处理中…" : count > 1 ? "批量删除" : "删除"}</Button>
    </div>
    {error && <p role="alert" className="mt-2 text-sm text-red-600">{error.message}</p>}
  </div>;
}

export function BulkFieldToggle({ label, checked, disabled, onChange }: {
  label: string; checked: boolean; disabled?: boolean; onChange: (checked: boolean) => void;
}) {
  return <label className="flex items-center gap-2 text-sm font-medium">
    <Checkbox checked={checked} disabled={disabled} onCheckedChange={(value) => onChange(Boolean(value))} />{label}
  </label>;
}

export function EditorFooter({ children }: { children: ReactNode }) {
  return <div className="sticky -bottom-6 -mx-6 z-10 flex justify-end gap-2 border-t border-neutral-200 bg-white px-6 py-4">{children}</div>;
}
