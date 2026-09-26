// Shared formatting for the "vs previous period" KPI-card deltas the
// backend attaches as `comparison.deltas.<key>` on every KPI/summary
// endpoint (see backend/app/services/db_utils.py's compute_deltas).

export type Delta = { previous: number; absolute: number; pct: number | null } | null | undefined;

/**
 * Turns a raw delta object into KpiCard's `delta` (display text) and
 * `deltaGood` (color) props. `higherIsBetter` flips which direction counts
 * as "good" (e.g. a rising stockout % is bad, a rising on-time % is good).
 */
export function formatDelta(
  delta: Delta,
  opts: { higherIsBetter?: boolean; isPercentagePoints?: boolean; isCurrency?: boolean } = {}
): { text: string; good: boolean } | null {
  if (!delta || delta.absolute == null) return null;
  const { higherIsBetter = true, isPercentagePoints = false, isCurrency = false } = opts;

  const absRounded = Math.abs(delta.absolute);
  if (absRounded < 0.005 && (delta.pct == null || Math.abs(delta.pct) < 0.05)) {
    return { text: "No change vs last period", good: true };
  }

  const sign = delta.absolute > 0 ? "+" : "-";
  // Currency deltas round to whole units, same as the KPI card's own `money()`
  // value next to them - showing a fractional cent there (e.g. "+292,572,587.7")
  // while the headline figure is a whole euro amount reads as a formatting bug.
  const magnitude = isPercentagePoints
    ? `${absRounded.toFixed(1)}pp`
    : absRounded.toLocaleString(undefined, { maximumFractionDigits: isCurrency ? 0 : 1 });
  const pctText = !isPercentagePoints && delta.pct != null ? ` (${sign}${Math.abs(delta.pct).toFixed(1)}%)` : "";

  const good = delta.absolute === 0 ? true : (delta.absolute > 0) === higherIsBetter;
  return { text: `${sign}${magnitude}${pctText} vs last period`, good };
}

/** "Last updated Xs/Xm/Xh ago" for the polling-refresh indicator (see useApi's `lastUpdated`). */
export function formatRelativeTime(timestampMs: number | null, nowMs: number = Date.now()): string {
  if (!timestampMs) return "";
  const seconds = Math.max(0, Math.round((nowMs - timestampMs) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  return `${hours}h ago`;
}
