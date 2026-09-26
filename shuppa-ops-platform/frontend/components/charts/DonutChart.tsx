"use client";

import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { categoricalOrder, chartTooltipStyle, CHART_FONT } from "../../lib/theme";

export default function DonutChart({
  data,
  nameKey,
  valueKey,
  colors,
}: {
  data: any[];
  nameKey: string;
  valueKey: string;
  colors?: string[];
}) {
  const palette = colors || categoricalOrder;
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie data={data} dataKey={valueKey} nameKey={nameKey} innerRadius={60} outerRadius={95} paddingAngle={2}>
          {data.map((_, i) => (
            <Cell key={i} fill={palette[i % palette.length]} stroke="var(--surface-solid)" strokeWidth={2} />
          ))}
        </Pie>
        <Tooltip {...chartTooltipStyle} />
        <Legend layout="vertical" align="right" verticalAlign="middle" wrapperStyle={{ fontSize: 12, fontFamily: CHART_FONT }} />
      </PieChart>
    </ResponsiveContainer>
  );
}
