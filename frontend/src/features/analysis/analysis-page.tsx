import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import { Feedback, Field, selectClass } from "@/features/record/entry-shared";
import { type Basis, type Granularity } from "./utils";
import { Segmented } from "./fields";
import { AnalysisContent } from "./analysis-content";
import "./analysis-page.css";

export function AnalysisPage() {
  const [granularity, setGranularity] = useState<Granularity>("month");
  const [basis, setBasis] = useState<Basis>("amortized");
  const [periods, setPeriods] = useState<Partial<Record<Granularity, string>>>({});
  const period = periods[granularity] ?? null;
  const analysis = useQuery({
    queryKey: ["ledger", "analysis", granularity, period, basis],
    queryFn: () => api.expenseAnalysis(granularity, period, basis),
  });
  const selectedPeriod = analysis.data?.selected_period ?? "";
  return (
    <section className="page-stack analysis-page">
      <header>
        <h1 className="page-title">开销分析</h1>
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
