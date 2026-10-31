import "@/styles/analysis-page.css";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo, useState, type FormEvent } from "react";

import { api, type ExpenseAnalysis, type MonthBudgetUpdate } from "@/api/client";
import { EChart } from "@/components/echart";
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
import { cumulativeNetExpense, netExpense } from "@/pages/analysis-calculations";
import { Feedback, Field, selectClass } from "@/pages/record/entry-shared";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer]);
type Granularity = "month" | "year";
type Basis = "cash" | "amortized";
type BreakdownLevel = "category" | "subcategory";
type PeriodData = NonNullable<ExpenseAnalysis["current"]>;
type BreakdownRow = PeriodData["expense_breakdown"][number];
type DetailSelection = {
  row: BreakdownRow;
  bucket: "expense" | "income";
  level: BreakdownLevel;
};

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
    <section className="page-stack">
      <header>
        <h1 className="page-title">开销分析</h1>
        <p className="page-description">查看收支、预算，以及每笔支出的去向。</p>
      </header>
      <div className="analysis-filters">
        <Segmented
          value={granularity}
          options={[
            { value: "month", label: "月" },
            { value: "year", label: "年" },
          ]}
          onChange={(value) => setGranularity(value as Granularity)}
        />
        {analysis.data && (
          <Field label={granularity === "month" ? "月份" : "年份"}>
            <select
              className={`${selectClass} analysis-period-select`}
              value={selectedPeriod}
              onChange={(event) =>
                setPeriods((current) => ({
                  ...current,
                  [granularity]: event.target.value,
                }))
              }
            >
              {(granularity === "month" ? analysis.data.months : analysis.data.years).map(
                (item) => (
                  <option key={item}>{item}</option>
                ),
              )}
            </select>
          </Field>
        )}
        {analysis.data?.end_date && (
          <p className="analysis-period-caption">
            {analysis.data.days
              ? `${analysis.data.start_date} 至 ${analysis.data.end_date} · ${analysis.data.days} 天`
              : "所选期间尚未开始"}
          </p>
        )}
      </div>
      {analysis.isPending ? (
        <p className="muted-text">正在分析…</p>
      ) : analysis.isError ? (
        <Feedback error={analysis.error} />
      ) : !analysis.data.current || !selectedPeriod ? (
        <div className="empty-panel">暂无账目数据。</div>
      ) : (
        <AnalysisContent
          key={`${selectedPeriod}-${basis}`}
          data={analysis.data}
          basis={basis}
          granularity={granularity}
          onBasisChange={setBasis}
        />
      )}
    </section>
  );
}

function AnalysisContent({
  data,
  basis,
  granularity,
  onBasisChange,
}: {
  data: ExpenseAnalysis;
  basis: Basis;
  granularity: Granularity;
  onBasisChange: (basis: Basis) => void;
}) {
  const current = data.current!;
  const cash = data.cash_current!;
  const cashNetExpense = netExpense(cash);
  const [level, setLevel] = useState<BreakdownLevel>("category");
  const [detail, setDetail] = useState<DetailSelection | null>(null);
  const daily = useMemo(() => cumulativeNetExpense(fillDaily(data)), [data]);
  const basisLabel = basis === "cash" ? "现金流" : "摊销后";
  return (
    <div className="analysis-sections">
      <section className="summary-section">
        <div>
          <h2 className="section-title">现金收支</h2>
          <p className="section-description">净支出 = 支出（已扣关联退款）− 收入。</p>
        </div>
        <div className="metrics-grid">
          <Metric label="现金流净支出" value={money(cashNetExpense)} />
          <Metric label="现金流收入" value={money(cash.income)} />
          <Metric
            label="日均现金流净支出"
            value={data.days ? money(cashNetExpense / data.days) : "—"}
            hint={data.days ? `按期间已过 ${data.days} 天计算` : "期间尚未开始"}
          />
          <Metric
            label="收支结余"
            value={money(cash.balance)}
            hint="收入 − 付款口径支出（已扣关联退款）"
          />
        </div>
      </section>
      {granularity === "month" && (
        <section className="content-panel">
          <div className="panel-heading">
            <h2 className="section-title">月度预算</h2>
            <BudgetEditor
              month={data.selected_period!}
              budget={data.budget ?? { amortized_total: null, cash_total: null }}
            />
          </div>
          <div className="budget-grid">
            <div>
              <p className="muted-text">固定费用参考</p>
              <p className="metric-value">{money(data.fixed_monthly_cost ?? 0)}</p>
              <p className="metric-hint">
                周期付款与预付摊销，不含一次性计划；不额外计入下方预算用量。
              </p>
            </div>
            <BudgetStatus
              label="现金流净支出"
              actual={cashNetExpense}
              budget={data.budget?.cash_total}
            />
            <BudgetStatus
              label="摊销后净支出"
              actual={netExpense({
                expense: data.amortized_expense ?? 0,
                income: cash.income,
              })}
              budget={data.budget?.amortized_total}
            />
          </div>
        </section>
      )}
      <section className="form-stack">
        <div className="page-heading">
          <div>
            <h2 className="section-title">支出走势与去向</h2>
            <p className="section-description">
              {basis === "cash"
                ? "按实际付款日期统计支出，关联退款在退款日抵扣。"
                : "跨月费用按月分摊；每月份额在月初归属，非逐日摊销。"}
            </p>
          </div>
          <Segmented
            value={basis}
            options={[
              { value: "cash", label: "现金流" },
              { value: "amortized", label: "摊销后" },
            ]}
            onChange={(value) => onBasisChange(value as Basis)}
          />
        </div>
        <div className="content-panel">
          <div className="chart-heading">
            <h3 className="content-label">
              {granularity === "month" ? "累计净支出" : "各月净支出"} · {basisLabel}
            </h3>
            <span className="chart-value">{money(netExpense(current))}</span>
          </div>
          {data.days ? (
            <EChart
              option={granularity === "month" ? lineOption(daily) : barOption(data.timeline ?? [])}
            />
          ) : (
            <p className="loading-message">期间尚未开始，暂无已发生支出。</p>
          )}
        </div>
        <div className="section-heading">
          <div>
            <h3 className="content-label">分类明细</h3>
            <p className="section-description">
              净支出 = 支出（已扣关联退款）− 收入。点击分类查看具体记录。
            </p>
          </div>
          <Segmented
            value={level}
            options={[
              { value: "category", label: "主类别" },
              { value: "subcategory", label: "子类别" },
            ]}
            onChange={(value) => setLevel(value as BreakdownLevel)}
          />
        </div>
        <div className="breakdown-grid">
          <Breakdown
            title={`支出 · ${basisLabel}`}
            rows={aggregateBreakdown(current.expense_breakdown, level)}
            onSelect={(row) => setDetail({ row, bucket: "expense", level })}
          />
          <Breakdown
            title="收入"
            rows={aggregateBreakdown(current.income_breakdown, level)}
            onSelect={(row) => setDetail({ row, bucket: "income", level })}
          />
        </div>
      </section>
      <DetailDialog data={current} selection={detail} onClose={() => setDetail(null)} />
    </div>
  );
}

function DetailDialog({
  data,
  selection,
  onClose,
}: {
  data: PeriodData;
  selection: DetailSelection | null;
  onClose: () => void;
}) {
  const entries = selection
    ? (data.entries ?? []).filter(
        (entry) =>
          entry.bucket === selection.bucket &&
          (entry.category || "") === (selection.row.category || "") &&
          (selection.level === "category" ||
            (entry.subcategory || "") === (selection.row.subcategory || "")),
      )
    : [];
  return (
    <Dialog
      open={Boolean(selection)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      {selection && (
        <DialogContent layout="center" className="detail-dialog">
          <DialogHeader>
            <DialogTitle>
              {categoryLabel(selection.row)} · {money(selection.row.total)}
            </DialogTitle>
            <DialogDescription>
              本期计入金额合计来自以下记录；退款显示负数，摊销显示本期份额。
            </DialogDescription>
          </DialogHeader>
          <div className="table-scroll">
            <table className="data-table">
              <thead className="summary-table-heading">
                <tr>
                  <th className="summary-heading-cell">交易日期</th>
                  <th className="summary-heading-cell">描述</th>
                  <th className="summary-heading-cell">归属日期</th>
                  <th className="summary-heading-amount">原金额</th>
                  <th className="summary-heading-amount">本期计入</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, index) => (
                  <tr key={`${entry.id}-${entry.allocation_date}-${index}`} className="data-row">
                    <td className="summary-date-cell">{entry.date}</td>
                    <td className="summary-description-cell">
                      {entry.description}
                      <span className="summary-entry-note">#{entry.id}</span>
                    </td>
                    <td className="summary-date-cell">{entry.allocation_date}</td>
                    <td className="summary-amount-cell">{money(entry.amount)}</td>
                    <td className="summary-total-cell">{money(entry.contribution)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <EditorFooter>
            <Button variant="outline" onClick={onClose}>
              关闭明细
            </Button>
          </EditorFooter>
        </DialogContent>
      )}
    </Dialog>
  );
}

function BudgetEditor({ month, budget }: { month: string; budget: MonthBudgetUpdate }) {
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
      queryClient.invalidateQueries({ queryKey: ["expense-analysis"] });
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
function Breakdown({
  title,
  rows,
  onSelect,
}: {
  title: string;
  rows: BreakdownRow[];
  onSelect: (row: BreakdownRow) => void;
}) {
  const max = Math.max(...rows.map((row) => Math.abs(row.total)), 1);
  return (
    <div className="content-panel">
      <h3 className="panel-title">{title}</h3>
      {!rows.length ? (
        <p className="empty-message">本期没有记录。</p>
      ) : (
        <table className="data-table">
          <thead className="summary-table-heading">
            <tr>
              <th className="breakdown-heading-cell">分类</th>
              <th className="breakdown-heading-amount">金额</th>
              <th className="breakdown-heading-amount">笔数</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.category}-${row.subcategory}`} className="data-row">
                <td className="breakdown-label-cell">
                  <button className="breakdown-link" onClick={() => onSelect(row)}>
                    {categoryLabel(row)}
                    <span className="visually-hidden">，查看记录</span>
                  </button>
                  <div className="breakdown-track">
                    <div
                      className="breakdown-fill"
                      style={{ width: `${(Math.abs(row.total) / max) * 100}%` }}
                    />
                  </div>
                </td>
                <td className="breakdown-amount">{money(row.total)}</td>
                <td className="breakdown-count">{row.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric-panel">
      <p className="muted-text">{label}</p>
      <p className="metric-value">{value}</p>
      {hint && <p className="metric-hint">{hint}</p>}
    </div>
  );
}
function BudgetStatus({
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
function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmented-control">
      {options.map((option) => (
        <button
          key={option.value}
          aria-pressed={value === option.value}
          className={cn("segmented-option", value === option.value && "segmented-selected")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
function money(value: number) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
  }).format(value);
}
function optionalAmount(value: string) {
  return value.trim() === "" ? null : Number(value);
}
function categoryLabel(row: BreakdownRow) {
  return row.subcategory
    ? `${row.category || "未分类"} / ${row.subcategory}`
    : row.category || "未分类";
}
function aggregateBreakdown(rows: BreakdownRow[], level: BreakdownLevel): BreakdownRow[] {
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
function fillDaily(data: ExpenseAnalysis) {
  const rows = data.current?.daily ?? [];
  if (!data.selected_period || data.selected_period.length !== 7 || !data.days) return [];
  const byDate = new Map(rows.map((row) => [row.date, row]));
  return Array.from({ length: data.days }, (_, i) => {
    const date = `${data.selected_period}-${String(i + 1).padStart(2, "0")}`;
    return byDate.get(date) ?? { date, income: 0, expense: 0 };
  });
}
function lineOption(rows: { date: string; expense: number }[]) {
  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) => money(Number(value)),
    },
    grid: { left: 65, right: 24, top: 20, bottom: 35 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: rows.map((row) => row.date.slice(5)),
    },
    yAxis: { type: "value" },
    series: [
      {
        name: "累计净支出",
        type: "line",
        showSymbol: rows.length < 15,
        data: rows.map((row) => row.expense),
        itemStyle: { color: "#525252" },
        areaStyle: { opacity: 0.06 },
      },
    ],
  };
}
function barOption(rows: { label: string; expense: number; income: number }[]) {
  return {
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: unknown) => money(Number(value)),
    },
    grid: { left: 65, right: 24, top: 20, bottom: 35 },
    xAxis: { type: "category", data: rows.map((row) => row.label) },
    yAxis: { type: "value" },
    series: [
      {
        name: "净支出",
        type: "bar",
        barMaxWidth: 40,
        data: rows.map(netExpense),
        itemStyle: { color: "#737373" },
      },
    ],
  };
}
