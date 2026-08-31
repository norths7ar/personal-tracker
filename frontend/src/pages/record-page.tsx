import { useState } from "react";

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
    <section className="mx-auto max-w-6xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">记录</h1>
        <p className="mt-1 text-sm text-neutral-500">
          草稿和确认状态留在浏览器；只有解析与保存访问后端。
        </p>
      </header>
      <div className="flex gap-1 rounded-lg bg-neutral-200/70 p-1">
        {tabs.map(({ value, label }) => (
          <button
            key={value}
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
      <div hidden={tab !== "batch"}>
        <BatchEntry />
      </div>
      <div hidden={tab !== "transaction"}>
        <TransactionEntry />
      </div>
      <div hidden={tab !== "meal"}>
        <MealEntry />
      </div>
    </section>
  );
}
