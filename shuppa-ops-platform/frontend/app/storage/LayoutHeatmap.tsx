import { useEffect, useState } from "react";
import { sequentialBlue, status } from "../../lib/theme";

// Same canonical order used everywhere else this enum shows up (Admin ->
// Add Product/Locations, Smart Placement Advisor) - only used to sort
// whichever types are actually present into a familiar order; a type this
// app has never seen still shows up (sorted after the known ones) rather
// than silently disappearing.
const STORAGE_TYPE_ORDER = ["AMBIENT", "CHILLED", "FROZEN", "VAPE_DRAWER"];

function colorFor(pct: number): string {
  if (pct > 95) return status.critical;
  if (pct > 85) return status.serious;
  const steps = sequentialBlue;
  const idx = Math.min(steps.length - 1, Math.floor((pct / 100) * steps.length));
  return steps[idx];
}

/**
 * Store Layout Heatmap - one cell per physical storage slot. A full
 * warehouse has 500+ slots (most locations carry one slot per shelf tier,
 * but a handful - vape drawers, small-item bins - carry 20-40 each), which
 * made a single ungrouped grid grow arbitrarily tall. Tabbed by storage
 * type (the same grouping the "Store Layout" card right next to this one
 * already shows, and the same `.insight-tabs`/`.insight-tab` pill style
 * KeyInsightsCard uses) bounds the grid to whichever slice is selected
 * instead of dumping every slot into one grid at once.
 */
export default function LayoutHeatmap({ data, onCellClick }: { data: any[]; onCellClick?: (locationId: number) => void }) {
  const [activeType, setActiveType] = useState<string | null>(null);

  const seenTypes = Array.from(new Set((data || []).map((c) => c.storage_type)));
  const typesPresent = [
    ...STORAGE_TYPE_ORDER.filter((t) => seenTypes.includes(t)),
    ...seenTypes.filter((t) => !STORAGE_TYPE_ORDER.includes(t)),
  ];

  // A fresh fetch (a warehouse change) can come back with a different mix
  // of storage types entirely - reset to the first tab whenever the
  // currently-selected type isn't in the new list, rather than silently
  // showing an empty grid. Mirrors KeyInsightsCard's own reset-on-refetch
  // pattern.
  useEffect(() => {
    if (typesPresent.length > 0 && !typesPresent.includes(activeType || "")) {
      setActiveType(typesPresent[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  if (!data || data.length === 0) return <p className="empty-state">No location data yet.</p>;

  const visible = data.filter((c) => c.storage_type === activeType);

  return (
    <div>
      {typesPresent.length > 1 && (
        <div className="insight-tabs">
          {typesPresent.map((t) => (
            <button
              key={t}
              type="button"
              className={`insight-tab${t === activeType ? " active" : ""}`}
              onClick={() => setActiveType(t)}
            >
              {t.replace("_", " ")} ({data.filter((c) => c.storage_type === t).length})
            </button>
          ))}
        </div>
      )}
      <div className="heatmap-grid">
        {visible.map((cell) => (
          <div
            key={cell.location_id}
            className="heatmap-cell heatmap-cell-clickable"
            title={`Location ${cell.location_code} / Tier ${cell.shelf_tier} (${cell.storage_type}) - ${cell.utilization_pct}% full - click for details`}
            style={{ background: colorFor(cell.utilization_pct) }}
            role="button"
            tabIndex={0}
            onClick={() => onCellClick?.(cell.location_id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onCellClick?.(cell.location_id);
              }
            }}
          >
            {Math.round(cell.utilization_pct)}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 12, fontSize: 12, color: "var(--text-secondary)", flexWrap: "wrap" }}>
        <span>
          <span style={{ color: sequentialBlue[1] }}>&#9632;</span> Low usage (&lt;60%)
        </span>
        <span>
          <span style={{ color: status.serious }}>&#9632;</span> Overstocked (85-95%)
        </span>
        <span>
          <span style={{ color: status.critical }}>&#9632;</span> Over capacity (&gt;95%)
        </span>
      </div>
    </div>
  );
}
