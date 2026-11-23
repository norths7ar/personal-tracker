import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, type MonthBudgetUpdate } from "@/api/client";
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
import { Feedback, Field } from "@/features/record/entry-shared";
import { money } from "./utils";

export function BudgetEditor({ month, budget }: { month: string; budget: MonthBudgetUpdate }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        设置预算
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent layout="center">
          <DialogHeader>
            <DialogTitle>{month} 月度预算</DialogTitle>
            <DialogDescription>
              分别设置现金流与摊销后的净支出上限，留空表示不设上限。
            </DialogDescription>
          </DialogHeader>
          {open && <BudgetForm month={month} budget={budget} onClose={() => setOpen(false)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function BudgetForm({
  month,
  budget,
  onClose,
}: {
  month: string;
  budget: MonthBudgetUpdate;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    amortized_total: budget.amortized_total?.toString() ?? "",
    cash_total: budget.cash_total?.toString() ?? "",
  });
  const update = useMutation({
    mutationFn: (payload: MonthBudgetUpdate) => api.updateMonthBudget(month, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ledger", "analysis"] });
      onClose();
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({
      amortized_total: optionalAmount(form.amortized_total),
      cash_total: optionalAmount(form.cash_total),
    });
  };
  return (
    <form className="form-stack" onSubmit={submit}>
      <Field label="现金流净支出上限">
        <Input
          type="number"
          min="0"
          step="0.01"
          value={form.cash_total}
          onChange={(event) => setForm({ ...form, cash_total: event.target.value })}
        />
      </Field>
      <Field label="摊销后净支出上限">
        <Input
          type="number"
          min="0"
          step="0.01"
          value={form.amortized_total}
          onChange={(event) => setForm({ ...form, amortized_total: event.target.value })}
        />
      </Field>
      <Feedback error={update.error} />
      <EditorFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          取消
        </Button>
        <Button disabled={update.isPending}>{update.isPending ? "保存中…" : "保存预算"}</Button>
      </EditorFooter>
    </form>
  );
}

export function BudgetStatus({
  label,
  actual,
  budget,
}: {
  label: string;
  actual: number;
  budget?: number | null;
}) {
  const ratio = budget == null ? 0 : budget === 0 ? (actual > 0 ? 1 : 0) : actual / budget;
  return (
    <div>
      <p className="muted-text">{label}</p>
      <p className="budget-value">
        {money(actual)}
        {budget != null && ` / ${money(budget)}`}
      </p>
      <div className="budget-track">
        <div
          className={cn(
            "budget-fill",
            budget != null && actual > budget ? "budget-exceeded" : "budget-available",
          )}
          style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%` }}
        />
      </div>
      <p className="metric-hint">
        {budget == null
          ? "尚未设置上限"
          : actual > budget
            ? `超出 ${money(actual - budget)}`
            : `剩余 ${money(budget - actual)}`}
      </p>
    </div>
  );
}

function optionalAmount(value: string) {
  return value.trim() === "" ? null : Number(value);
}
