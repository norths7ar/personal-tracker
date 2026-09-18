import type { RowSelectionState } from "@tanstack/react-table";
import { useState, type MouseEvent } from "react";

export function useRecordSelection() {
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const selectedIds = Object.keys(rowSelection)
    .filter((id) => rowSelection[id])
    .map(Number);
  const rowEvents = (id: number, edit: () => void) => ({
    onClick: (event: MouseEvent) => {
      if (
        (event.target as HTMLElement).closest(
          "button, input, a, [role=checkbox]",
        )
      )
        return;
      setRowSelection({ [id]: true });
    },
    onDoubleClick: (event: MouseEvent) => {
      if (
        (event.target as HTMLElement).closest(
          "button, input, a, [role=checkbox]",
        )
      )
        return;
      setRowSelection({ [id]: true });
      edit();
    },
  });
  return { rowSelection, setRowSelection, selectedIds, rowEvents };
}
