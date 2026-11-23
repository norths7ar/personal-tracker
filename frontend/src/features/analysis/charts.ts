import { BarChart, LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { type ExpenseAnalysis } from "@/api/client";
import { netExpense } from "@/features/analysis/calculations";
import { money } from "./utils";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export function lineOption(rows: { date: string; expense: number }[]) {
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
        itemStyle: { color: "#4d4d4d" },
        lineStyle: { width: 3 },
        areaStyle: {
          color: "#4d4d4d",
          opacity: 0.07,
        },
      },
    ],
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
  if (!data.selected_period || data.selected_period.length !== 7 || !data.days) return [];
  const byDate = new Map(rows.map((row) => [row.date, row]));
  return Array.from({ length: data.days }, (_, i) => {
    const date = `${data.selected_period}-${String(i + 1).padStart(2, "0")}`;
    return byDate.get(date) ?? { date, income: 0, expense: 0 };
  });
}
