"use client";

import DataTable from "../../components/DataTable";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { stockApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";

const money = (v: number) => `€${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

/**
 * Profit per cm3 of a product's own volume - flags bulky, low-margin
 * products occupying a lot of space for little return, versus compact,
 * high-margin ones. This is a product-level density score, NOT a literal
 * per-shelf-slot figure (this app has no product-to-slot assignment table
 * to know which exact slot holds which product). Sorted worst-first since
 * that's the actionable end of the list. See
 * backend/app/services/stock_service.py:get_margin_density.
 */
export default function MarginDensityPanel() {
  const density = useApi(() => stockApi.marginDensity(15), []);

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Space Efficiency - Profit per cm³</h3>
      </div>
      <p className="empty-state" style={{ padding: "0 0 8px" }}>
        Gross profit divided by each product's own volume - a bulky, low-margin item near the top of this list is
        using a lot of space for little return. This is a per-product density score, not a per-shelf-slot figure
        (the app doesn't track which exact slot a product sits in).
      </p>
      {density.loading && <LoadingState />}
      {density.error && <ErrorState message={density.error} onRetry={density.reload} />}
      {density.data && (
        <DataTable
          keyField="product_id"
          rows={density.data}
          csvFilename="margin-density"
          pageSize={10}
          columns={[
            { key: "product_name", header: "Product" },
            { key: "category", header: "Category" },
            {
              key: "dims",
              header: "Size (L×W×H cm)",
              render: (r) => `${r.length_cm} × ${r.width_cm} × ${r.height_cm}`,
            },
            { key: "gross_profit", header: "Gross Profit", align: "right", render: (r) => money(r.gross_profit) },
            {
              key: "margin_per_cm3",
              header: "Profit / cm³",
              align: "right",
              render: (r) => `€${Number(r.margin_per_cm3).toFixed(4)}`,
            },
          ]}
        />
      )}
    </div>
  );
}
