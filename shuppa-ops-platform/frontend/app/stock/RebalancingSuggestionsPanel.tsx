"use client";

import DataTable from "../../components/DataTable";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { WAREHOUSES, stockApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";

const warehouseName = (id: number) => WAREHOUSES.find((w) => w.id === id)?.name || `Warehouse ${id}`;

/**
 * Cross-warehouse transfer suggestions: a product that's LOW/CRITICAL in one
 * warehouse while another warehouse is carrying a comfortable surplus of the
 * same product right now. Suggestion only - nothing here moves stock. See
 * backend/app/services/stock_service.py:get_rebalancing_suggestions.
 */
export default function RebalancingSuggestionsPanel({ warehouseId }: { warehouseId?: number }) {
  const rebalancing = useApi(() => stockApi.rebalancingSuggestions(50, warehouseId), [warehouseId]);

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Multi-Warehouse Rebalancing</h3>
      </div>
      <p className="empty-state" style={{ padding: "0 0 8px" }}>
        Products that are low/critical in one warehouse while another warehouse has a comfortable surplus - a
        transfer between warehouses could resolve this faster than a new purchase order. Suggestion only; nothing
        here moves stock automatically.
      </p>
      {rebalancing.loading && <LoadingState />}
      {rebalancing.error && <ErrorState message={rebalancing.error} onRetry={rebalancing.reload} />}
      {rebalancing.data && (
        <DataTable
          keyField="__row"
          rows={rebalancing.data.map((r: any, i: number) => ({ ...r, __row: i }))}
          csvFilename="rebalancing-suggestions"
          pageSize={10}
          emptyMessage="No cross-warehouse rebalancing opportunities right now."
          columns={[
            { key: "product_name", header: "Product" },
            {
              key: "short_warehouse_id",
              header: "Short In",
              render: (r) => `${warehouseName(r.short_warehouse_id)} (${r.short_stock_status})`,
            },
            { key: "short_stock_on_hand", header: "Stock On Hand", align: "right" },
            {
              key: "surplus_warehouse_id",
              header: "Surplus At",
              render: (r) => `${warehouseName(r.surplus_warehouse_id)} (${r.surplus_stock_on_hand} on hand)`,
            },
            { key: "suggested_transfer_qty", header: "Suggested Transfer Qty", align: "right" },
          ]}
        />
      )}
    </div>
  );
}
