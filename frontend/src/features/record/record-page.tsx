import "@/features/record/record-page.css";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, NotebookPen, Utensils, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { BatchEntry } from "@/features/record/batch-entry";
import { MealEntry } from "@/features/record/meal-entry";
import { TransactionEntry } from "@/features/record/transaction-entry";
import { cn } from "@/lib/utils";

type Tab = "transaction" | "meal";
const tabs = [
  { value: "transaction", label: "开销与收支", icon: Wallet },
  { value: "meal", label: "饮食", icon: Utensils },
] as const;

export function RecordPage() {
  const [tab, setTab] = useState<Tab>("transaction");

  return (
    <section
      className="page-stack record-page"
      onKeyDown={(event) => {
        if (
          event.defaultPrevented ||
          !event.ctrlKey ||
          event.key !== "Enter" ||
          event.repeat ||
          event.nativeEvent.isComposing
        )
          return;
        event.preventDefault();
        event.currentTarget
          .querySelector<HTMLButtonElement>(
            `#record-${(event.target as HTMLElement).closest(".manual-entry") ? tab : "batch"} button[data-primary-action="true"]:not(:disabled)`,
          )
          ?.click();
      }}
    >
      <header className="record-heading">
        <h1 className="page-title">记录日常</h1>
        <div className="record-emblem" aria-hidden="true">
          <NotebookPen size={22} strokeWidth={1.5} />
        </div>
      </header>
      <div id="record-batch">
        <BatchEntry />
      </div>
      <details className="manual-entry">
        <summary>手动记一笔</summary>
        <div aria-label="手动录入方式" className="page-tabs record-tabs">
          {tabs.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              aria-pressed={tab === value}
              aria-controls={`record-${value}`}
              className={cn("page-tab", tab === value && "page-tab-selected")}
              onClick={() => setTab(value)}
            >
              <Icon size={16} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
        <div id="record-transaction" hidden={tab !== "transaction"}>
          <TransactionEntry />
        </div>
        <div id="record-meal" hidden={tab !== "meal"}>
          <MealEntry />
        </div>
      </details>
      <HomeSummary />
    </section>
  );
}

function HomeSummary() {
  const summary = useQuery({
    queryKey: ["capture", "home"],
    queryFn: api.homeSummary,
    refetchInterval: 5000,
  });
  if (!summary.data) return null;
  const {
    reminders,
    pending_count: pendingCount,
    today_expense: expense,
    today_meals: meals,
  } = summary.data;
  if (!reminders.length && !pendingCount && !expense && !meals.length) return null;
  return (
    <div
      className={`home-summary ${reminders.length > 0 || pendingCount > 0 ? "summary-with-reminders" : ""}`}
    >
      {(reminders.length > 0 || pendingCount > 0) && (
        <div className="reminder-panel">
          <h2 className="reminder-title">待办提醒</h2>
          <ul className="reminder-list">
            {reminders.slice(0, 4).map((item) => (
              <li key={`${item.source}-${item.id}`}>
                • {item.description} · {dueLabel(item.days_until_due)}
                {item.amount ? ` · ${money(item.amount)}` : ""}
              </li>
            ))}
            {reminders.length > 4 && <li>• 另有 {reminders.length - 4} 项付款提醒</li>}
            {pendingCount > 0 && <li>• 待处理记录 · {pendingCount} 项</li>}
          </ul>
          <div className="reminder-links">
            {reminders.length > 0 && (
              <Link className="reminder-link" to="/cross-period">
                处理跨期费用
                <ArrowRight size={14} />
              </Link>
            )}
            {pendingCount > 0 && (
              <Link className="reminder-link" to="/pending">
                查看待处理
                <ArrowRight size={14} />
              </Link>
            )}
          </div>
        </div>
      )}
      <div className="metric-panel">
        <h2 className="content-label">今日概览</h2>
        <p className="today-expense">支出 {expense ? money(expense) : "¥0.00"}</p>
        <div className="today-meals">
          {meals.length ? (
            meals.map((meal) => (
              <p key={meal.id}>
                <span className="today-meal-time">
                  {meal.time || "--:--"}
                  {meal.meal_type ? ` · ${meal.meal_type}` : ""}
                </span>{" "}
                {meal.foods.join("、") || meal.description}
              </p>
            ))
          ) : (
            <p>今日暂无饮食记录</p>
          )}
        </div>
      </div>
    </div>
  );
}

function dueLabel(days: number): string {
  return days < 0 ? `逾期 ${-days} 天` : days === 0 ? "今天" : `${days} 天后`;
}
function money(value: number): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
  }).format(value);
}
