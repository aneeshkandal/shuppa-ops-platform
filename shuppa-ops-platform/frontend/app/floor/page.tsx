"use client";

import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import { optimizerApi, stockApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";

/**
 * Today's two most actionable lists for a picker or warehouse floor worker -
 * reorder suggestions and top movers. Originally a standalone, no-sidebar
 * page for a phone-width screen, but that left it a dead end (no way back
 * to the rest of the dashboard) - it now uses the same AppLayout/Sidebar/
 * TopBar shell as every other page, so it's reachable and escapable like
 * anywhere else. The compact "floor-card" list styling is kept since it's
 * still a nice, scannable format on a narrow screen.
 */
export default function FloorViewPage() {
  const { warehouseId, setWarehouseId } = useFilters();

  const reorder = useApi(() => stockApi.reorderSuggestions(10, warehouseId), [warehouseId]);
  const movers = useApi(() => optimizerApi.topMovers(warehouseId, 8), [warehouseId]);

  return (
    <AppLayout>
      <TopBar title="Floor View">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
      </TopBar>
      <div className="content-area">
        <div className="grid-2">
          <div className="card">
            <div className="chart-card-header">
              <h3>Reorder Today</h3>
            </div>
            {reorder.loading && <LoadingState />}
            {reorder.error && <ErrorState message={reorder.error} onRetry={reorder.reload} />}
            {reorder.data && reorder.data.length === 0 && <p className="empty-state">Nothing needs reordering.</p>}
            {reorder.data?.map((r: any) => (
              <div className="floor-card" key={r.product_id}>
                <div className="floor-card-title">{r.product_name}</div>
                <div className="floor-card-detail">
                  Qty: <strong>{r.suggested_reorder_qty}</strong>
                  {r.is_estimate ? " (estimate)" : ""} · On hand: {r.stock_on_hand}
                </div>
                {r.best_supplier && (
                  <div className="floor-card-detail">Supplier: {r.best_supplier.supplier_name}</div>
                )}
              </div>
            ))}
          </div>

          <div className="card">
            <div className="chart-card-header">
              <h3>Top Movers</h3>
            </div>
            {movers.loading && <LoadingState />}
            {movers.error && <ErrorState message={movers.error} onRetry={movers.reload} />}
            {movers.data && movers.data.length === 0 && <p className="empty-state">No standout movers yet.</p>}
            {movers.data?.map((m: any) => (
              <div className="floor-card" key={m.product_id}>
                <div className="floor-card-title">{m.product_name}</div>
                <div className="floor-card-detail">{m.avg_daily_units} units/day avg</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
