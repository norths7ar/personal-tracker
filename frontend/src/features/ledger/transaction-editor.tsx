import { zodResolver } from "@hookform/resolvers/zod";
import { TextArea } from "@radix-ui/themes";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api, type Transaction } from "@/api/client";
import { EditorFooter } from "@/components/record-actions";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { selectClass, transactionTypes, unique } from "./utils";
import { FormField } from "./fields";
import { AmortizationForm, RecurringForm, RefundForm } from "./transaction-actions";

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
  const [tab, setTab] = useState<"edit" | "amortization" | "recurring" | "refund">("edit");
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
      <DialogContent layout="center">
        <DialogHeader>
          <DialogTitle>编辑账目</DialogTitle>
          <DialogDescription>修改收支信息，保存后生效。</DialogDescription>
        </DialogHeader>
        {transaction && (
          <>
            <div className="editor-tabs">
              {(
                [
                  ["edit", "编辑"],
                  ["amortization", "摊销"],
                  ["recurring", "周期"],
                  ["refund", "退款"],
                ] as const
              ).map(([value, label]) => (
                <button
                  type="button"
                  key={value}
                  className={cn("editor-tab", tab === value && "segmented-selected")}
                  onClick={() => setTab(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "edit" && (
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
                    <Input
                      type="date"
                      {...form.register("date")}
                      value={form.watch("date") ?? ""}
                    />
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
            )}
            {tab === "amortization" && (
              <AmortizationForm transaction={transaction} onSaved={onSaved} />
            )}
            {tab === "recurring" && <RecurringForm transaction={transaction} onSaved={onRefresh} />}
            {tab === "refund" && (
              <RefundForm
                transaction={transaction}
                transactions={transactions}
                onSaved={onRefresh}
              />
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
