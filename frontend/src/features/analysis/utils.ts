import { type ExpenseAnalysis } from "@/api/client";

export type Granularity = "month" | "year";

export type Basis = "cash" | "amortized";

export type BreakdownLevel = "category" | "subcategory";

export type PeriodData = NonNullable<ExpenseAnalysis["current"]>;

export type BreakdownRow = PeriodData["expense_breakdown"][number];

export type DetailSelection = {
  row: BreakdownRow;
  bucket: "expense" | "income";
  level: BreakdownLevel;
};

export function money(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
  }).format(value);
}

export function categoryLabel(row: BreakdownRow) {
  return row.subcategory
    ? `${row.category || "未分类"} / ${row.subcategory}`
    : row.category || "未分类";
}

export function aggregateBreakdown(rows: BreakdownRow[], level: BreakdownLevel): BreakdownRow[] {
  if (level === "subcategory") return rows;
  const totals = new Map<string, BreakdownRow>();
  for (const row of rows) {
    const key = row.category || "";
    const current = totals.get(key) ?? {
      category: row.category,
      subcategory: null,
      total: 0,
      count: 0,
    };
    current.total += row.total;
    current.count += row.count;
    totals.set(key, current);
  }
  return [...totals.values()].sort((a, b) => b.total - a.total);
}
