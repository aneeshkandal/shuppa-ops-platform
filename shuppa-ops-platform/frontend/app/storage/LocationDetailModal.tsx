"use client";

import { useEffect } from "react";
import { optimizerApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import Icon from "../../components/Icon";

/**
 * Popup shown when a Store Layout Heatmap cell is clicked. Fetches
 * GET /optimizer/locations/{id} (see storage_optimizer.get_location_detail)
 * on demand, only while a location is selected - `useApi`'s dep array is
 * `[locationId]`, and the fetcher resolves to null immediately when there
 * isn't one, so nothing is requested until a cell is actually clicked.
 *
 * Every product listed here is a REAL row in dim_product_placements - either
 * someone actually confirmed that slot through the Placement Advisor
 * ("Place here"), or it was backfilled by a one-time migration because the
 * product carries real inventory in this warehouse but nobody had ever
 * recorded where it physically sits (placement tracking didn't exist before
 * this feature). The "Backfilled" badge makes that distinction visible
 * rather than presenting a reconstructed guess as confirmed fact - see
 * app/migrations.py's comment on dim_product_placements for the full
 * reasoning.
 */
export default function LocationDetailModal({
  locationId,
  onClose,
}: {
  locationId: number | null;
  onClose: () => void;
}) {
  const detail = useApi(
    () => (locationId ? optimizerApi.locationDetail(locationId) : Promise.resolve(null)),
    [locationId]
  );

  useEffect(() => {
    if (!locationId) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [locationId, onClose]);

  if (!locationId) return null;

  const loc = detail.data?.location;
  const products = detail.data?.products || [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">{loc ? `Location ${loc.location_code} / Tier ${loc.shelf_tier}` : "Location details"}</div>
            {loc && (
              <div className="modal-subtitle">
                {loc.warehouse_name} · {loc.storage_type.replace("_", " ")}
                {loc.sub_location != null ? ` · Slot ${loc.sub_location}` : ""}
              </div>
            )}
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close" type="button">
            <Icon name="x" size={20} />
          </button>
        </div>

        {detail.loading && <LoadingState />}
        {detail.error && <ErrorState message={detail.error} onRetry={detail.reload} />}

        {loc && (
          <>
            <div className="location-stat-grid">
              <div className="location-stat">
                <div className="location-stat-label">Utilization</div>
                <div className="location-stat-value">{loc.utilization_pct}%</div>
              </div>
              <div className="location-stat">
                <div className="location-stat-label">Weight</div>
                <div className="location-stat-value">
                  {loc.current_weight_kg} / {loc.max_weight_kg} kg
                </div>
              </div>
              <div className="location-stat">
                <div className="location-stat-label">Volume</div>
                <div className="location-stat-value">
                  {loc.current_volume_cm3} / {loc.max_volume_cm3} cm³
                </div>
              </div>
              <div className="location-stat">
                <div className="location-stat-label">Overstock tier</div>
                <div className="location-stat-value">{loc.is_overstock_tier ? "Yes" : "No"}</div>
              </div>
            </div>

            {loc.is_synthetic_capacity && (
              <p className="empty-state" style={{ marginTop: -8, marginBottom: 16 }}>
                This slot's maximum capacity (the "/ {loc.max_weight_kg} kg" and "/ {loc.max_volume_cm3} cm³" figures
                above) is an estimated ceiling - there's no real per-slot maximum-capacity data to replace it with.
                The current weight/volume/utilization numbers themselves are real, though: they're computed from the
                products actually listed below, not a synthetic value - see README.md's Known Limitations.
              </p>
            )}

            <div className="chart-card-header">
              <h3>Products stored here ({products.length})</h3>
            </div>
            {products.length === 0 && (
              <p className="empty-state">No product is on record as placed at this specific slot.</p>
            )}
            {products.map((p: any) => (
              <div className="location-product-row" key={p.product_id}>
                <div>
                  <div className="location-product-name">{p.product_name}</div>
                  <div className="location-product-meta">
                    {p.category} · {p.length_cm}×{p.width_cm}×{p.height_cm} cm · {p.weight_kg} kg
                    {p.current_stock_on_hand != null ? ` · ${p.current_stock_on_hand} on hand` : ""}
                  </div>
                </div>
                {p.is_backfilled && (
                  <span className="backfilled-badge" title="Reconstructed automatically - nobody actually confirmed this slot for this product; see README.md">
                    Backfilled
                  </span>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
