import "@/features/record/record-page.css";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Layers3, NotebookPen, Utensils, Wallet } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { BatchEntry } from "@/features/record/batch-entry";
import { MealEntry } from "@/features/record/meal-entry";
import { TransactionEntry } from "@/features/record/transaction-entry";
import { cn } from "@/lib/utils";

type Tab = "batch" | "transaction" | "meal";
const tabs = [
  { value: "batch", label: "批量录入", icon: Layers3 },
  { value: "transaction", label: "开销与收支", icon: Wallet },
  { value: "meal", label: "饮食", icon: Utensils },
] as const;

export function RecordPage() {
  const [tab, setTab] = useState<Tab>("batch");

  return (
    <section
      className="page-stack record-page"
      onKeyDown={(event) => {
        if (
          !event.ctrlKey ||
          event.key !== "Enter" ||
          event.repeat ||
          event.nativeEvent.isComposing
        )
          return;
        event.preventDefault();
        event.currentTarget
          .querySelector<HTMLButtonElement>(
            `#record-${tab} button[data-primary-action="true"]:not(:disabled)`,
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
      <div aria-label="录入方式" className="page-tabs record-tabs">
        {tabs.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            aria-pressed={tab === value}
            aria-controls={`record-${value}`}
            className={cn("page-tab", tab === value && "page-tab-selected")}
            onClick={() => setTab(value)}
          >
            <Icon size={18} strokeWidth={1.7} aria-hidden="true" />
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
      <HomeSummary />
    </section>
  );
}

function HomeSummary() {
  const summary = useQuery({
    queryKey: ["capture", "home"],
    queryFn: api.homeSummary,
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
            {pendingCount > 0 && <li>• 待分类支出 · {pendingCount} 笔</li>}
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
                处理待分类
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
                {meal.foods.join("、")}
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
