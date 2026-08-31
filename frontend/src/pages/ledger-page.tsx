import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type RowSelectionState,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDownUp, Download, Pencil, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  api,
  type RefundCreate,
  type SubscriptionCreate,
  type Transaction,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const columnHelper = createColumnHelper<Transaction>();
const transactionTypes = ["支出", "收入", "迁移"] as const;
const emptyTransactions: Transaction[] = [];

export function LedgerPage() {
  const queryClient = useQueryClient();
  const transactions = useQuery({ queryKey: ["transactions"], queryFn: api.transactions });
  const categories = useQuery({ queryKey: ["categories"], queryFn: api.categories });
  const [typeFilter, setTypeFilter] = useState("全部");
  const [categoryFilter, setCategoryFilter] = useState("全部");
  const [subcategoryFilter, setSubcategoryFilter] = useState("全部");
  const [search, setSearch] = useState("");
  const [sorting, setSorting] = useState<SortingState>([]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [editing, setEditing] = useState<Transaction | null>(null);

  const allRows = transactions.data ?? emptyTransactions;
  const filteredRows = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return allRows.filter((row) => {
      if (typeFilter !== "全部" && row.type !== typeFilter) return false;
      if (categoryFilter !== "全部" && row.category !== categoryFilter) return false;
      if (subcategoryFilter !== "全部" && row.subcategory !== subcategoryFilter) return false;
      if (!needle) return true;
      return [row.description, row.category, row.subcategory, row.notes]
        .filter(Boolean)
        .some((value) => value!.toLocaleLowerCase().includes(needle));
    });
  }, [allRows, categoryFilter, search, subcategoryFilter, typeFilter]);

  const categoryOptions = useMemo(() => {
    const source = typeFilter === "全部" ? allRows : allRows.filter((row) => row.type === typeFilter);
    return unique(source.map((row) => row.category));
  }, [allRows, typeFilter]);
  const subcategoryOptions = useMemo(() => {
    return unique(
      allRows
        .filter((row) => typeFilter === "全部" || row.type === typeFilter)
        .filter((row) => categoryFilter === "全部" || row.category === categoryFilter)
        .map((row) => row.subcategory),
    );
  }, [allRows, categoryFilter, typeFilter]);

  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        header: ({ table }) => (
          <Checkbox
            aria-label="选择当前页"
            checked={table.getIsAllPageRowsSelected() || (table.getIsSomePageRowsSelected() && "indeterminate")}
            onCheckedChange={(checked) => table.toggleAllPageRowsSelected(Boolean(checked))}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`选择记录 ${row.original.id}`}
            checked={row.getIsSelected()}
            onCheckedChange={(checked) => row.toggleSelected(Boolean(checked))}
          />
        ),
        size: 40,
      }),
      columnHelper.accessor("date", { header: "日期", size: 110 }),
      columnHelper.accessor("type", { header: "类型", size: 75 }),
      columnHelper.accessor("description", { header: "描述", size: 360 }),
      columnHelper.accessor("amount", {
        header: "金额",
        cell: ({ getValue }) => formatMoney(getValue()),
        size: 110,
      }),
      columnHelper.accessor("category", { header: "主类别", size: 110 }),
      columnHelper.accessor("subcategory", { header: "子类别", size: 120 }),
      columnHelper.accessor("notes", { header: "备注", size: 220 }),
    ],
    [],
  );

  const table = useReactTable({
    data: filteredRows,
    columns,
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
  }, [categoryFilter, search, subcategoryFilter, table, typeFilter]);

  const selectedIds = Object.entries(rowSelection)
    .filter(([, selected]) => selected)
    .map(([id]) => Number(id));
  const selectedRecord = selectedIds.length === 1
    ? allRows.find((row) => row.id === selectedIds[0]) ?? null
    : null;

  const deletion = useMutation({
    mutationFn: api.deleteTransactions,
    onSuccess: (_, ids) => {
      queryClient.setQueryData<Transaction[]>(["transactions"], (current = []) =>
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
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">账目</h1>
          <p className="mt-1 text-sm text-neutral-500">筛选、排序、翻页和勾选都在本地完成。</p>
        </div>
        <Button variant="outline" onClick={exportCsv} disabled={!filteredRows.length}>
          <Download size={16} />导出当前结果
        </Button>
      </header>

      <div className="grid gap-3 rounded-lg border border-neutral-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-[160px_180px_180px_minmax(240px,1fr)]">
        <FilterSelect label="类型" value={typeFilter} options={[...transactionTypes]} onChange={(value) => {
          setTypeFilter(value); setCategoryFilter("全部"); setSubcategoryFilter("全部");
        }} />
        <FilterSelect label="主类别" value={categoryFilter} options={categoryOptions} onChange={(value) => {
          setCategoryFilter(value); setSubcategoryFilter("全部");
        }} />
        <FilterSelect label="子类别" value={subcategoryFilter} options={subcategoryOptions} onChange={setSubcategoryFilter} />
        <label className="space-y-1 text-sm font-medium">
          <span>搜索</span>
          <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="描述、分类或备注" />
        </label>
      </div>

      <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-200 px-4 py-3 text-sm text-neutral-500">
          <span>共 {filteredRows.length} 条{selectedIds.length ? `，已选择 ${selectedIds.length} 条` : ""}</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>上一页</Button>
            <span>第 {table.getState().pagination.pageIndex + 1} / {Math.max(table.getPageCount(), 1)} 页</span>
            <Button variant="outline" size="sm" onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>下一页</Button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-collapse text-sm">
            <thead className="bg-neutral-50 text-left text-xs font-medium text-neutral-500">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <th key={header.id} style={{ width: header.getSize() }} className="border-b border-neutral-200 px-3 py-2.5">
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          className="flex items-center gap-1 hover:text-neutral-900"
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
              {transactions.isPending ? (
                <TableMessage columns={columns.length}>正在读取账目…</TableMessage>
              ) : transactions.isError ? (
                <TableMessage columns={columns.length} danger>{transactions.error.message}</TableMessage>
              ) : table.getRowModel().rows.length ? (
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className={cn("border-b border-neutral-100 last:border-0 hover:bg-neutral-50", row.getIsSelected() && "bg-amber-50 hover:bg-amber-50")}>
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="max-w-80 truncate px-3 py-2.5">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              ) : (
                <TableMessage columns={columns.length}>没有符合条件的记录</TableMessage>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selectedIds.length > 0 && (
        <div className="sticky bottom-4 z-20 flex flex-wrap items-center gap-3 rounded-lg border border-neutral-300 bg-white p-3 shadow-lg">
          <strong className="mr-auto text-sm">已选择 {selectedIds.length} 条</strong>
          {selectedRecord && (
            <Button variant="outline" onClick={() => setEditing(selectedRecord)}>
              <Pencil size={15} />编辑
            </Button>
          )}
          <Button variant="danger" onClick={deleteSelected} disabled={deletion.isPending}>
            <Trash2 size={15} />{deletion.isPending ? "删除中…" : "批量删除"}
          </Button>
        </div>
      )}

      <TransactionEditor
        transaction={editing}
        transactions={allRows}
        categories={categories.data ?? {}}
        onClose={() => setEditing(null)}
        onSaved={(updated) => {
          queryClient.setQueryData<Transaction[]>(["transactions"], (current = []) =>
            current.map((row) => row.id === updated.id ? updated : row),
          );
          setEditing(null);
        }}
        onRefresh={() => {
          queryClient.invalidateQueries({ queryKey: ["transactions"] });
          queryClient.invalidateQueries({ queryKey: ["expense-analysis"] });
          queryClient.invalidateQueries({ queryKey: ["cross-period"] });
          queryClient.invalidateQueries({ queryKey: ["home-summary"] });
          setRowSelection({});
          setEditing(null);
        }}
      />
    </section>
  );
}

const editSchema = z.object({
  type: z.enum(transactionTypes),
  description: z.string().trim().min(1, "请填写描述"),
  amount: z.number().positive("金额须大于 0"),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "日期格式不正确"),
  category: z.string(),
  subcategory: z.string(),
  notes: z.string(),
});
type EditValues = z.infer<typeof editSchema>;

function TransactionEditor({ transaction, transactions, categories, onClose, onSaved, onRefresh }: {
  transaction: Transaction | null;
  transactions: Transaction[];
  categories: Record<string, Record<string, string[]>>;
  onClose: () => void;
  onSaved: (transaction: Transaction) => void;
  onRefresh: () => void;
}) {
  const [tab, setTab] = useState<"edit" | "amortization" | "recurring" | "refund">("edit");
  const form = useForm<EditValues>({ resolver: zodResolver(editSchema) });
  const entryType = form.watch("type");
  const category = form.watch("category");
  const categoryOptions = Object.keys(categories[entryType] ?? {});
  const subcategoryOptions = categories[entryType]?.[category] ?? [];
  const typeRegistration = form.register("type");
  const categoryRegistration = form.register("category");
  const update = useMutation({
    mutationFn: (values: EditValues) => api.updateTransaction(transaction!.id, {
      ...values,
      category: values.category || null,
      subcategory: values.subcategory || null,
      notes: values.notes || null,
    }),
    onSuccess: onSaved,
  });

  useEffect(() => {
    if (!transaction) return;
    setTab("edit");
    form.reset({
      type: transaction.type,
      description: transaction.description,
      amount: transaction.amount,
      date: transaction.date,
      category: transaction.category ?? "",
      subcategory: transaction.subcategory ?? "",
      notes: transaction.notes ?? "",
    });
  }, [form, transaction]);

  return (
    <Dialog open={Boolean(transaction)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑账目</DialogTitle>
          <DialogDescription>保存后只更新本地缓存中的这一行，不重新加载整个页面。</DialogDescription>
        </DialogHeader>
        {transaction && (
          <>
            <div className="mb-5 grid grid-cols-4 gap-1 rounded-lg bg-neutral-100 p-1">
              {([
                ["edit", "编辑"],
                ["amortization", "摊销"],
                ["recurring", "周期"],
                ["refund", "退款"],
              ] as const).map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={cn("rounded-md px-2 py-2 text-sm", tab === value && "bg-white font-medium shadow-sm")}
                  onClick={() => setTab(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "edit" && <form className="space-y-4" onSubmit={form.handleSubmit((values) => update.mutate(values))}>
            <FormField label="类型">
              <select
                className={selectClass}
                {...typeRegistration}
                onChange={(event) => {
                  typeRegistration.onChange(event);
                  form.setValue("category", "");
                  form.setValue("subcategory", "");
                }}
              >
                {transactionTypes.map((type) => <option key={type}>{type}</option>)}
              </select>
            </FormField>
            <FormField label="描述" error={form.formState.errors.description?.message}>
              <Input {...form.register("description")} />
            </FormField>
            <div className="grid grid-cols-2 gap-3">
              <FormField label="金额" error={form.formState.errors.amount?.message}>
                <Input type="number" min="0.01" step="0.01" {...form.register("amount", { valueAsNumber: true })} />
              </FormField>
              <FormField label="日期" error={form.formState.errors.date?.message}>
                <Input type="date" {...form.register("date")} />
              </FormField>
            </div>
            <FormField label="主类别">
              <select
                className={selectClass}
                {...categoryRegistration}
                onChange={(event) => {
                  categoryRegistration.onChange(event);
                  form.setValue("subcategory", "");
                }}
              >
                <option value="">无</option>
                {categoryOptions.map((item) => <option key={item}>{item}</option>)}
              </select>
            </FormField>
            <FormField label="子类别">
              <select className={selectClass} {...form.register("subcategory")}>
                <option value="">无</option>
                {subcategoryOptions.map((item) => <option key={item}>{item}</option>)}
              </select>
            </FormField>
            <FormField label="备注">
              <textarea className="min-h-24 w-full rounded-md border border-neutral-300 p-3 text-sm outline-none focus:border-neutral-500 focus:ring-2 focus:ring-neutral-200" {...form.register("notes")} />
            </FormField>
            {update.isError && <p className="text-sm text-red-600">{update.error.message}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>取消</Button>
              <Button type="submit" disabled={update.isPending}>{update.isPending ? "保存中…" : "保存修改"}</Button>
            </div>
            </form>}
            {tab === "amortization" && <AmortizationForm transaction={transaction} onSaved={onSaved} />}
            {tab === "recurring" && <RecurringForm transaction={transaction} onSaved={onRefresh} />}
            {tab === "refund" && <RefundForm transaction={transaction} transactions={transactions} onSaved={onRefresh} />}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function AmortizationForm({ transaction, onSaved }: { transaction: Transaction; onSaved: (record: Transaction) => void }) {
  const [months, setMonths] = useState(String(transaction.amortization_months ?? 12));
  const [startMonth, setStartMonth] = useState((transaction.amortization_start ?? transaction.date).slice(0, 7));
  const update = useMutation({
    mutationFn: () => api.updateTransaction(transaction.id, {
      amortization_months: Number(months),
      amortization_start: `${startMonth}-01`,
    }),
    onSuccess: onSaved,
  });
  if (transaction.type !== "支出") return <Info>只有支出记录可以设置摊销。</Info>;
  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); update.mutate(); }}>
      <p className="text-sm text-neutral-500">把这笔已发生的支出分摊到多个自然月。</p>
      <FormField label="摊销月数"><Input type="number" min="2" max="120" value={months} onChange={(event) => setMonths(event.target.value)} /></FormField>
      <FormField label="摊销开始月份"><Input type="month" value={startMonth} onChange={(event) => setStartMonth(event.target.value)} /></FormField>
      {update.isError && <p className="text-sm text-red-600">{update.error.message}</p>}
      <Button className="w-full" disabled={update.isPending || Number(months) < 2}>{update.isPending ? "保存中…" : "保存摊销"}</Button>
    </form>
  );
}

function RefundForm({ transaction, transactions, onSaved }: { transaction: Transaction; transactions: Transaction[]; onSaved: () => void }) {
  const refunded = transactions.filter((item) => item.refund_for_id === transaction.id).reduce((sum, item) => sum + item.amount, 0);
  const remaining = Math.max(0, transaction.amount - refunded);
  const [entry, setEntry] = useState<RefundCreate>({ description: `${transaction.description} 退款`, amount: remaining, date: formatDate(new Date()) });
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useMutation({ mutationFn: () => api.createRefund(transaction.id, entry, idempotencyKey), onSuccess: onSaved });
  if (transaction.type !== "支出") return <Info>只有支出记录可以关联退款。</Info>;
  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
      <p className="text-sm text-neutral-500">已关联退款 {formatMoney(refunded)}，剩余可退 {formatMoney(remaining)}。</p>
      <FormField label="退款描述"><Input value={entry.description} onChange={(event) => setEntry({ ...entry, description: event.target.value })} /></FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="退款金额"><Input type="number" min="0.01" max={remaining} step="0.01" value={entry.amount} onChange={(event) => setEntry({ ...entry, amount: Number(event.target.value) })} /></FormField>
        <FormField label="退款日期"><Input type="date" value={entry.date} onChange={(event) => setEntry({ ...entry, date: event.target.value })} /></FormField>
      </div>
      {create.isError && <p className="text-sm text-red-600">{create.error.message}</p>}
      <Button className="w-full" disabled={create.isPending || entry.amount <= 0 || entry.amount > remaining || !entry.description.trim()}>{create.isPending ? "保存中…" : "保存退款"}</Button>
    </form>
  );
}

function RecurringForm({ transaction, onSaved }: { transaction: Transaction; onSaved: () => void }) {
  const [name, setName] = useState(transaction.description);
  const [nextDate, setNextDate] = useState(formatDate(new Date()));
  const [mode, setMode] = useState<"same_day" | "fixed_days">("same_day");
  const [interval, setInterval] = useState("1");
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useMutation({
    mutationFn: () => {
      const months = Number(interval);
      const entry: SubscriptionCreate = {
        name: name.trim(),
        billing_cycle: mode === "fixed_days" ? "自定义" : cycleFromMonths(months),
        billing_interval_months: mode === "fixed_days" || [1, 3, 12].includes(months) ? null : months,
        next_renewal_date: nextDate,
        renewal_mode: mode,
        renewal_interval: months,
        renewal_anchor_day: mode === "same_day" ? Number(nextDate.slice(8, 10)) : null,
      };
      return api.createSubscription(transaction.id, entry, idempotencyKey);
    },
    onSuccess: onSaved,
  });
  if (transaction.type !== "支出") return <Info>只有支出记录可以设为周期性付款。</Info>;
  if (transaction.subscription_id != null) return <Info>这笔支出已经关联周期性付款。</Info>;
  return (
    <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
      <p className="text-sm text-neutral-500">用这笔支出作为首次付款，后续到期时再确认入账。</p>
      <FormField label="描述"><Input value={name} onChange={(event) => setName(event.target.value)} /></FormField>
      <FormField label="下次付款日"><Input type="date" value={nextDate} onChange={(event) => setNextDate(event.target.value)} /></FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="续费方式"><select className={selectClass} value={mode} onChange={(event) => { const value = event.target.value as "same_day" | "fixed_days"; setMode(value); setInterval(value === "same_day" ? "1" : "30"); }}><option value="same_day">按月同日</option><option value="fixed_days">固定天数</option></select></FormField>
        <FormField label={mode === "same_day" ? "间隔月数" : "间隔天数"}><Input type="number" min="1" max={mode === "same_day" ? "120" : "730"} value={interval} onChange={(event) => setInterval(event.target.value)} /></FormField>
      </div>
      {create.isError && <p className="text-sm text-red-600">{create.error.message}</p>}
      <Button className="w-full" disabled={create.isPending || !name.trim() || Number(interval) < 1}>{create.isPending ? "创建中…" : "创建周期性付款"}</Button>
    </form>
  );
}

function Info({ children }: { children: ReactNode }) { return <div className="rounded-lg bg-neutral-100 p-4 text-sm text-neutral-600">{children}</div>; }

function FilterSelect({ label, value, options, onChange }: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1 text-sm font-medium">
      <span>{label}</span>
      <select className={selectClass} value={value} onChange={(event) => onChange(event.target.value)}>
        <option>全部</option>
        {options.map((option) => <option key={option}>{option}</option>)}
      </select>
    </label>
  );
}

function FormField({ label, error, children }: { label: string; error?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5 text-sm font-medium">
      <span>{label}</span>
      {children}
      {error && <span className="block text-xs text-red-600">{error}</span>}
    </label>
  );
}

function TableMessage({ columns, danger, children }: { columns: number; danger?: boolean; children: ReactNode }) {
  return (
    <tr><td colSpan={columns} className={cn("px-4 py-12 text-center text-neutral-500", danger && "text-red-600")}>{children}</td></tr>
  );
}

function unique(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort();
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value);
}

function formatDate(value: Date): string {
  return new Intl.DateTimeFormat("en-CA").format(value);
}

function cycleFromMonths(months: number): "月付" | "季付" | "年付" | "自定义" {
  if (months === 1) return "月付";
  if (months === 3) return "季付";
  if (months === 12) return "年付";
  return "自定义";
}

function csvCell(value: unknown): string {
  const text = String(value ?? "");
  return `"${text.replaceAll('"', '""')}"`;
}

const selectClass = "h-9 w-full rounded-md border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-neutral-500 focus:ring-2 focus:ring-neutral-200";
