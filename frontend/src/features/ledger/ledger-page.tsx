import { settingsApi } from "@/api/client";
import { transactionColumns } from "./columns";
import { LedgerFilters } from "./ledger-filters";
import { LedgerTable } from "./ledger-table";
import { useLedgerFilters } from "./use-ledger-filters";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { Download } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Transaction } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { RecordActions } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import { useRecordSelection } from "@/lib/use-record-selection";
import { csvCell } from "./utils";
import { BulkTransactionEditor } from "./bulk-editor";
import { TransactionEditor } from "./transaction-editor";
import "./ledger-page.css";

export function LedgerPage() {
  const queryClient = useQueryClient();
  const transactions = useQuery({
    queryKey: ["ledger", "transactions"],
    queryFn: api.transactions,
  });
  const categories = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    select: (settings) => settings.records.categories,
  });
  const [sorting, setSorting] = useState<SortingState>([]);
  const { rowSelection, setRowSelection, selectedIds, rowEvents } = useRecordSelection();
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [bulkEditing, setBulkEditing] = useState(false);

  const allRows = transactions.data ?? emptyTransactions;
  const filters = useLedgerFilters(allRows);
  const {
    filteredRows,
    categoryFilter,
    search,
    subcategoryFilter,
    typeFilter,
    startDate,
    endDate,
  } = filters;
  const table = useReactTable({
    data: filteredRows,
    columns: transactionColumns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getRowId: (row) => String(row.id),
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 50 } },
  });

  useEffect(() => {
    table.setPageIndex(0);
    setRowSelection({});
  }, [
    categoryFilter,
    search,
    subcategoryFilter,
    table,
    typeFilter,
    startDate,
    endDate,
    setRowSelection,
  ]);

  const selectedRecord =
    selectedIds.length === 1 ? (allRows.find((row) => row.id === selectedIds[0]) ?? null) : null;
  const selectedRecords = allRows.filter((row) => selectedIds.includes(row.id));

  const deletion = useMutation({
    mutationFn: api.deleteTransactions,
    onSuccess: (_, ids) => {
      void invalidateFinance(queryClient);
      queryClient.setQueryData<Transaction[]>(["ledger", "transactions"], (current = []) =>
        current.filter((row) => !ids.includes(row.id)),
      );
      setRowSelection({});
    },
  });

  const deleteSelected = () => {
    if (!selectedIds.length) return;
    if (window.confirm(`确定删除选中的 ${selectedIds.length} 条记录吗？`)) {
      deletion.mutate(selectedIds);
    }
  };

  const exportCsv = () => {
    const header = ["ID", "日期", "类型", "描述", "金额", "主类别", "子类别", "备注"];
    const body = filteredRows.map((row) => [
      row.id,
      row.date,
      row.type,
      row.description,
      row.amount,
      row.category ?? "",
      row.subcategory ?? "",
      row.notes ?? "",
    ]);
    const csv = [header, ...body].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8" }));
    link.download = "transactions.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <section className="page-stack">
      <header className="page-heading">
        <div>
          <h1 className="page-title">账目</h1>
        </div>
        <Button variant="outline" onClick={exportCsv} disabled={!filteredRows.length}>
          <Download size={16} />
          导出当前结果
        </Button>
      </header>

      <LedgerFilters filters={filters} />
      <LedgerTable
        table={table}
        selectedCount={selectedIds.length}
        rowCount={filteredRows.length}
        pending={transactions.isPending}
        error={transactions.error}
        rowEvents={rowEvents}
        onEdit={setEditing}
      />

      <RecordActions
        count={selectedIds.length}
        busy={deletion.isPending}
        error={deletion.error}
        onEdit={() => (selectedRecord ? setEditing(selectedRecord) : setBulkEditing(true))}
        onDelete={deleteSelected}
        onClear={() => setRowSelection({})}
      />

      {bulkEditing && (
        <BulkTransactionEditor
          transactions={selectedRecords}
          categories={categories.data ?? {}}
          onClose={() => setBulkEditing(false)}
          onSaved={(changes) => {
            invalidateFinance(queryClient);
            queryClient.setQueryData<Transaction[]>(["ledger", "transactions"], (current = []) =>
              current.map((row) =>
                selectedIds.includes(row.id)
                  ? {
                      ...row,
                      ...changes,
                      reviewed:
                        "category" in changes || "subcategory" in changes ? true : row.reviewed,
                    }
                  : row,
              ),
            );
            setBulkEditing(false);
            setRowSelection({});
          }}
        />
      )}

      <TransactionEditor
        transaction={editing}
        transactions={allRows}
        categories={categories.data ?? {}}
        onClose={() => setEditing(null)}
        onSaved={(updated) => {
          invalidateFinance(queryClient);
          queryClient.setQueryData<Transaction[]>(["ledger", "transactions"], (current = []) =>
            current.map((row) => (row.id === updated.id ? updated : row)),
          );
          setEditing(null);
        }}
        onRefresh={() => {
          void invalidateFinance(queryClient);
          setRowSelection({});
          setEditing(null);
        }}
      />
    </section>
  );
}

const emptyTransactions: Transaction[] = [];
