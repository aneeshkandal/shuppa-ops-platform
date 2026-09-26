"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { categorical, chrome, chartTooltipStyle, CHART_FONT, formatAxisDate } from "../../lib/theme";

/**
 * Renders a historical series (solid) continuing into a naive forecast
 * (dashed) - see backend/app/services/sales_service.py's get_forecast,
 * which fits a simple linear trend over the trailing history and
 * extrapolates it forward. Not a seasonal/ML model - a directional signal.
 */
export default function ForecastTrend({
  history,
  forecast,
  xKey = "bucket",
  yKey = "revenue",
  valueFormatter,
}: {
  history: any[];
  forecast: any[];
  xKey?: string;
  yKey?: string;
  valueFormatter?: (v: number) => string;
}) {
  if (!history || history.length === 0) {
    return <p className="empty-state">Not enough history to chart yet.</p>;
  }

  const forecastKey = `${yKey}_forecast`;
  const merged: Record<string, any>[] = history.map((h) => ({ [xKey]: h[xKey], [yKey]: h[yKey] }));
  // Bridge the two series so the dashed line visually connects to the solid
  // one instead of starting with a gap.
  if (merged.length > 0) {
    merged[merged.length - 1] = { ...merged[merged.length - 1], [forecastKey]: history[history.length - 1][yKey] };
  }
  (forecast || []).forEach((f) => merged.push({ [xKey]: f[xKey], [forecastKey]: f[yKey] }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={merged} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={chrome.gridline} vertical={false} />
        <XAxis
          dataKey={xKey}
          stroke={chrome.muted}
          tick={{ fontSize: 11, fontFamily: CHART_FONT }}
          tickFormatter={formatAxisDate}
        />
        <YAxis stroke={chrome.muted} tick={{ fontSize: 12, fontFamily: CHART_FONT }} tickFormatter={valueFormatter} />
        <Tooltip
          {...chartTooltipStyle}
          labelFormatter={formatAxisDate}
          formatter={(v: number) => (valueFormatter ? valueFormatter(v) : v)}
        />
        <Legend wrapperStyle={{ fontSize: 12, fontFamily: CHART_FONT }} />
        <Line type="monotone" dataKey={yKey} name="Actual" stroke={categorical.magenta} strokeWidth={2} dot={false} connectNulls />
        <Line
          type="monotone"
          dataKey={forecastKey}
          name="Forecast"
          stroke={categorical.violet}
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={false}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
