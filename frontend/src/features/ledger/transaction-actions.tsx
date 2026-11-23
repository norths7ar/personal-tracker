import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, type RefundCreate, type SubscriptionCreate, type Transaction } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField, Info } from "./fields";
import { formatDate, formatMoney, selectClass } from "./utils";

export function AmortizationForm({
  transaction,
  onSaved,
}: {
  transaction: Transaction;
  onSaved: (record: Transaction) => void;
}) {
  const [months, setMonths] = useState(String(transaction.amortization_months ?? 12));
  const [startMonth, setStartMonth] = useState(
    (transaction.amortization_start ?? transaction.date).slice(0, 7),
  );
  const update = useMutation({
    mutationFn: () =>
      api.updateTransaction(transaction.id, {
        amortization_months: Number(months),
        amortization_start: `${startMonth}-01`,
      }),
    onSuccess: onSaved,
  });
  if (transaction.type !== "支出") return <Info>只有支出记录可以设置摊销。</Info>;
  return (
    <form
      className="form-stack"
      onSubmit={(event) => {
        event.preventDefault();
        update.mutate();
      }}
    >
      <p className="muted-text">把这笔已发生的支出分摊到多个自然月。</p>
      <FormField label="摊销月数">
        <Input
          type="number"
          min="2"
          max="120"
          value={months}
          onChange={(event) => setMonths(event.target.value)}
        />
      </FormField>
      <FormField label="摊销开始月份">
        <Input
          type="month"
          value={startMonth}
          onChange={(event) => setStartMonth(event.target.value)}
        />
      </FormField>
      {update.isError && <p className="error-text">{update.error.message}</p>}
      <Button className="form-submit" disabled={update.isPending || Number(months) < 2}>
        {update.isPending ? "保存中…" : "保存摊销"}
      </Button>
    </form>
  );
}

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
      <Button
        className="form-submit"
        disabled={
          create.isPending ||
          entry.amount <= 0 ||
          entry.amount > remaining ||
          !entry.description.trim()
        }
      >
        {create.isPending ? "保存中…" : "保存退款"}
      </Button>
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
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const create = useMutation({
    mutationFn: () => {
      const months = Number(interval);
      const entry: SubscriptionCreate = {
        name: name.trim(),
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
    <form
      className="form-stack"
      onSubmit={(event) => {
        event.preventDefault();
        create.mutate();
      }}
    >
      <p className="muted-text">用这笔支出作为首次付款，后续到期时再确认入账。</p>
      <FormField label="描述">
        <Input value={name} onChange={(event) => setName(event.target.value)} />
      </FormField>
      <FormField label="下次付款日">
        <Input type="date" value={nextDate} onChange={(event) => setNextDate(event.target.value)} />
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
      {create.isError && <p className="error-text">{create.error.message}</p>}
      <Button
        className="form-submit"
        disabled={create.isPending || !name.trim() || Number(interval) < 1}
      >
        {create.isPending ? "创建中…" : "创建周期性付款"}
      </Button>
    </form>
  );
}
