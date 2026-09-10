import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api, type Transaction, type TransactionUpdate } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Feedback,
  Field,
  selectClass,
  textareaClass,
} from "@/pages/record/entry-shared";

const pendingCategory = "待分类";

export function PendingPage() {
  const queryClient = useQueryClient();
  const pending = useQuery({
    queryKey: ["pending-transactions"],
    queryFn: api.pendingTransactions,
  });
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: api.categories,
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [checkedIds, setCheckedIds] = useState<number[]>([]);
  const [bulkCategory, setBulkCategory] = useState("");
  const [bulkSubcategory, setBulkSubcategory] = useState("");
  const [message, setMessage] = useState("");
  const bulkSubcategories = categories.data?.支出?.[bulkCategory] ?? [];
  const refresh = () => Promise.all(
    ["transactions", "pending-transactions", "home-summary", "expense-analysis", "cross-period"].map((key) =>
      queryClient.invalidateQueries({ queryKey: [key] })),
  );
  const bulkUpdate = useMutation({
    mutationFn: () => api.updateTransactions(checkedIds, { category: bulkCategory, subcategory: bulkSubcategory || null }),
    onSuccess: async (result) => {
      setMessage(`已确认 ${result.updated_count} 笔支出的分类。`);
      setCheckedIds([]);
      setSelectedId(null);
      await refresh();
    },
    onError: () => { void refresh(); },
  });
  const effectiveSelectedId = selectedId ?? pending.data?.[0]?.id ?? null;
  const selected =
    pending.data?.find((row) => row.id === effectiveSelectedId) ?? null;

  const update = useMutation({
    mutationFn: ({ id, changes }: { id: number; changes: TransactionUpdate }) =>
      api.updateTransaction(id, changes),
    onSuccess: (updated) => {
      queryClient.setQueryData<Transaction[]>(
        ["transactions"],
        (current = []) =>
          current.map((row) => (row.id === updated.id ? updated : row)),
      );
      queryClient.setQueryData<Transaction[]>(
        ["pending-transactions"],
        (current = []) =>
          isPending(updated)
            ? current.map((row) => (row.id === updated.id ? updated : row))
            : current.filter((row) => row.id !== updated.id),
      );
      setSelectedId(null);
      setCheckedIds((ids) => ids.filter((id) => id !== updated.id));
      setMessage("分类已保存。");
      void refresh();
    },
  });

  return (
    <section className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">待处理</h1>
        <p className="mt-1 text-sm text-neutral-500">
          处理待分类、缺失分类或低置信度支出。
        </p>
      </header>
      <Feedback message={message} error={bulkUpdate.error} />
      {Boolean(checkedIds.length) && (
        <form className="space-y-3 rounded-lg border border-neutral-200 bg-white p-4" onSubmit={(event) => {
          event.preventDefault();
          if (!bulkUpdate.isPending && !update.isPending) bulkUpdate.mutate();
        }}>
          <p className="text-sm font-medium">已选择 {checkedIds.length} 笔，统一确认分类为：</p>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="批量主类别">
              <select required disabled={bulkUpdate.isPending} className={selectClass} value={bulkCategory} onChange={(event) => { setBulkCategory(event.target.value); setBulkSubcategory(""); }}>
                <option value="">请选择</option>
                {Object.keys(categories.data?.支出 ?? {}).map((category) => <option key={category}>{category}</option>)}
              </select>
            </Field>
            {bulkSubcategories.length > 0 && <Field label="批量子类别">
              <select required disabled={bulkUpdate.isPending} className={selectClass} value={bulkSubcategory} onChange={(event) => setBulkSubcategory(event.target.value)}>
                <option value="">请选择</option>
                {bulkSubcategories.map((category) => <option key={category}>{category}</option>)}
              </select>
            </Field>}
            <Button disabled={bulkUpdate.isPending || update.isPending || !bulkCategory || (bulkSubcategories.length > 0 && !bulkSubcategory)}>{bulkUpdate.isPending ? "保存中…" : `确认 ${checkedIds.length} 笔分类`}</Button>
            <Button type="button" variant="ghost" disabled={bulkUpdate.isPending} onClick={() => setCheckedIds([])}>取消选择</Button>
          </div>
        </form>
      )}
      {pending.isPending ? (
        <p className="text-sm text-neutral-500">正在读取…</p>
      ) : pending.isError ? (
        <Feedback error={pending.error} />
      ) : !pending.data.length ? (
        <div className="rounded-lg border border-neutral-200 bg-white p-8 text-center text-neutral-500">
          暂无待处理支出。
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(340px,0.75fr)]">
          <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-neutral-50 text-left text-xs text-neutral-500">
                <tr>
                  <th className="p-3"><Checkbox aria-label="选择全部待处理支出" disabled={bulkUpdate.isPending || update.isPending} checked={checkedIds.length === pending.data.length || (checkedIds.length > 0 && "indeterminate")} onCheckedChange={(checked) => setCheckedIds(checked ? pending.data.map((row) => row.id) : [])} /></th>
                  <th className="p-3">日期</th><th className="p-3">描述</th>
                  <th className="p-3">金额</th><th className="p-3">当前分类</th>
                </tr>
              </thead>
              <tbody>
                {pending.data.map((row) => (
                  <tr
                    key={row.id}
                    className={`cursor-pointer border-t border-neutral-100 ${row.id === effectiveSelectedId ? "bg-amber-50" : "hover:bg-neutral-50"}`}
                    onClick={() => setSelectedId(row.id)}
                  >
                    <td className="p-3" onClick={(event) => event.stopPropagation()}><Checkbox aria-label={`选择待处理支出 ${row.id}`} disabled={bulkUpdate.isPending || update.isPending} checked={checkedIds.includes(row.id)} onCheckedChange={(checked) => setCheckedIds((ids) => checked ? [...ids, row.id] : ids.filter((id) => id !== row.id))} /></td>
                    <td className="p-3">{row.date}</td>
                    <td className="p-3"><button type="button" className="text-left underline-offset-4 hover:underline" aria-pressed={row.id === effectiveSelectedId} onClick={() => setSelectedId(row.id)}>{row.description}</button></td>
                    <td className="p-3">¥{row.amount.toFixed(2)}</td>
                    <td className="p-3">{row.category || "未分类"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {selected && (
            <PendingEditor
              key={selected.id}
              transaction={selected}
              categories={categories.data?.支出 ?? {}}
              saving={update.isPending || bulkUpdate.isPending}
              error={update.error}
              onSave={(changes) =>
                update.mutate({ id: selected.id, changes })
              }
            />
          )}
        </div>
      )}
    </section>
  );
}

function PendingEditor({
  transaction,
  categories,
  saving,
  error,
  onSave,
}: {
  transaction: Transaction;
  categories: Record<string, string[]>;
  saving: boolean;
  error: Error | null;
  onSave: (changes: TransactionUpdate) => void;
}) {
  const [form, setForm] = useState({
    description: transaction.description,
    amount: transaction.amount,
    date: transaction.date,
    category: transaction.category || pendingCategory,
    subcategory: transaction.subcategory || pendingCategory,
    notes: transaction.notes || "",
  });
  const subcategories =
    form.category === pendingCategory ? [] : (categories[form.category] ?? []);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const unresolved = form.category === pendingCategory;
    onSave({
      description: form.description.trim(),
      amount: form.amount,
      date: form.date,
      category: form.category,
      subcategory: unresolved ? pendingCategory : form.subcategory || null,
      notes: form.notes.trim() || null,
      reviewed: !unresolved,
    });
  };

  return (
    <form className="space-y-4 rounded-lg border border-neutral-200 bg-white p-5" onSubmit={submit}>
      <div>
        <h2 className="font-semibold">确认分类</h2>
        <p className="text-sm text-neutral-500">#{transaction.id}</p>
      </div>
      <Field label="描述">
        <Input value={form.description} required onChange={(event) => setForm({ ...form, description: event.target.value })} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="金额">
          <Input type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: Number(event.target.value) })} />
        </Field>
        <Field label="日期">
          <Input type="date" value={form.date} onChange={(event) => setForm({ ...form, date: event.target.value })} />
        </Field>
      </div>
      <Field label="主类别">
        <select className={selectClass} value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value, subcategory: "" })}>
          {[...Object.keys(categories), pendingCategory].map((category) => <option key={category}>{category}</option>)}
        </select>
      </Field>
      {form.category === pendingCategory ? (
        <p className="text-xs text-neutral-500">保留后会继续出现在此列表。</p>
      ) : subcategories.length > 0 ? (
        <Field label="子类别">
          <select className={selectClass} value={form.subcategory} onChange={(event) => setForm({ ...form, subcategory: event.target.value })}>
            <option value="">请选择</option>
            {subcategories.map((subcategory) => <option key={subcategory}>{subcategory}</option>)}
          </select>
        </Field>
      ) : null}
      <Field label="备注">
        <textarea className={textareaClass} value={form.notes} onChange={(event) => setForm({ ...form, notes: event.target.value })} />
      </Field>
      <Button disabled={saving || !form.description.trim() || form.amount <= 0 || (subcategories.length > 0 && !form.subcategory)}>
        {saving ? "保存中…" : "保存分类"}
      </Button>
      <Feedback error={error} />
    </form>
  );
}

function isPending(transaction: Transaction): boolean {
  return (
    !transaction.category ||
    transaction.category === pendingCategory ||
    transaction.subcategory === pendingCategory ||
    (!transaction.reviewed && (transaction.confidence ?? 1) < 0.75)
  );
}
