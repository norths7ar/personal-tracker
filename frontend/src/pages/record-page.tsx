import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "@/api/client";
import { cn } from "@/lib/utils";
import { BatchEntry } from "@/pages/record/batch-entry";
import { MealEntry } from "@/pages/record/meal-entry";
import { TransactionEntry } from "@/pages/record/transaction-entry";

type Tab = "batch" | "transaction" | "meal";
const tabs: Array<{ value: Tab; label: string }> = [
  { value: "batch", label: "批量录入" },
  { value: "transaction", label: "开销与收支" },
  { value: "meal", label: "饮食" },
];

export function RecordPage() {
  const [tab, setTab] = useState<Tab>("batch");

  return (
    <section className="space-y-5" onKeyDown={(event) => {
      if (!event.ctrlKey || event.key !== "Enter" || event.repeat || event.nativeEvent.isComposing) return;
      event.preventDefault();
      event.currentTarget.querySelector<HTMLButtonElement>(`#record-${tab} button[data-primary-action="true"]:not(:disabled)`)?.click();
    }}>
      <header>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">记录</h1>
        <p className="mt-1 text-sm text-neutral-500">
          Ctrl+Enter 执行当前步骤；有待确认内容时请检查后保存。
        </p>
      </header>
      <HomeSummary />
      <div aria-label="录入方式" className="flex gap-1 rounded-lg bg-neutral-200/70 p-1">
        {tabs.map(({ value, label }) => (
          <button
            key={value}
            aria-pressed={tab === value}
            aria-controls={`record-${value}`}
            className={cn(
              "flex-1 rounded-md px-3 py-2 text-sm font-medium",
              tab === value && "bg-white shadow-sm",
            )}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div id="record-batch" hidden={tab !== "batch"}>
        <BatchEntry />
      </div>
      <div id="record-transaction" hidden={tab !== "transaction"}>
        <TransactionEntry />
      </div>
      <div id="record-meal" hidden={tab !== "meal"}>
        <MealEntry />
      </div>
    </section>
  );
}

function HomeSummary() {
  const summary = useQuery({ queryKey: ["home-summary"], queryFn: api.homeSummary });
  if (!summary.data) return null;
  const { reminders, pending_count: pendingCount, today_expense: expense, today_meals: meals } = summary.data;
  if (!reminders.length && !pendingCount && !expense && !meals.length) return null;
  return (
    <div className={`grid gap-3 ${reminders.length > 0 || pendingCount > 0 ? "lg:grid-cols-2" : ""}`}>
      {(reminders.length > 0 || pendingCount > 0) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <h2 className="font-medium text-amber-950">待办提醒</h2>
          <ul className="mt-2 space-y-1 text-sm text-amber-900">
            {reminders.slice(0, 4).map((item) => <li key={`${item.source}-${item.id}`}>• {item.description} · {dueLabel(item.days_until_due)}{item.amount ? ` · ${money(item.amount)}` : ""}</li>)}
            {reminders.length > 4 && <li>• 另有 {reminders.length - 4} 项付款提醒</li>}
            {pendingCount > 0 && <li>• 待分类支出 · {pendingCount} 笔</li>}
          </ul>
          <div className="mt-3 flex flex-wrap gap-3 text-sm font-medium">
            {reminders.length > 0 && <Link className="inline-flex items-center gap-1" to="/cross-period">处理跨期费用<ArrowRight size={14} /></Link>}
            {pendingCount > 0 && <Link className="inline-flex items-center gap-1" to="/pending">处理待分类<ArrowRight size={14} /></Link>}
          </div>
        </div>
      )}
      <div className="rounded-lg border border-neutral-200 bg-white p-4">
        <h2 className="font-medium">今日概览</h2>
        <p className="mt-2 text-sm text-neutral-600">支出 {expense ? money(expense) : "¥0.00"}</p>
        <div className="mt-2 space-y-1 text-sm text-neutral-600">
          {meals.length ? meals.map((meal) => <p key={meal.id}><span className="font-medium text-neutral-800">{meal.time || "--:--"}{meal.meal_type ? ` · ${meal.meal_type}` : ""}</span> {meal.foods.join("、")}</p>) : <p>今日暂无饮食记录</p>}
        </div>
      </div>
    </div>
  );
}

function dueLabel(days: number): string { return days < 0 ? `逾期 ${-days} 天` : days === 0 ? "今天" : `${days} 天后`; }
function money(value: number): string { return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value); }
