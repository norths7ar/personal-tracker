import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type Meal } from "@/api/client";
import { EChart } from "@/components/echart";
import { Feedback, Field, selectClass } from "@/features/record/entry-shared";
import { formatDate, frequencyOption, mealTimeOption } from "./charts";

export function DietAnalysis({ meals }: { meals: Meal[] }) {
  const months = [...new Set(meals.map((meal) => meal.date.slice(0, 7)))].sort().reverse();
  const [today] = useState(() => formatDate(new Date()));
  const [selectedMonth, setSelectedMonth] = useState(months[0] ?? today.slice(0, 7));
  const [year, month] = selectedMonth.split("-").map(Number);
  const startDate = `${selectedMonth}-01`;
  const monthEnd = formatDate(new Date(year!, month!, 0));
  const endDate = monthEnd < today ? monthEnd : today;
  const days = Array.from(
    {
      length: selectedMonth > today.slice(0, 7) ? 0 : Number(endDate.slice(-2)),
    },
    (_, index) => `${selectedMonth}-${String(index + 1).padStart(2, "0")}`,
  );
  const stats = useQuery({
    queryKey: ["diet", "stats", startDate, endDate],
    queryFn: () => api.dietStats(startDate, endDate),
  });
  if (!months.length) return <div className="empty-panel">暂无饮食记录。</div>;
  if (stats.isPending) return <p className="muted-text">正在分析…</p>;
  if (stats.isError) return <Feedback error={stats.error} />;
  const totalRecords = stats.data.daily_meals.reduce((sum, item) => sum + item.count, 0);
  const dailyCounts = new Map(stats.data.daily_meals.map((item) => [item.date, item.count]));
  const topFood = stats.data.food_freq[0]?.food_name ?? "—";
  return (
    <div className="form-stack">
      <div className="diet-analysis-toolbar">
        <Field label="月份">
          <select
            className={`${selectClass} diet-period-select`}
            value={selectedMonth}
            onChange={(event) => setSelectedMonth(event.target.value)}
          >
            {months.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </Field>
        <p className="diet-analysis-period">
          {days.length ? `${startDate} 至 ${endDate} · ${days.length} 天` : "所选期间尚未开始。"}
        </p>
      </div>
      <div className="metrics-grid">
        <Metric
          label="记录天数 / 期间天数"
          value={`${stats.data.daily_meals.length} / ${days.length}`}
        />
        <Metric label="饮食记录次数" value={String(totalRecords)} />
        <Metric
          label="日均记录次数"
          value={days.length ? (totalRecords / days.length).toFixed(1) : "—"}
        />
        <Metric label="最高频食物" value={topFood} />
      </div>
      <div className="diet-charts">
        <Chart title="用餐时间分布" option={mealTimeOption(stats.data.meal_times, days)} />
        <Chart
          title="每日饮食记录次数"
          option={{
            grid: { left: 40, right: 16, top: 24, bottom: 32 },
            xAxis: {
              type: "category",
              data: days,
              axisLabel: { formatter: (value: string) => value.slice(5) },
            },
            yAxis: { type: "value", min: 0, minInterval: 1 },
            series: [
              {
                type: "line",
                connectNulls: false,
                showSymbol: true,
                showAllSymbol: true,
                symbol: "circle",
                symbolSize: 7,
                data: days.map((day) => dailyCounts.get(day) ?? null),
              },
            ],
            tooltip: { trigger: "axis" },
          }}
        />
      </div>
      <div className="diet-charts">
        <Chart
          title="高频食物"
          option={frequencyOption(
            stats.data.food_freq.map((item) => ({
              name: item.food_name,
              count: item.count,
            })),
          )}
        />
        <Chart
          title="高频食材"
          empty={!stats.data.ingredient_freq.length}
          option={frequencyOption(
            stats.data.ingredient_freq.map((item) => ({
              name: item.ingredient_name,
              count: item.count,
            })),
          )}
        />
      </div>
      <details className="diet-methodology">
        <summary>统计口径</summary>
        <dl>
          <div>
            <dt>记录次数</dt>
            <dd>
              按记录次数统计，零食记录不视为一餐；未记录不代表没有进食。日均记录次数按期间{" "}
              {days.length} 天计算。
            </dd>
          </div>
          <div>
            <dt>时间与趋势</dt>
            <dd>
              用餐时间从上到下由早到晚，仅展示已记录的时间。趋势断点表示当天未记录，不计为进食 0
              次。
            </dd>
          </div>
          <div>
            <dt>食物与食材</dt>
            <dd>
              食物按原文统计，不合并相似名称。{totalRecords} 条记录中有{" "}
              {stats.data.ingredient_record_count}{" "}
              条包含食材；同一食材每条记录只计一次，未填写不代表未食用。
            </dd>
          </div>
        </dl>
      </details>
    </div>
  );
}

function Chart({
  title,
  option,
  empty = false,
}: {
  title: string;
  option: object;
  empty?: boolean;
}) {
  return (
    <div className="metric-panel">
      <h2 className="content-label">{title}</h2>
      {empty ? <p className="chart-empty">该期间尚无食材数据。</p> : <EChart option={option} />}
    </div>
  );
}

export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-panel">
      <p className="muted-text">{label}</p>
      <p className="metric-value">{value}</p>
    </div>
  );
}
