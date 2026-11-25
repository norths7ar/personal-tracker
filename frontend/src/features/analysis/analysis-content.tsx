import { useMemo, useState } from "react";
import { type ExpenseAnalysis } from "@/api/client";
import { EChart } from "@/components/echart";
import { cumulativeNetExpense, netExpense } from "@/features/analysis/calculations";
import {
  aggregateBreakdown,
  money,
  type Basis,
  type BreakdownLevel,
  type DetailSelection,
  type Granularity,
} from "./utils";
import { barOption, fillDaily, lineOption } from "./charts";
import { Metric, Segmented } from "./fields";
import { BudgetEditor, BudgetStatus } from "./budget-editor";
import { Breakdown, DetailDialog } from "./detail-dialog";

export function AnalysisContent({
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
  const elapsedDays = data.days ?? 0;
  const budgetLimit =
    granularity === "month"
      ? basis === "cash"
        ? data.budget?.cash_total
        : data.budget?.amortized_total
      : null;
  const hasChartData = granularity === "month" ? daily.length > 0 : elapsedDays > 0;

  return (
    <div className="analysis-sections">
      <section className="summary-section">
        <h2 className="section-title">现金收支</h2>
        <div className="metrics-grid">
          <Metric label="现金支出" value={money(cash.expense)} />
          <Metric label="现金收入" value={money(cash.income)} />
          <Metric
            label="日均现金支出"
            value={elapsedDays ? money(cash.expense / elapsedDays) : "—"}
            hint={elapsedDays ? `已过 ${elapsedDays} 天` : "期间尚未开始"}
          />
          <Metric label="收支结余" value={money(cash.balance)} />
        </div>
      </section>
      {granularity === "month" && (
        <section className="summary-section">
          <div className="page-heading">
            <h2 className="section-title">月度预算</h2>
            <BudgetEditor
              month={data.selected_period!}
              budget={data.budget ?? { amortized_total: null, cash_total: null }}
            />
          </div>
          <div className="content-panel analysis-budget">
            <div className="budget-grid">
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
          </div>
        </section>
      )}
      <section className="form-stack">
        <div className="page-heading">
          <h2 className="section-title">支出走势与去向</h2>
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
          {hasChartData ? (
            <EChart
              option={
                granularity === "month"
                  ? lineOption(daily, elapsedDays, budgetLimit)
                  : barOption(data.timeline ?? [])
              }
            />
          ) : (
            <p className="loading-message">期间尚未开始，暂无已发生支出。</p>
          )}
        </div>
        <div className="section-heading">
          <h3 className="content-label">分类明细</h3>
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
      <details className="analysis-methodology">
        <summary>统计口径</summary>
        <dl>
          <div>
            <dt>净支出与结余</dt>
            <dd>
              净支出 = 支出（已扣关联退款）− 收入；收支结余 = 收入 −
              付款口径支出（已扣关联退款）。日均现金支出按期间已过天数计算。
            </dd>
          </div>
          <div>
            <dt>现金流</dt>
            <dd>按实际付款日期统计支出，关联退款在退款日抵扣。</dd>
          </div>
          <div>
            <dt>摊销后</dt>
            <dd>
              设置生效期的支出按起止日（含）逐天分摊，月度视图展示全月已确定分摊（未到日期以虚线表示）；未设置生效期的支出按付款日归属。
            </dd>
          </div>
        </dl>
      </details>
      <DetailDialog data={current} selection={detail} onClose={() => setDetail(null)} />
    </div>
  );
}
