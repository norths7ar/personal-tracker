import { Checkbox, TextArea } from "@radix-ui/themes";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, settingsApi, type ConfirmExpected, type ExpectedWrite } from "@/api/client";
import { invalidateFinance } from "@/api/invalidate";
import { Button } from "@/components/ui/button";
import { DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Feedback, Field, selectClass, textareaClass, today } from "@/features/record/entry-shared";
import { CoverageDurationFields } from "../coverage-duration-fields";
import { categoryValues, coverageDurationLabel, type ExpectedAction } from "./utils";
import { CategoryFields } from "./fields";

export function ExpectedForm({ action, onDone }: { action: ExpectedAction; onDone: () => void }) {
  const queryClient = useQueryClient();
  const categories = useQuery({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
    select: (settings) => settings.records.categories,
  });
  const record = action.mode === "create" ? null : action.record;
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [form, setForm] = useState({
    description: record?.description ?? "",
    amount: record?.amount.toString() ?? "",
    recurring: record?.source === "subscription",
    hasDate: record?.next_date != null || record?.source === "subscription",
    dueDate: record?.next_date ?? today(),
    category: record?.category ?? "",
    subcategory: record?.subcategory ?? "",
    notes: record?.notes ?? "",
    renewalMode: record?.renewal_mode ?? "same_day",
    renewalInterval: record?.renewal_interval?.toString() ?? "1",
    coverageUnit: record?.coverage_unit ?? ("" as const),
    coverageInterval: record?.coverage_interval?.toString() ?? "1",
  });
  const mutation = useMutation({
    mutationFn: async () => {
      const [category, subcategory] = categoryValues(
        categories.data?.支出 ?? {},
        form.category,
        form.subcategory,
        action.mode !== "create",
      );
      if (action.mode === "confirm") {
        const payload: ConfirmExpected = {
          description: form.description.trim(),
          amount: Number(form.amount),
          payment_date: form.dueDate,
          category,
          subcategory,
          notes: form.notes.trim() || null,
        };
        return api.confirmExpected(action.record, payload, idempotencyKey);
      }
      const payload: ExpectedWrite = {
        description: form.description.trim(),
        amount: Number(form.amount),
        recurring: form.recurring,
        due_date: form.recurring || form.hasDate ? form.dueDate : null,
        category,
        subcategory,
        notes: form.notes.trim() || null,
        renewal_mode: form.renewalMode,
        renewal_interval: Number(form.renewalInterval),
        coverage_unit: form.recurring ? form.coverageUnit || null : null,
        coverage_interval:
          form.recurring && form.coverageUnit ? Number(form.coverageInterval) : null,
      };
      return action.mode === "create"
        ? api.createExpected(payload, idempotencyKey)
        : api.updateExpected(action.record, payload);
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
  const isConfirm = action.mode === "confirm";
  const coverageLabel = record ? coverageDurationLabel(record) : "";
  return (
    <form className="form-stack" onSubmit={submit}>
      <DialogHeader>
        <DialogTitle>
          {isConfirm ? "确认入账" : action.mode === "create" ? "新增付款计划" : "编辑付款计划"}
        </DialogTitle>
        <DialogDescription>
          {isConfirm ? "本次付款只会在确认后写入账目。" : "一次性计划和周期付款共用一张清单。"}
        </DialogDescription>
      </DialogHeader>
      <Field label="描述">
        <Input
          value={form.description}
          required
          onChange={(event) => setForm({ ...form, description: event.target.value })}
        />
      </Field>
      <Field label={isConfirm ? "实际金额" : "预计金额"}>
        <Input
          type="number"
          min="0.01"
          step="0.01"
          value={form.amount}
          required
          onChange={(event) => setForm({ ...form, amount: event.target.value })}
        />
      </Field>
      {!isConfirm && action.mode === "create" && (
        <label className="plan-checkbox">
          <Checkbox
            checked={form.recurring}
            onCheckedChange={(checked) =>
              setForm({
                ...form,
                recurring: Boolean(checked),
                hasDate: Boolean(checked) || form.hasDate,
              })
            }
          />
          周期性付款
        </label>
      )}
      {!isConfirm && !form.recurring && (
        <label className="plan-checkbox">
          <Checkbox
            checked={form.hasDate}
            onCheckedChange={(checked) => setForm({ ...form, hasDate: Boolean(checked) })}
          />
          设置预计日期
        </label>
      )}
      {(isConfirm || form.recurring || form.hasDate) && (
        <Field label={isConfirm ? "实际付款日期" : "计划付款日"}>
          <Input
            type="date"
            value={form.dueDate}
            required
            onChange={(event) => setForm({ ...form, dueDate: event.target.value })}
          />
        </Field>
      )}
      {isConfirm && record?.next_date && coverageLabel && (
        <p className="muted-text">
          这笔支出的生效期从计划付款日 {record.next_date} 起算，共 {coverageLabel}
          。实际付款日期用于流水和计算下次续费日期。
        </p>
      )}
      {!isConfirm && form.recurring && (
        <div className="paired-fields">
          <Field label="续费方式">
            <select
              className={selectClass}
              value={form.renewalMode}
              onChange={(event) =>
                setForm({
                  ...form,
                  renewalMode: event.target.value as "same_day" | "fixed_days",
                })
              }
            >
              <option value="same_day">按月同日</option>
              <option value="fixed_days">固定天数</option>
            </select>
          </Field>
          <Field label={form.renewalMode === "same_day" ? "间隔月数" : "间隔天数"}>
            <Input
              type="number"
              min="1"
              required
              max={form.renewalMode === "same_day" ? "120" : "730"}
              value={form.renewalInterval}
              onChange={(event) => setForm({ ...form, renewalInterval: event.target.value })}
            />
          </Field>
        </div>
      )}
      {!isConfirm && form.recurring && (
        <CoverageDurationFields
          unit={form.coverageUnit}
          interval={form.coverageInterval}
          onChange={(coverageUnit, coverageInterval) =>
            setForm({ ...form, coverageUnit, coverageInterval })
          }
        />
      )}
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
        disabled={mutation.isPending || !form.description.trim() || Number(form.amount) <= 0}
      >
        {mutation.isPending ? "提交中…" : isConfirm ? "确认并记账" : "保存"}
      </Button>
      <Feedback error={mutation.error} />
    </form>
  );
}
