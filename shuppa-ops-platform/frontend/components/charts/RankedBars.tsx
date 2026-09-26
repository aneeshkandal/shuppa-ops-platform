"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { categorical, chrome, chartTooltipStyle, CHART_FONT } from "../../lib/theme";

export default function RankedBars({
  data,
  xKey,
  yKey,
  color = categorical.violet,
  valueFormatter,
  layout = "vertical",
}: {
  data: any[];
  xKey: string;
  yKey: string;
  color?: string;
  valueFormatter?: (v: number) => string;
  layout?: "vertical" | "horizontal";
}) {
  const isHorizontalBars = layout === "vertical"; // recharts calls a sideways bar chart layout="vertical"
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 34)}>
      <BarChart
        data={data}
        layout={layout}
        margin={{ top: 8, right: 16, left: isHorizontalBars ? 8 : 0, bottom: 0 }}
      >
        <CartesianGrid stroke={chrome.gridline} horizontal={!isHorizontalBars} vertical={isHorizontalBars} />
        {isHorizontalBars ? (
          <>
            <XAxis type="number" stroke={chrome.muted} tick={{ fontSize: 12, fontFamily: CHART_FONT }} tickFormatter={valueFormatter} />
            <YAxis type="category" dataKey={xKey} stroke={chrome.muted} tick={{ fontSize: 12, fontFamily: CHART_FONT }} width={140} />
          </>
        ) : (
          <>
            <XAxis
              dataKey={xKey}
              stroke={chrome.muted}
              tick={{ fontSize: 11, fontFamily: CHART_FONT }}
              interval={0}
              angle={-20}
              textAnchor="end"
              height={60}
            />
            <YAxis stroke={chrome.muted} tick={{ fontSize: 12, fontFamily: CHART_FONT }} tickFormatter={valueFormatter} />
          </>
        )}
        <Tooltip {...chartTooltipStyle} formatter={(v: number) => (valueFormatter ? valueFormatter(v) : v)} />
        <Bar dataKey={yKey} fill={color} radius={isHorizontalBars ? [0, 4, 4, 0] : [4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
