import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type RefundCreate, type SubscriptionCreate, type Transaction } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CoverageDurationFields, type CoverageUnit } from "./coverage-duration-fields";
import { FormField, Info } from "./fields";
import { formatDate, formatMoney, selectClass } from "./utils";

export function RefundForm({
  transaction,
  transactions,
  onSaved,
}: {
  transaction: Transaction;
  transactions: Transaction[];
  onSaved: () => void;
}) {
  const refunded = transactions
    .filter((item) => item.refund_for_id === transaction.id)
    .reduce((sum, item) => sum + item.amount, 0);
  const remaining = Math.max(0, transaction.amount - refunded);
  const [entry, setEntry] = useState<RefundCreate>(() => ({
    description: `${transaction.description} 退款`,
    amount: remaining,
    date: formatDate(new Date()),
  }));
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useMutation({
    mutationFn: () => api.createRefund(transaction.id, entry, idempotencyKey),
    onSuccess: onSaved,
  });
  if (transaction.type !== "支出") return <Info>只有支出记录可以关联退款。</Info>;
  return (
    <form
      className="form-stack"
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate();
      }}
    >
      <p className="muted-text">
        已关联退款 {formatMoney(refunded)}，剩余可退 {formatMoney(remaining)}。
      </p>
      <FormField label="退款描述">
        <Input
          value={entry.description}
          onChange={(event) => setEntry({ ...entry, description: event.target.value })}
        />
      </FormField>
      <div className="paired-fields">
        <FormField label="退款金额">
          <Input
            type="number"
            min="0.01"
            max={remaining}
            step="0.01"
            value={entry.amount}
            onChange={(event) => setEntry({ ...entry, amount: Number(event.target.value) })}
          />
        </FormField>
        <FormField label="退款日期">
          <Input
            type="date"
            value={entry.date}
            onChange={(event) => setEntry({ ...entry, date: event.target.value })}
          />
        </FormField>
      </div>
      {create.isError && <p className="error-text">{create.error.message}</p>}
      <div className="transaction-action-footer">
        <Button
          disabled={
            create.isPending ||
            entry.amount <= 0 ||
            entry.amount > remaining ||
            !entry.description.trim()
          }
        >
          {create.isPending ? "保存中…" : "保存退款"}
        </Button>
      </div>
    </form>
  );
}

export function RecurringForm({
  transaction,
  onSaved,
}: {
  transaction: Transaction;
  onSaved: () => void;
}) {
  const [name, setName] = useState(transaction.description);
  const [nextDate, setNextDate] = useState(() => formatDate(new Date()));
  const [mode, setMode] = useState<"same_day" | "fixed_days">("same_day");
  const [interval, setInterval] = useState("1");
  const [coverageUnit, setCoverageUnit] = useState<CoverageUnit | "">("");
  const [coverageInterval, setCoverageInterval] = useState("1");
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useMutation({
    mutationFn: () => {
      const entry: SubscriptionCreate = {
        name: name.trim(),
        next_renewal_date: nextDate,
        renewal_mode: mode,
        renewal_interval: Number(interval),
        renewal_anchor_day: mode === "same_day" ? Number(nextDate.slice(8, 10)) : null,
        coverage_unit: coverageUnit || null,
        coverage_interval: coverageUnit ? Number(coverageInterval) : null,
      };
      return api.createSubscription(transaction.id, entry, idempotencyKey);
    },
    onSuccess: onSaved,
  });
  if (transaction.type !== "支出") return <Info>只有支出记录可以设为周期性付款。</Info>;
  if (transaction.subscription_id != null) return <Info>这笔支出已经关联周期性付款。</Info>;
  return (
    <form
      className="form-stack"
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate();
      }}
    >
      <FormField label="描述">
        <Input value={name} onChange={(event) => setName(event.target.value)} />
      </FormField>
      <FormField label="下次付款日">
        <Input
          type="date"
          required
          value={nextDate}
          onChange={(event) => setNextDate(event.target.value)}
        />
      </FormField>
      <div className="paired-fields">
        <FormField label="续费方式">
          <select
            className={selectClass}
            value={mode}
            onChange={(event) => {
              const value = event.target.value as "same_day" | "fixed_days";
              setMode(value);
              setInterval(value === "same_day" ? "1" : "30");
            }}
          >
            <option value="same_day">按月同日</option>
            <option value="fixed_days">固定天数</option>
          </select>
        </FormField>
        <FormField label={mode === "same_day" ? "间隔月数" : "间隔天数"}>
          <Input
            type="number"
            min="1"
            max={mode === "same_day" ? "120" : "730"}
            value={interval}
            onChange={(event) => setInterval(event.target.value)}
          />
        </FormField>
      </div>
      <CoverageDurationFields
        unit={coverageUnit}
        interval={coverageInterval}
        onChange={(unit, duration) => {
          setCoverageUnit(unit);
          setCoverageInterval(duration);
        }}
      />
      {create.isError && <p className="error-text">{create.error.message}</p>}
      <div className="transaction-action-footer">
        <Button disabled={create.isPending || !name.trim() || Number(interval) < 1}>
          {create.isPending ? "创建中…" : "创建周期性付款"}
        </Button>
      </div>
    </form>
  );
}
