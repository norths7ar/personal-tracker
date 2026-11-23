import { transactionColumns } from "./columns";
import { flexRender } from "@tanstack/react-table";
import { ArrowDownUp } from "lucide-react";
import { type Transaction } from "@/api/client";
import { Button } from "@/components/ui/button";
import { useRecordSelection } from "@/lib/use-record-selection";
import { cn } from "@/lib/utils";
import { TableMessage } from "./fields";
import "./ledger-page.css";
import type { Table } from "@tanstack/react-table";
export function LedgerTable({
  table,
  selectedCount,
  rowCount,
  pending,
  error,
  rowEvents,
  onEdit,
}: {
  table: Table<Transaction>;
  selectedCount: number;
  rowCount: number;
  pending: boolean;
  error: Error | null;
  rowEvents: ReturnType<typeof useRecordSelection>["rowEvents"];
  onEdit: (row: Transaction) => void;
}) {
  return (
    <div className="table-panel">
      <div className="ledger-toolbar">
        <span>
          共 {rowCount} 条{selectedCount ? `，已选择 ${selectedCount} 条` : ""}
        </span>
        <div className="pagination-controls">
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.previousPage()}
            disabled={!table.getCanPreviousPage()}
          >
            上一页
          </Button>
          <span>
            第 {table.getState().pagination.pageIndex + 1} / {Math.max(table.getPageCount(), 1)} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={() => table.nextPage()}
            disabled={!table.getCanNextPage()}
          >
            下一页
          </Button>
        </div>
      </div>
      <div className="table-scroll">
        <table className="ledger-table">
          <thead className="ledger-table-heading">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    style={{ width: header.getSize() }}
                    className="ledger-heading-cell"
                  >
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <button
                        className="table-sort"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <ArrowDownUp size={12} />
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {pending ? (
              <TableMessage columns={transactionColumns.length}>正在读取账目…</TableMessage>
            ) : error !== null ? (
              <TableMessage columns={transactionColumns.length} danger>
                {error?.message}
              </TableMessage>
            ) : table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  aria-selected={row.getIsSelected()}
                  {...rowEvents(row.original.id, () => onEdit(row.original))}
                  className={cn("ledger-row", row.getIsSelected() && "ledger-row-selected")}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="ledger-cell">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <TableMessage columns={transactionColumns.length}>没有符合条件的记录</TableMessage>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
