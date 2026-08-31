import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo, useState, type FormEvent } from "react";

import {
  api,
  type ExpenseAnalysis,
  type MonthBudgetUpdate,
} from "@/api/client";
import { Button } from "@/components/ui/button";
import { EChart } from "@/components/echart";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { Feedback, Field, selectClass } from "@/pages/record/entry-shared";

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

type Granularity = "month" | "year";
type Basis = "cash" | "amortized";
type BreakdownLevel = "category" | "subcategory";

export function AnalysisPage() {
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [basis, setBasis] = useState<Basis>("amortized");
  const [periods, setPeriods] = useState<Partial<Record<Granularity, string>>>({});
  const period = periods[granularity] ?? null;
  const analysis = useQuery({
    queryKey: ["expense-analysis", granularity, period, basis],
    queryFn: () => api.expenseAnalysis(granularity, period, basis),
  });
  const selectedPeriod = analysis.data?.selected_period ?? "";

  return (
    <section className="mx-auto max-w-6xl space-y-5">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">开销分析</h1>
        <p className="mt-1 text-sm text-neutral-500">现金流、摊销成本与分类变化。</p>
      </header>
      <div className="flex flex-wrap gap-4 rounded-lg border border-neutral-200 bg-white p-4">
        <Segmented
          value={granularity}
          options={[{ value: "month", label: "月" }, { value: "year", label: "年" }]}
          onChange={(value) => setGranularity(value as Granularity)}
        />
        <Segmented
          value={basis}
          options={[{ value: "amortized", label: "摊销后" }, { value: "cash", label: "现金流" }]}
          onChange={(value) => setBasis(value as Basis)}
        />
        {analysis.data && (
          <Field label={granularity === "month" ? "月份" : "年份"}>
            <select
              className={`${selectClass} min-w-40`}
              value={selectedPeriod}
              onChange={(event) =>
                setPeriods((current) => ({ ...current, [granularity]: event.target.value }))
              }
            >
              {(granularity === "month" ? analysis.data.months : analysis.data.years).map(
                (item) => <option key={item}>{item}</option>,
              )}
            </select>
          </Field>
        )}
      </div>

      {analysis.isPending ? (
        <p className="text-sm text-neutral-500">正在分析…</p>
      ) : analysis.isError ? (
        <Feedback error={analysis.error} />
      ) : !analysis.data.current || !analysis.data.selected_period ? (
        <div className="rounded-lg border bg-white p-8 text-center text-neutral-500">暂无账目数据。</div>
      ) : (
        <AnalysisContent
          data={analysis.data}
          basis={basis}
          granularity={granularity}
        />
      )}
    </section>
  );
}

function AnalysisContent({ data, basis, granularity }: { data: ExpenseAnalysis; basis: Basis; granularity: Granularity }) {
  const current = data.current!;
  const previous = data.previous!;
  const cashCurrent = data.cash_current!;
  const cashPrevious = data.cash_previous!;
  const [level, setLevel] = useState<BreakdownLevel>("category");
  const daily = useMemo(() => fillDaily(data), [data]);
  const breakdown = aggregateBreakdown(current.expense_breakdown, level);
  const incomeBreakdown = aggregateBreakdown(current.income_breakdown, level);
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="现金流支出" value={money(cashCurrent.expense)} delta={cashCurrent.expense - cashPrevious.expense} inverse />
        <Metric label="现金流收入" value={money(cashCurrent.income)} delta={cashCurrent.income - cashPrevious.income} />
        <Metric label="日均现金流支出" value={money(cashCurrent.expense / (data.days || 1))} />
        <Metric label="收支结余" value={money(cashCurrent.balance)} />
      </div>
      {granularity === "month" && (
        <>
          <div className="grid gap-3 lg:grid-cols-3">
            <Metric label="固定支出" value={money(data.fixed_monthly_cost ?? 0)} />
            <BudgetStatus label="摊销后成本上限" actual={data.amortized_expense ?? 0} budget={data.budget?.amortized_total} />
            <BudgetStatus label="现金流上限" actual={data.cash_expense ?? 0} budget={data.budget?.cash_total} />
          </div>
          <BudgetEditor month={data.selected_period!} budget={data.budget ?? { amortized_total: null, cash_total: null }} />
        </>
      )}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
        {trendSummary(current, previous, basis === "cash" ? "现金流" : "摊销后")}
      </div>
      <Chart
        title={granularity === "month" ? "本月每日收支" : "本年各月收支"}
        option={granularity === "month" ? lineOption(daily) : barOption(data.timeline ?? [])}
      />
      {granularity === "month" ? (
        <Chart title="最近 12 个月对比" option={barOption(data.timeline ?? [])} />
      ) : (
        <Chart title="历年对比" option={barOption(data.comparison ?? [])} />
      )}
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">分类明细</h2>
        <Segmented
          value={level}
          options={[{ value: "category", label: "主类别" }, { value: "subcategory", label: "子类别" }]}
          onChange={(value) => setLevel(value as BreakdownLevel)}
        />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Breakdown title="支出" rows={breakdown} chart />
        <Breakdown title="收入" rows={incomeBreakdown} />
      </div>
    </div>
  );
}

function BudgetEditor({ month, budget }: { month: string; budget: MonthBudgetUpdate }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    amortized_total: budget.amortized_total?.toString() ?? "",
    cash_total: budget.cash_total?.toString() ?? "",
  });
  const update = useMutation({
    mutationFn: (payload: MonthBudgetUpdate) => api.updateMonthBudget(month, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["expense-analysis"] });
      setOpen(false);
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    update.mutate({
      amortized_total: optionalAmount(form.amortized_total),
      cash_total: optionalAmount(form.cash_total),
    });
  };
  if (!open) return <Button variant="outline" onClick={() => setOpen(true)}>设置本月预算</Button>;
  return (
    <form className="grid gap-3 rounded-lg border border-neutral-200 bg-white p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end" onSubmit={submit}>
      <Field label="摊销后成本上限"><Input type="number" min="0" step="0.01" value={form.amortized_total} onChange={(event) => setForm({ ...form, amortized_total: event.target.value })} /></Field>
      <Field label="现金流上限"><Input type="number" min="0" step="0.01" value={form.cash_total} onChange={(event) => setForm({ ...form, cash_total: event.target.value })} /></Field>
      <div className="flex gap-2"><Button disabled={update.isPending}>{update.isPending ? "保存中…" : "保存"}</Button><Button type="button" variant="ghost" onClick={() => setOpen(false)}>取消</Button></div>
      {update.error && <div className="sm:col-span-3"><Feedback error={update.error} /></div>}
    </form>
  );
}

type BreakdownRow = {
  category?: string | null;
  subcategory?: string | null;
  total: number;
  count: number;
};

function Breakdown({ title, rows, chart = false }: { title: string; rows: BreakdownRow[]; chart?: boolean }) {
  return (
    <div className="rounded-lg border border-neutral-200 bg-white p-4">
      <h3 className="mb-3 font-medium">{title}</h3>
      {!rows.length ? <p className="text-sm text-neutral-500">本期无{title}记录。</p> : (
        <>
          {chart && <EChart option={breakdownOption(rows.slice(0, 8))} height={Math.max(220, rows.slice(0, 8).length * 38)} />}
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-xs text-neutral-500"><tr><th className="py-2">分类</th><th className="py-2 text-right">金额</th><th className="py-2 text-right">笔数</th></tr></thead><tbody>{rows.map((row) => <tr className="border-t border-neutral-100" key={`${row.category}-${row.subcategory}`}><td className="py-2">{row.subcategory ? `${row.category || "未分类"} / ${row.subcategory}` : row.category || "未分类"}</td><td className="py-2 text-right">{money(row.total)}</td><td className="py-2 text-right">{row.count}</td></tr>)}</tbody></table></div>
        </>
      )}
    </div>
  );
}

function Chart({ title, option }: { title: string; option: object }) { return <div className="rounded-lg border border-neutral-200 bg-white p-4"><h2 className="mb-2 font-medium">{title}</h2><EChart option={option} /></div>; }
function Metric({ label, value, delta, inverse = false }: { label: string; value: string; delta?: number; inverse?: boolean }) { const good = delta === undefined || delta === 0 ? null : inverse ? delta < 0 : delta > 0; return <div className="rounded-lg border border-neutral-200 bg-white p-4"><p className="text-sm text-neutral-500">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p>{delta !== undefined && delta !== 0 && <p className={cn("mt-1 text-xs", good ? "text-emerald-600" : "text-red-600")}>较上期 {delta > 0 ? "+" : ""}{money(delta)}</p>}</div>; }
function BudgetStatus({ label, actual, budget }: { label: string; actual: number; budget?: number | null }) { if (budget == null) return <div className="rounded-lg border bg-white p-4"><p className="text-sm text-neutral-500">{label}</p><p className="mt-2 text-sm">尚未设置</p></div>; const ratio = budget ? actual / budget : 0; return <div className="rounded-lg border bg-white p-4"><p className="text-sm text-neutral-500">{label}</p><p className="mt-1 font-medium">{money(actual)} / {money(budget)}</p><div className="mt-3 h-2 overflow-hidden rounded bg-neutral-100"><div className={cn("h-full", ratio >= 1 ? "bg-red-500" : ratio >= 0.8 ? "bg-amber-500" : "bg-emerald-500")} style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%` }} /></div><p className="mt-2 text-xs text-neutral-500">{ratio >= 1 ? `超出 ${money(actual - budget)}` : `剩余 ${money(budget - actual)}`}</p></div>; }
function Segmented({ value, options, onChange }: { value: string; options: { value: string; label: string }[]; onChange: (value: string) => void }) { return <div className="flex self-end rounded-lg bg-neutral-100 p-1">{options.map((option) => <button className={cn("rounded-md px-3 py-1.5 text-sm", option.value === value && "bg-white font-medium shadow-sm")} key={option.value} onClick={() => onChange(option.value)}>{option.label}</button>)}</div>; }

function money(value: number): string { return new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value); }
function optionalAmount(value: string): number | null { const parsed = Number(value); return value && parsed > 0 ? parsed : null; }
function aggregateBreakdown(rows: BreakdownRow[], level: BreakdownLevel): BreakdownRow[] { if (level === "subcategory") return rows; const totals = new Map<string, BreakdownRow>(); for (const row of rows) { const category = row.category || "未分类"; const current = totals.get(category) ?? { category, subcategory: null, total: 0, count: 0 }; current.total += row.total; current.count += row.count; totals.set(category, current); } return [...totals.values()].sort((a, b) => b.total - a.total); }
function trendSummary(current: NonNullable<ExpenseAnalysis["current"]>, previous: NonNullable<ExpenseAnalysis["previous"]>, label: string): string { const delta = current.expense - previous.expense; if (Math.abs(delta) < 0.005) return `按${label}口径，本期支出与上期基本持平。`; const changes = categoryTotals(current.expense_breakdown); const previousTotals = categoryTotals(previous.expense_breakdown); let largest = ["", 0] as [string, number]; for (const category of new Set([...changes.keys(), ...previousTotals.keys()])) { const change = (changes.get(category) ?? 0) - (previousTotals.get(category) ?? 0); if (Math.abs(change) > Math.abs(largest[1])) largest = [category, change]; } const direction = delta > 0 ? "增加" : "减少"; if (!largest[0]) return `按${label}口径，本期支出较上期${direction} ${money(Math.abs(delta))}。`; return `按${label}口径，本期支出较上期${direction} ${money(Math.abs(delta))}；变化最大的是${largest[0]}，${largest[1] > 0 ? "增加" : "减少"} ${money(Math.abs(largest[1]))}。`; }
function categoryTotals(rows: BreakdownRow[]): Map<string, number> { const result = new Map<string, number>(); for (const row of rows) { const key = row.category || "未分类"; result.set(key, (result.get(key) ?? 0) + row.total); } return result; }
function fillDaily(data: ExpenseAnalysis) { const rows = data.current?.daily ?? []; if (!data.selected_period || data.selected_period.length !== 7 || !data.days) return rows; const byDate = new Map(rows.map((row) => [row.date, row])); return Array.from({ length: data.days }, (_, index) => { const date = `${data.selected_period}-${String(index + 1).padStart(2, "0")}`; return byDate.get(date) ?? { date, income: 0, expense: 0 }; }); }
function lineOption(rows: { date: string; income: number; expense: number }[]) { return { tooltip: { trigger: "axis" }, legend: { data: ["支出", "收入"] }, xAxis: { type: "category", data: rows.map((row) => row.date.slice(5)) }, yAxis: { type: "value" }, series: [{ name: "支出", type: "line", data: rows.map((row) => row.expense), itemStyle: { color: "#dc2626" } }, { name: "收入", type: "line", data: rows.map((row) => row.income), itemStyle: { color: "#059669" } }] }; }
function barOption(rows: { label: string; income: number; expense: number }[]) { return { tooltip: { trigger: "axis" }, legend: { data: ["支出", "收入"] }, xAxis: { type: "category", data: rows.map((row) => row.label) }, yAxis: { type: "value" }, series: [{ name: "支出", type: "bar", data: rows.map((row) => row.expense) }, { name: "收入", type: "bar", data: rows.map((row) => row.income) }] }; }
function breakdownOption(rows: BreakdownRow[]) { const reversed = [...rows].reverse(); return { tooltip: { trigger: "axis" }, grid: { left: 100, right: 28 }, xAxis: { type: "value" }, yAxis: { type: "category", data: reversed.map((row) => row.subcategory ? `${row.category} / ${row.subcategory}` : row.category || "未分类") }, series: [{ type: "bar", data: reversed.map((row) => row.total) }] }; }
