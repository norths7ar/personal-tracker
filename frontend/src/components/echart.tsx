import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { useEffect, useRef } from "react";

const chartTheme = {
  color: ["#4d4d4d"],
  textStyle: { fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif', color: "#6e6e6e" },
  categoryAxis: {
    axisLine: { lineStyle: { color: "#e1e1e1" } },
    axisTick: { show: false },
    axisLabel: { color: "#7e7e7e", margin: 12 },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: "#7e7e7e" },
    splitLine: { lineStyle: { color: "#eaeaea", type: "dashed" } },
  },
  line: { symbol: "circle", symbolSize: 7, lineStyle: { width: 3 } },
  bar: { itemStyle: { borderRadius: 4 } },
  tooltip: {
    backgroundColor: "#ffffff",
    borderColor: "#e3e3e3",
    padding: [12, 16],
    textStyle: { color: "#424242", fontSize: 13 },
    extraCssText: "border-radius:12px;box-shadow:0 8px 32px #40404015;",
    axisPointer: { lineStyle: { color: "#aaaaaa", type: "dashed" } },
  },
};

export function EChart({ option, height = 280 }: { option: object; height?: number }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const chart = echarts.init(container.current, chartTheme);
    chart.setOption(
      {
        animationDuration: 450,
        ...option,
        animation: !window.matchMedia("(prefers-reduced-motion: reduce)").matches,
      } as EChartsCoreOption,
      { notMerge: true },
    );
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return <div ref={container} style={{ height }} />;
}
