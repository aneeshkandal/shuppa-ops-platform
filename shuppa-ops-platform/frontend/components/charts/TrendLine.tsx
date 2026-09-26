"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { categorical, chrome, chartTooltipStyle, CHART_FONT, formatAxisDate } from "../../lib/theme";

export default function TrendLine({
  data,
  xKey,
  yKey,
  color = categorical.blue,
  valueFormatter,
}: {
  data: any[];
  xKey: string;
  yKey: string;
  color?: string;
  valueFormatter?: (v: number) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={chrome.gridline} vertical={false} />
        <XAxis
          dataKey={xKey}
          stroke={chrome.muted}
          tick={{ fontSize: 12, fontFamily: CHART_FONT }}
          tickFormatter={formatAxisDate}
        />
        <YAxis stroke={chrome.muted} tick={{ fontSize: 12, fontFamily: CHART_FONT }} tickFormatter={valueFormatter} />
        <Tooltip
          {...chartTooltipStyle}
          labelFormatter={formatAxisDate}
          formatter={(v: number) => (valueFormatter ? valueFormatter(v) : v)}
        />
        <Line type="monotone" dataKey={yKey} stroke={color} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
