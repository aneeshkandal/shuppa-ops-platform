"use client";

import DataTable from "../../components/DataTable";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { stockApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";

const money = (v: number) => `€${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

/**
 * Dead stock / cash-tied-up report: products carrying stock value but with
 * zero sales over the trailing dead_stock_days_threshold days (Admin ->
 * Settings, default 60) - money and shelf space sitting idle. See
 * backend/app/services/stock_service.py:get_dead_stock.
 */
export default function DeadStockPanel({ warehouseId }: { warehouseId?: number }) {
  const deadStock = useApi(() => stockApi.deadStock(50, warehouseId), [warehouseId]);
  const days = deadStock.data?.dead_stock_days_threshold ?? 60;

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Dead Stock - Cash Tied Up</h3>
        {deadStock.data && deadStock.data.items.length > 0 && (
          <span className="status-pill" style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}>
            {money(deadStock.data.total_value_tied_up)} tied up
          </span>
        )}
      </div>
      <p className="empty-state" style={{ padding: "0 0 8px" }}>
        Products with stock on hand but zero units sold in the trailing {days} days - inventory value and shelf
        space sitting idle rather than a stockout risk.
      </p>
      {deadStock.loading && <LoadingState />}
      {deadStock.error && <ErrorState message={deadStock.error} onRetry={deadStock.reload} />}
      {deadStock.data && (
        <DataTable
          keyField="__row"
          rows={deadStock.data.items.map((r: any, i: number) => ({ ...r, __row: `${r.product_id}-${r.warehouse_id}-${i}` }))}
          csvFilename="dead-stock"
          pageSize={10}
          emptyMessage="No dead stock right now - everything with stock on hand has sold at least one unit recently."
          columns={[
            { key: "product_name", header: "Product" },
            { key: "category", header: "Category" },
            { key: "warehouse_id", header: "Warehouse", align: "center" },
            { key: "stock_on_hand", header: "Stock on Hand", align: "right" },
            { key: "stock_value", header: "Value Tied Up", align: "right", render: (r) => money(r.stock_value) },
          ]}
        />
      )}
    </div>
  );
}
