"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chrome, stockStatusColor, chartTooltipStyle, CHART_FONT, formatAxisDate } from "../../lib/theme";

export default function StackedAreaTrend({
  data,
  xKey,
  series,
}: {
  data: any[];
  xKey: string;
  series: { key: string; label: string }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={chrome.gridline} vertical={false} />
        <XAxis
          dataKey={xKey}
          stroke={chrome.muted}
          tick={{ fontSize: 12, fontFamily: CHART_FONT }}
          tickFormatter={formatAxisDate}
        />
        <YAxis stroke={chrome.muted} tick={{ fontSize: 12, fontFamily: CHART_FONT }} />
        <Tooltip {...chartTooltipStyle} labelFormatter={formatAxisDate} />
        <Legend wrapperStyle={{ fontSize: 12, fontFamily: CHART_FONT }} />
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stackId="1"
            stroke={stockStatusColor[s.key.toUpperCase()] || "#2a78d6"}
            fill={stockStatusColor[s.key.toUpperCase()] || "#2a78d6"}
            fillOpacity={0.35}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
