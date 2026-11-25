import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { type ExpenseAnalysis } from "@/api/client";
import { netExpense } from "@/features/analysis/calculations";
import { money } from "./utils";

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  MarkLineComponent,
  CanvasRenderer,
]);

export function lineOption(
  rows: { date: string; expense: number }[],
  elapsedDays: number,
  budgetLimit?: number | null,
) {
  const split = Math.max(0, Math.min(elapsedDays, rows.length));
  const maxExpense = Math.max(...rows.map((row) => row.expense), 0);
  const showBudgetInAxis =
    budgetLimit != null && (maxExpense >= budgetLimit * 0.5 || split >= rows.length);

  const markLine =
    budgetLimit != null
      ? {
          silent: true,
          symbol: "none",
          lineStyle: { type: "dashed" as const, color: "#c2410c", opacity: 0.55 },
          label: {
            formatter: () => `预算 ${money(budgetLimit)}`,
            position: "insideEndTop" as const,
            color: "#9a3412",
          },
          data: [{ yAxis: budgetLimit }],
        }
      : undefined;

  const series = [];
  if (split > 0) {
    series.push({
      name: "累计净支出",
      type: "line",
      showSymbol: rows.length < 15,
      data: rows.map((row, index) => (index < split ? row.expense : null)),
      itemStyle: { color: "#4d4d4d" },
      lineStyle: { width: 3 },
      areaStyle: {
        color: "#4d4d4d",
        opacity: 0.07,
      },
      markLine,
    });
  }
  if (split < rows.length) {
    const startIndex = Math.max(0, split - 1);
    series.push({
      name: "未到日期",
      type: "line",
      showSymbol: false,
      data: rows.map((row, index) => (index >= startIndex ? row.expense : null)),
      itemStyle: { color: "#8c8c8c" },
      lineStyle: { width: 2, type: "dashed" as const, color: "#8c8c8c" },
      ...(series.length === 0 ? { markLine } : {}),
    });
  }

  return {
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const items = Array.isArray(params) ? params : [params];
        const valid = items.filter(
          (item): item is { axisValueLabel?: string; dataIndex?: number; value?: unknown } =>
            typeof item === "object" && item !== null && "value" in item && item.value != null,
        );
        const point = valid[0];
        if (!point) return "";
        const index = point.dataIndex ?? 0;
        const suffix = index >= split ? "（未到日期）" : "";
        return `${point.axisValueLabel ?? ""}${suffix}<br/>累计净支出：${money(Number(point.value))}`;
      },
    },
    grid: { left: 65, right: 24, top: 28, bottom: 35 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: rows.map((row) => row.date.slice(5)),
    },
    yAxis: {
      type: "value",
      ...(showBudgetInAxis && budgetLimit != null
        ? { max: (value: { max: number }) => Math.max(value.max, budgetLimit) }
        : {}),
    },
    series,
  };
}

export function barOption(rows: { label: string; expense: number; income: number }[]) {
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
        itemStyle: {
          borderRadius: 5,
          color: "#4d4d4d",
        },
      },
    ],
  };
}

export function fillDaily(data: ExpenseAnalysis) {
  const rows = data.current?.daily ?? [];
  const totalDays = data.total_days ?? data.days ?? 0;
  if (!data.selected_period || data.selected_period.length !== 7 || !totalDays) return [];
  const byDate = new Map(rows.map((row) => [row.date, row]));
  return Array.from({ length: totalDays }, (_, i) => {
    const date = `${data.selected_period}-${String(i + 1).padStart(2, "0")}`;
    return byDate.get(date) ?? { date, income: 0, expense: 0 };
  });
}
