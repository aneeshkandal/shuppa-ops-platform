"use client";

import { useState } from "react";
import { optimizerApi, WAREHOUSES } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import Icon from "../../components/Icon";

const warehouseName = (id: number) => WAREHOUSES.find((w) => w.id === id)?.name || `Warehouse ${id}`;

/**
 * Products added through the Admin "Add Product" form land here until
 * someone runs the Smart Placement Advisor for them and confirms slots -
 * this is the "whenever a new product is added it will be displayed in the
 * location suggester" requirement made visible on every Stock Optimizer
 * page.
 *
 * Renders a putaway grid: one row per warehouse, one column per candidate
 * location in that warehouse (storage_optimizer.suggest_locations returns
 * up to top_n candidates PER warehouse when no warehouse filter is passed -
 * see that function's docstring). Every row starts pre-selected with its own
 * best-scoring candidate (radio-style - clicking a different card in a row
 * replaces that row's pick, but never affects other rows), so the common
 * case is just reviewing the defaults and confirming rather than
 * hand-picking every row. "Confirm Putaway for All Locations" only enables
 * once every row has a pick, then confirms all of them together in one
 * atomic call (POST /optimizer/mark-placed-bulk - see
 * storage_optimizer.mark_placed_bulk) rather than one request per warehouse.
 *
 * Deliberately does NOT scope the suggestion request to the page's
 * currently selected warehouse filter (unlike the Overstocked/Underutilized
 * tables and the heatmap on this same page) - a brand-new product should be
 * shown real options in every warehouse, not just whichever one the page
 * happens to be filtered to when someone clicks "Suggest Locations". A
 * WAREHOUSE-role login is still transparently locked to their own warehouse
 * server-side regardless (see storage_optimizer.suggest_locations's
 * docstring) - that's an access-control boundary, not a scoping preference,
 * so it's unaffected by this component not threading a warehouse filter
 * through.
 *
 * Auto-advance queue: after a bulk product upload there can be 20+ items
 * sitting here needing putaway, and reopening this panel from scratch for
 * every single one (find the row, click "Suggest Locations", pick, confirm,
 * scroll back to find the next row...) doesn't scale. So the moment
 * "Confirm Putaway for All Locations" succeeds for a product, this jumps
 * straight into fetching suggestions for whichever pending product was next
 * in the list at that moment, opening its grid automatically - turning a
 * bulk cleanup into a fast confirm -> confirm -> confirm queue instead of a
 * fresh open/suggest/pick/confirm cycle each time. It only ever advances
 * this way after a successful confirm; a manual "Suggest Locations" click on
 * any row still just opens that one row as before, and reaching the end of
 * the list (no next product) falls back to closing the panel like before.
 */
export default function NewProductsPanel() {
  const pending = useApi(() => optimizerApi.pendingPlacement(50), []);
  const [openProductId, setOpenProductId] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<any>(null);
  const [selectedByWarehouse, setSelectedByWarehouse] = useState<Record<number, number>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [busyAction, setBusyAction] = useState<"suggest" | "confirm" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const suggestFor = async (productId: number) => {
    setBusyId(productId);
    setBusyAction("suggest");
    setError(null);
    try {
      const res = await optimizerApi.suggest({ product_id: productId, top_n: 3 });
      setSuggestions(res);
      setOpenProductId(productId);
      // Pre-select the best-scoring candidate in every row by default -
      // the operator can still click a different card in any row to
      // override it, but the common case ("just take the top suggestion
      // everywhere") now takes one confirm click per product instead of
      // first hand-picking every row. Computed by explicitly comparing
      // fit_score per warehouse rather than trusting the API's own
      // ordering, so this stays correct even if suggest_locations' sort
      // order ever changes. This also applies to "Suggest Again": a fresh
      // set of candidates gets its own fresh best-pick defaults, so a
      // stale selection from the previous set is never silently carried
      // over and confirmed by accident.
      const bestByWarehouse: Record<number, number> = {};
      const bestScoreByWarehouse: Record<number, number> = {};
      for (const s of res.suggestions || []) {
        const prevScore = bestScoreByWarehouse[s.warehouse_id];
        if (prevScore == null || s.fit_score > prevScore) {
          bestScoreByWarehouse[s.warehouse_id] = s.fit_score;
          bestByWarehouse[s.warehouse_id] = s.location_id;
        }
      }
      setSelectedByWarehouse(bestByWarehouse);
    } catch (e: any) {
      setError(e?.message || "Could not get a suggestion.");
    } finally {
      setBusyId(null);
      setBusyAction(null);
    }
  };

  const closePanel = () => {
    setOpenProductId(null);
    setSuggestions(null);
    setSelectedByWarehouse({});
  };

  const confirmPutaway = async (productId: number, warehouseIds: number[]) => {
    const locationIds = warehouseIds.map((wid) => selectedByWarehouse[wid]);
    if (locationIds.some((lid) => lid == null)) return;
    setBusyId(productId);
    setBusyAction("confirm");
    try {
      await optimizerApi.markPlacedBulk(productId, locationIds);
      // Figure out what was next in the list BEFORE reloading (the reload
      // drops this product from pending.data, which would make "the next
      // item" ambiguous to compute afterwards).
      const currentList = pending.data || [];
      const currentIndex = currentList.findIndex((p: any) => p.product_id === productId);
      const nextProduct = currentIndex >= 0 ? currentList[currentIndex + 1] : undefined;
      pending.reload();
      if (nextProduct) {
        // Reuses the normal suggestFor path (same loading state, same error
        // handling) so a failed suggestion here behaves exactly like a
        // failed manual click - it surfaces the error banner rather than
        // silently breaking the queue.
        await suggestFor(nextProduct.product_id);
      } else {
        closePanel();
      }
    } catch (e: any) {
      setError(e?.message || "Could not update this product.");
    } finally {
      setBusyId(null);
      setBusyAction(null);
    }
  };

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>
          New Products Awaiting Placement
          {pending.data && pending.data.length > 0 && <span className="pending-badge" style={{ marginLeft: 8 }}>{pending.data.length}</span>}
        </h3>
      </div>
      {pending.loading && <LoadingState />}
      {pending.error && <ErrorState message={pending.error} onRetry={pending.reload} />}
      {pending.data && pending.data.length === 0 && (
        <p className="empty-state">Nothing waiting on placement - every catalogued product has a suggested slot.</p>
      )}
      {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
      {pending.data?.map((p: any) => {
        const isOpen = openProductId === p.product_id;
        let rows: { warehouseId: number; candidates: any[] }[] = [];
        if (isOpen && suggestions) {
          const byWarehouse = new Map<number, any[]>();
          for (const s of suggestions.suggestions) {
            if (!byWarehouse.has(s.warehouse_id)) byWarehouse.set(s.warehouse_id, []);
            byWarehouse.get(s.warehouse_id)!.push(s);
          }
          rows = Array.from(byWarehouse.entries())
            .sort((a, b) => a[0] - b[0])
            .map(([warehouseId, candidates]) => ({ warehouseId, candidates }));
        }
        const allRowsPicked = rows.length > 0 && rows.every((r) => selectedByWarehouse[r.warehouseId] != null);

        return (
          <div key={p.product_id} className="pending-item">
            <div style={{ flex: 1 }}>
              <div className="pending-item-name">{p.product_name}</div>
              <div className="pending-item-meta">
                {p.category} · {p.length_cm}×{p.width_cm}×{p.height_cm} cm · {p.weight_kg} kg · {p.storage_type}
              </div>
              {isOpen && suggestions && (
                <div style={{ marginTop: 8 }}>
                  {suggestions.message && <p className="empty-state">{suggestions.message}</p>}
                  <p className="empty-state" style={{ padding: "0 0 8px" }}>
                    The best-fit location per warehouse is already selected below - click a different
                    card in a row to override it, or confirm putaway for all of them at once.
                  </p>
                  <div className="putaway-grid">
                    {rows.map((row) => (
                      <div className="putaway-grid-row" key={row.warehouseId}>
                        <div className="putaway-grid-warehouse">{warehouseName(row.warehouseId)}</div>
                        {row.candidates.map((s: any) => {
                          const selected = selectedByWarehouse[row.warehouseId] === s.location_id;
                          return (
                            <div
                              className={`suggestion-card suggestion-card-selectable${selected ? " selected" : ""}`}
                              key={s.location_id}
                              role="button"
                              tabIndex={0}
                              aria-pressed={selected}
                              onClick={() =>
                                setSelectedByWarehouse((prev) => ({ ...prev, [row.warehouseId]: s.location_id }))
                              }
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setSelectedByWarehouse((prev) => ({ ...prev, [row.warehouseId]: s.location_id }));
                                }
                              }}
                            >
                              <div className="suggestion-header">
                                <span className="suggestion-select-indicator">
                                  {selected && <Icon name="checkCircle" size={15} />}
                                </span>
                                <span className="fit-score">{s.fit_score}% fit</span>
                              </div>
                              <div className="suggestion-sub">
                                {s.storage_type} - Location {s.location_code} / Tier {s.shelf_tier}
                              </div>
                              {s.reasons && (
                                <div className="reason-tags">
                                  {s.reasons.map((r: string, i: number) => (
                                    <span className="reason-tag" key={i}>
                                      {r}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    ))}
                  </div>
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 10 }}>
                    <button
                      className="btn-secondary btn-small"
                      onClick={() => suggestFor(p.product_id)}
                      disabled={busyId === p.product_id}
                      title="Fetch a fresh set of candidate locations for every warehouse"
                    >
                      {busyId === p.product_id && busyAction === "suggest" ? "Refreshing..." : "Suggest Again"}
                    </button>
                    <button className="btn-secondary btn-small" onClick={closePanel} disabled={busyId === p.product_id}>
                      Cancel
                    </button>
                    <button
                      className="btn-primary btn-small"
                      onClick={() => confirmPutaway(p.product_id, rows.map((r) => r.warehouseId))}
                      disabled={busyId === p.product_id || !allRowsPicked}
                    >
                      {busyId === p.product_id && busyAction === "confirm" ? "Saving..." : "Confirm Putaway for All Locations"}
                    </button>
                  </div>
                </div>
              )}
            </div>
            {!isOpen && (
              <button className="btn-secondary" onClick={() => suggestFor(p.product_id)} disabled={busyId === p.product_id}>
                {busyId === p.product_id ? "Scoring..." : "Suggest Locations"}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
