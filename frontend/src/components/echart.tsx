import * as echarts from "echarts/core";
import type { EChartsCoreOption } from "echarts/core";
import { useEffect, useRef } from "react";

export function EChart({
  option,
  height = 280,
}: {
  option: object;
  height?: number;
}) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    const chart = echarts.init(container.current);
    chart.setOption(option as EChartsCoreOption, { notMerge: true });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return <div ref={container} style={{ height }} />;
}
