import { settingsApi } from "@/api/client";
import { TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, type PrepaidUpdate, type PrepaidWrite } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Feedback, Field, textareaClass, today } from "@/features/record/entry-shared";
import { categoryValues, type PrepaidAction } from "./utils";
import { CategoryFields } from "./fields";

export function PrepaidForm({ action, onDone }: { action: PrepaidAction; onDone: () => void }) {
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    select: (settings) => settings.records.categories,
  });
  const record = action.mode === "edit" ? action.record : null;
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [form, setForm] = useState({
    description: record?.description ?? "",
    amount: record?.amount.toString() ?? "",
    paymentDate: today(),
    months: record?.months.toString() ?? "12",
    startMonth: record?.start_month ?? today().slice(0, 7),
    category: record?.category ?? "",
    subcategory: record?.subcategory ?? "",
    notes: record?.notes ?? "",
  });
  const mutation = useMutation({
    mutationFn: () => {
      const [category, subcategory] = categoryValues(
        categories.data?.支出 ?? {},
        form.category,
        form.subcategory,
        action.mode !== "create",
      );
      const base: PrepaidUpdate = {
        description: form.description.trim(),
        months: Number(form.months),
        start_month: form.startMonth,
        category,
        subcategory,
        notes: form.notes.trim() || null,
      };
      if (action.mode === "edit") return api.updatePrepaid(action.record.id, base);
      const payload: PrepaidWrite = {
        ...base,
        amount: Number(form.amount),
        payment_date: form.paymentDate,
      };
      return api.createPrepaid(payload, idempotencyKey);
    },
    onSuccess: async () => {
      await invalidateFinance(queryClient);
      onDone();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    mutation.mutate();
  };
  return (
    <form className="form-stack" onSubmit={submit}>
      <DialogHeader>
        <DialogTitle>{action.mode === "create" ? "新增预付摊销" : "编辑预付摊销"}</DialogTitle>
        <DialogDescription>
          {record
            ? `关联流水 #${record.transaction_id}；金额和付款日期请到账目页修改。`
            : "保存时会同时生成付款流水与摊销设置。"}
        </DialogDescription>
      </DialogHeader>
      <Field label="描述">
        <Input
          value={form.description}
          required
          onChange={(event) => setForm({ ...form, description: event.target.value })}
        />
      </Field>
      {action.mode === "create" && (
        <>
          <Field label="总金额">
            <Input
              type="number"
              min="0.01"
              step="0.01"
              value={form.amount}
              required
              onChange={(event) => setForm({ ...form, amount: event.target.value })}
            />
          </Field>
          <Field label="付款日期">
            <Input
              type="date"
              value={form.paymentDate}
              onChange={(event) => setForm({ ...form, paymentDate: event.target.value })}
            />
          </Field>
        </>
      )}
      <div className="paired-fields">
        <Field label="摊销月数">
          <Input
            type="number"
            min="1"
            max="120"
            value={form.months}
            onChange={(event) => setForm({ ...form, months: event.target.value })}
          />
        </Field>
        <Field label="摊销开始月份">
          <Input
            type="month"
            value={form.startMonth}
            onChange={(event) => setForm({ ...form, startMonth: event.target.value })}
          />
        </Field>
      </div>
      <CategoryFields
        categories={categories.data?.支出 ?? {}}
        preserveCurrent={action.mode !== "create"}
        category={form.category}
        subcategory={form.subcategory}
        onChange={(category, subcategory) => setForm({ ...form, category, subcategory })}
      />
      <Field label="备注">
        <TextArea
          className={textareaClass}
          value={form.notes}
          onChange={(event) => setForm({ ...form, notes: event.target.value })}
        />
      </Field>
      <Button
        className="form-submit"
        disabled={
          mutation.isPending ||
          !form.description.trim() ||
          (action.mode === "create" && Number(form.amount) <= 0)
        }
      >
        {mutation.isPending ? "提交中…" : action.mode === "create" ? "保存并记账" : "保存修改"}
      </Button>
      <Feedback error={mutation.error} />
    </form>
  );
}
