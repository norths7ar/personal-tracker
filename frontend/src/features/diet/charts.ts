import { BarChart, LineChart, ScatterChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { type DietStats } from "@/api/client";

echarts.use([BarChart, LineChart, ScatterChart, GridComponent, TooltipComponent, CanvasRenderer]);

export function mealTimeOption(rows: DietStats["meal_times"], days: string[]) {
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 32 },
    tooltip: {
      formatter: (params: { data: [string, number, string] }) =>
        `${params.data[0]} ${params.data[2]}`,
    },
    xAxis: {
      type: "category",
      data: days,
      axisLabel: { formatter: (value: string) => value.slice(5) },
    },
    yAxis: {
      type: "value",
      inverse: true,
      min: 0,
      max: 24,
      interval: 4,
      axisLabel: {
        formatter: (value: number) => `${String(value).padStart(2, "0")}:00`,
      },
    },
    series: [
      {
        type: "scatter",
        symbolSize: 9,
        data: rows.map((item) => {
          const [hour = 0, minute = 0] = item.time.split(":").map(Number);
          return [item.date, hour + minute / 60, item.time] as [string, number, string];
        }),
      },
    ],
  };
}

export function frequencyOption(rows: { name: string; count: number }[]) {
  const visible = rows.slice(0, 10);
  return {
    grid: { left: 12, right: 32, top: 16, bottom: 24, containLabel: true },
    yAxis: {
      type: "category",
      inverse: true,
      data: visible.map((item) => item.name),
      axisLabel: { width: 120, overflow: "chart-label" },
    },
    xAxis: { type: "value", minInterval: 1 },
    series: [
      {
        type: "bar",
        barMaxWidth: 18,
        label: { show: true, position: "right" },
        data: visible.map((item) => item.count),
      },
    ],
    tooltip: { trigger: "axis" },
  };
}

export function formatDate(value: Date): string {
  return new Intl.DateTimeFormat("en-CA").format(value);
}
