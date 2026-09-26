// Chart / data-encoding colors, taken from the validated palette in the
// dataviz skill (references/palette.md). These are for DATA (series, status)
// - the pink/purple gradient chrome around them (backgrounds, sidebar) is
// separate and lives in globals.css.

export const categorical = {
  blue: "#2a78d6",
  orange: "#eb6834",
  aqua: "#1baf7a",
  yellow: "#eda100",
  magenta: "#e87ba4",
  green: "#008300",
  violet: "#4a3aa7",
  red: "#e34948",
};

// Fixed order - never cycle/reassign per filter.
export const categoricalOrder = [
  categorical.blue,
  categorical.orange,
  categorical.aqua,
  categorical.yellow,
  categorical.magenta,
  categorical.green,
  categorical.violet,
  categorical.red,
];

// Reserved - never reused for a plain series.
export const status = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
};

// Stock health states map onto the fixed status roles.
export const stockStatusColor: Record<string, string> = {
  HEALTHY: status.good,
  LOW: status.warning,
  OVERSTOCK: status.serious,
  CRITICAL: status.critical,
};

// Supplier / delivery risk levels.
export const riskLevelColor: Record<string, string> = {
  LOW: status.good,
  MEDIUM: status.warning,
  HIGH: status.critical,
};

// Supplier Return line-item resolution states.
export const resolutionColor: Record<string, string> = {
  PENDING: status.warning,
  RETURNED: status.good,
  RESOLVED: status.good,
  PO_GENERATED: categorical.blue,
  LISTED_AS_NEW_PRODUCT: categorical.violet,
};

// Sequential (single hue, light -> dark) for magnitude/heatmap encodings.
export const sequentialBlue = [
  "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b",
];

// Chart chrome (gridlines/axis text) reads the same CSS variables the rest
// of the UI uses for light/dark mode, rather than a fixed hex, so charts
// stop looking "pasted on" against a dark card. DATA colors above are left
// untouched - only the surrounding scaffolding adapts.
export const chrome = {
  textPrimary: "var(--text-primary)",
  textSecondary: "var(--text-secondary)",
  muted: "var(--text-muted)",
  gridline: "var(--border-subtle)",
};

export const CHART_FONT = "Inter, -apple-system, BlinkMacSystemFont, sans-serif";

// Every trend chart's X axis is fed a raw bucket value straight from the
// backend - a Postgres date/timestamp serializes to an ISO string like
// "2025-12-05" or "2025-12-05T00:00:00" - and Recharts prints whatever it's
// given verbatim if no tickFormatter is set. Shown as-is, that reads as a
// rendering bug rather than a date. This turns a recognizable ISO date into
// a short "5 Dec" label; anything that isn't one (a category name, a
// month name already formatted server-side, etc.) is returned unchanged,
// so it's safe to use as the default formatter on any bucket-shaped axis.
const ISO_DATE_PREFIX = /^\d{4}-\d{2}-\d{2}/;
export function formatAxisDate(value: unknown): string {
  if (typeof value !== "string" || !ISO_DATE_PREFIX.test(value)) return value == null ? "" : String(value);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

// Turns an hour-of-day integer (0-23) into a 12-hour clock label ("12 AM",
// "1 PM", ...) for the Peak Order Time chart. Passed through formatAxisDate-
// style charts as an already-formatted category label, not a date.
export function formatHourLabel(hour: number): string {
  const h = ((hour % 24) + 24) % 24;
  const period = h < 12 ? "AM" : "PM";
  const display = h % 12 === 0 ? 12 : h % 12;
  return `${display} ${period}`;
}

// Shared Recharts <Tooltip> styling so every chart's tooltip matches the
// app's glass-card look (and stays legible in dark mode) instead of
// Recharts' plain white default box.
export const chartTooltipStyle = {
  contentStyle: {
    borderRadius: 12,
    border: "1px solid var(--border-soft)",
    boxShadow: "0 12px 32px rgba(0, 0, 0, 0.18)",
    background: "var(--surface-solid)",
    color: "var(--text-primary)",
    fontSize: 12.5,
    fontFamily: CHART_FONT,
    padding: "8px 12px",
  },
  labelStyle: { color: "var(--text-heading)", fontWeight: 700, marginBottom: 4 },
  itemStyle: { color: "var(--text-primary)" },
  cursor: { fill: "rgba(139, 92, 246, 0.06)" },
};
