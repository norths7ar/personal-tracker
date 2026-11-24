import { zodResolver } from "@hookform/resolvers/zod";
import { TextArea } from "@radix-ui/themes";
import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, type Transaction } from "@/api/client";
import { EditorFooter } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { CoverageFields } from "./coverage-fields";
import { selectClass, transactionTypes, unique } from "./utils";
import { FormField } from "./fields";
import { RecurringForm, RefundForm } from "./transaction-actions";

const editSchema = z.object({
  type: z.enum(transactionTypes),
  description: z.string().trim().min(1, "请填写描述"),
  amount: z.number().positive("金额须大于 0"),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "日期格式不正确"),
  category: z.string(),
  subcategory: z.string(),
  notes: z.string(),
  coverage_start: z.string(),
  coverage_end: z.string(),
});

type EditValues = z.infer<typeof editSchema>;

export function TransactionEditor({
  transaction,
  transactions,
  categories,
  onClose,
  onSaved,
  onRefresh,
}: {
  transaction: Transaction | null;
  transactions: Transaction[];
  categories: Record<string, Record<string, string[]>>;
  onClose: () => void;
  onSaved: (transaction: Transaction) => void;
  onRefresh: () => void;
}) {
  const form = useForm<EditValues>({ resolver: zodResolver(editSchema) });
  const entryType = form.watch("type");
  const category = form.watch("category");
  const categoryOptions = unique([...Object.keys(categories[entryType] ?? {}), category]);
  const subcategoryOptions = unique([
    ...(categories[entryType]?.[category] ?? []),
    form.watch("subcategory"),
  ]);
  const typeRegistration = form.register("type");
  const categoryRegistration = form.register("category");
  const update = useMutation({
    mutationFn: (values: EditValues) =>
      api.updateTransaction(transaction!.id, {
        ...values,
        category: values.category || null,
        subcategory: values.subcategory || null,
        notes: values.notes || null,
        coverage_start: values.type === "支出" ? values.coverage_start || null : null,
        coverage_end: values.type === "支出" ? values.coverage_end || null : null,
      }),
    onSuccess: onSaved,
  });

  useEffect(() => {
    if (!transaction) return;

    form.reset({
      type: transaction.type,
      description: transaction.description,
      amount: transaction.amount,
      date: transaction.date,
      category: transaction.category ?? "",
      subcategory: transaction.subcategory ?? "",
      notes: transaction.notes ?? "",
      coverage_start: transaction.coverage_start ?? "",
      coverage_end: transaction.coverage_end ?? "",
    });
  }, [form, transaction]);

  return (
    <Dialog open={Boolean(transaction)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent layout="center" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>编辑账目</DialogTitle>
        </DialogHeader>
        {transaction && (
          <>
            <form
              className="form-stack"
              onSubmit={form.handleSubmit((values) => update.mutate(values))}
            >
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
                  {transactionTypes.map((type) => (
                    <option key={type}>{type}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="描述" error={form.formState.errors.description?.message}>
                <Input {...form.register("description")} />
              </FormField>
              <div className="paired-fields">
                <FormField label="金额" error={form.formState.errors.amount?.message}>
                  <Input
                    type="number"
                    min="0.01"
                    step="0.01"
                    {...form.register("amount", { valueAsNumber: true })}
                  />
                </FormField>
                <FormField label="日期" error={form.formState.errors.date?.message}>
                  <Input type="date" {...form.register("date")} value={form.watch("date") ?? ""} />
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
                  {categoryOptions.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="子类别">
                <select className={selectClass} {...form.register("subcategory")}>
                  <option value="">无</option>
                  {subcategoryOptions.map((item) => (
                    <option key={item}>{item}</option>
                  ))}
                </select>
              </FormField>
              <FormField label="备注">
                <TextArea className="form-textarea" {...form.register("notes")} />
              </FormField>
              {entryType === "支出" && (
                <CoverageFields
                  start={form.watch("coverage_start") ?? ""}
                  end={form.watch("coverage_end") ?? ""}
                  paymentDate={form.watch("date") ?? ""}
                  onChange={(start, end) => {
                    form.setValue("coverage_start", start);
                    form.setValue("coverage_end", end);
                  }}
                />
              )}
              {update.isError && <p className="error-text">{update.error.message}</p>}
              <EditorFooter>
                <Button type="button" variant="outline" onClick={onClose}>
                  取消
                </Button>
                <Button type="submit" disabled={update.isPending}>
                  {update.isPending ? "保存中…" : "保存修改"}
                </Button>
              </EditorFooter>
            </form>
            {transaction.type === "支出" && (
              <div className="form-stack transaction-extra-actions">
                <details className="manual-options">
                  <summary>登记退款</summary>
                  <RefundForm
                    transaction={transaction}
                    transactions={transactions}
                    onSaved={onRefresh}
                  />
                </details>
                <details className="manual-options">
                  <summary>设为周期计划</summary>
                  <RecurringForm transaction={transaction} onSaved={onRefresh} />
                </details>
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function LockedField({ label, value }: { label: string; value: string }) {
  return (
    <FormField label={label}>
      <Input className="readonly-input" value={value} disabled readOnly />
    </FormField>
  );
}
