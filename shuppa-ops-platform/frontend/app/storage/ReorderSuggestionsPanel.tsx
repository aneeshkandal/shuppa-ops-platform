"use client";

import { useState } from "react";
import DataTable from "../../components/DataTable";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { stockApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";

/**
 * Auto-suggested reorder quantity + best historical supplier for every
 * LOW/CRITICAL product line, backed by GET /stock/reorder-suggestions (see
 * backend/app/services/stock_service.py:get_reorder_suggestions). Lives on
 * the Stock Optimizer page since it's about acting on the current stock
 * picture, not just viewing it. Each row can also be turned into a Draft PO
 * (dim_draft_purchase_orders) with one click - a record of intent only,
 * it doesn't place a real order with a supplier.
 */
export default function ReorderSuggestionsPanel({ warehouseId }: { warehouseId?: number }) {
  const reorder = useApi(() => stockApi.reorderSuggestions(50, warehouseId), [warehouseId]);
  const [drafting, setDrafting] = useState<number | null>(null);
  const [drafted, setDrafted] = useState<Record<number, boolean>>({});
  const [draftError, setDraftError] = useState<Record<number, string>>({});

  const draftPo = async (r: any) => {
    setDrafting(r.product_id);
    setDraftError((e) => ({ ...e, [r.product_id]: "" }));
    try {
      await stockApi.draftPo({
        product_id: r.product_id,
        supplier_id: r.best_supplier?.supplier_id,
        warehouse_id: r.warehouse_id,
        quantity: r.suggested_reorder_qty,
      });
      setDrafted((d) => ({ ...d, [r.product_id]: true }));
    } catch (e: any) {
      setDraftError((err) => ({ ...err, [r.product_id]: e?.message || "Could not draft PO." }));
    } finally {
      setDrafting(null);
    }
  };

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Reorder Suggestions</h3>
      </div>
      <p className="empty-state" style={{ padding: "0 0 8px" }}>
        Suggested quantity replenishes each product to its target days-of-stock based on recent sales velocity
        (falls back to a rough 2× reorder-point estimate, flagged below, for products with no recent sales).
        "Draft PO" records intent only - it doesn't place a real order with a supplier.
      </p>
      {reorder.loading && <LoadingState />}
      {reorder.error && <ErrorState message={reorder.error} onRetry={reorder.reload} />}
      {reorder.data && (
        <DataTable
          keyField="product_id"
          rows={reorder.data}
          pageSize={10}
          csvFilename="reorder-suggestions"
          emptyMessage="Nothing needs reordering right now - no LOW/CRITICAL stock lines."
          columns={[
            { key: "product_name", header: "Product" },
            { key: "warehouse_id", header: "Warehouse", align: "center" },
            { key: "stock_on_hand", header: "On Hand", align: "right" },
            {
              key: "suggested_reorder_qty",
              header: "Suggested Qty",
              align: "right",
              render: (r) => (
                <span>
                  {r.suggested_reorder_qty}
                  {r.is_estimate && (
                    <span style={{ color: "var(--text-muted)", fontSize: 11 }}> (rough estimate)</span>
                  )}
                </span>
              ),
            },
            {
              key: "best_supplier",
              header: "Best Supplier",
              render: (r) =>
                r.best_supplier ? (
                  <span>
                    {r.best_supplier.supplier_name}{" "}
                    <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
                      ({r.best_supplier.on_time_delivery_pct}% on-time, {r.best_supplier.orders_completed} orders)
                    </span>
                  </span>
                ) : (
                  <span style={{ color: "var(--text-muted)" }}>{r.best_supplier_note}</span>
                ),
            },
            {
              key: "draft_po",
              header: "",
              sortable: false,
              render: (r) =>
                drafted[r.product_id] ? (
                  <span style={{ color: "var(--status-good)", fontSize: 12.5, fontWeight: 700 }}>Draft PO created</span>
                ) : (
                  <div>
                    <button
                      className="btn-secondary btn-small"
                      type="button"
                      disabled={drafting === r.product_id}
                      onClick={() => draftPo(r)}
                    >
                      {drafting === r.product_id ? "Drafting..." : "Draft PO"}
                    </button>
                    {draftError[r.product_id] && (
                      <div style={{ color: "var(--status-critical)", fontSize: 11, marginTop: 4 }}>{draftError[r.product_id]}</div>
                    )}
                  </div>
                ),
            },
          ]}
        />
      )}
    </div>
  );
}
