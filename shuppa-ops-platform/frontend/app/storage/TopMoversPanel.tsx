"use client";

import { useState } from "react";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { optimizerApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";

/**
 * Highest sales-velocity products, with a one-click "Check ideal placement"
 * that runs the Smart Placement Advisor for that product - when a product is
 * a top mover, the advisor's scoring gives extra weight to locations closer
 * to dispatch (a synthetic proxy - see the backend's suggest_locations
 * docstring). This does NOT know where a product is stored today (no
 * product-to-slot assignment table exists) - it only shows where it would
 * score best if placed now.
 */
export default function TopMoversPanel({ warehouseId }: { warehouseId?: number }) {
  const movers = useApi(() => optimizerApi.topMovers(warehouseId, 10), [warehouseId]);
  const [checking, setChecking] = useState<number | null>(null);
  const [results, setResults] = useState<Record<number, any>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});

  const checkPlacement = async (productId: number) => {
    setChecking(productId);
    setErrors((e) => ({ ...e, [productId]: "" }));
    try {
      const res = await optimizerApi.suggest({ product_id: productId, warehouse_id: warehouseId, top_n: 2 });
      setResults((r) => ({ ...r, [productId]: res }));
    } catch (e: any) {
      setErrors((err) => ({ ...err, [productId]: e?.message || "Could not check placement." }));
    } finally {
      setChecking(null);
    }
  };

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Top Movers - Placement Check</h3>
      </div>
      <p className="empty-state" style={{ padding: "0 0 8px" }}>
        Highest-velocity products (trailing 30 days). Check a product's ideal placement to see whether it would
        score better in a slot closer to dispatch - this app doesn't track where a product is stored today, only
        where it would score best if placed now.
      </p>
      {movers.loading && <LoadingState />}
      {movers.error && <ErrorState message={movers.error} onRetry={movers.reload} />}
      {movers.data && movers.data.length === 0 && <p className="empty-state">No recent sales history yet.</p>}
      {movers.data?.map((m: any) => (
        <div key={m.product_id} style={{ borderBottom: "1px solid var(--border-color)", padding: "10px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13.5, color: "var(--text-heading)" }}>{m.product_name}</div>
              <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {m.category || "Uncategorized"} - {m.avg_daily_units} units/day avg
              </div>
            </div>
            <button
              className="btn-secondary btn-small"
              type="button"
              disabled={checking === m.product_id}
              onClick={() => checkPlacement(m.product_id)}
            >
              {checking === m.product_id ? "Checking..." : "Check ideal placement"}
            </button>
          </div>
          {errors[m.product_id] && (
            <p className="empty-state" style={{ color: "var(--status-critical)", marginTop: 6 }}>
              {errors[m.product_id]}
            </p>
          )}
          {results[m.product_id] && (
            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
              {results[m.product_id].suggestions.map((s: any) => (
                <div className="suggestion-card" key={s.location_id}>
                  <div className="suggestion-header">
                    <span>
                      {s.storage_type} - Location {s.location_code} / Tier {s.shelf_tier}
                    </span>
                    <span className="fit-score">{s.fit_score}% fit</span>
                  </div>
                  <div className="reason-tags">
                    {s.reasons.map((r: string, i: number) => (
                      <span className="reason-tag" key={i}>
                        {r}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
