"use client";

import { useState } from "react";
import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import DataTable from "../../components/DataTable";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { insightsApi, optimizerApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";
import KeyInsightsCard from "../../components/KeyInsightsCard";
import PlacementAdvisor from "./PlacementAdvisor";
import LayoutHeatmap from "./LayoutHeatmap";
import LocationDetailModal from "./LocationDetailModal";
import NewProductsPanel from "./NewProductsPanel";
import ReorderSuggestionsPanel from "./ReorderSuggestionsPanel";
import TopMoversPanel from "./TopMoversPanel";
import MarginDensityPanel from "./MarginDensityPanel";

export default function StockOptimizerPage() {
  const { warehouseId, setWarehouseId } = useFilters();
  // Pre-filled when arriving from the global search bar's "jump to product"
  // link. Read directly from window.location rather than next/navigation's
  // useSearchParams so this page doesn't need a Suspense boundary just for
  // an optional deep link.
  const [search, setSearch] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("search") || "";
  });

  const tree = useApi(() => optimizerApi.tree(warehouseId), [warehouseId]);
  const products = useApi(() => optimizerApi.products(search || undefined, 12), [search]);
  const heatmap = useApi(() => optimizerApi.heatmap(warehouseId), [warehouseId]);
  const overstocked = useApi(() => optimizerApi.overstocked(90, warehouseId), [warehouseId]);
  const underutilized = useApi(() => optimizerApi.underutilized(25, warehouseId), [warehouseId]);
  const [selectedLocationId, setSelectedLocationId] = useState<number | null>(null);

  return (
    <AppLayout>
      <TopBar title="Stock Optimizer">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
      </TopBar>
      <div className="content-area">
        <NewProductsPanel />

        <KeyInsightsCard fetcher={() => insightsApi.storage(warehouseId)} deps={[warehouseId]} />

        <div className="grid-2" style={{ gridTemplateColumns: "1fr 2fr" }}>
          <div className="card">
            <div className="chart-card-header">
              <h3>Store Layout</h3>
            </div>
            {tree.loading && <LoadingState />}
            {tree.error && <ErrorState message={tree.error} onRetry={tree.reload} />}
            {tree.data && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {tree.data.map((g: any) => (
                  <div key={g.storage_type}>
                    <div style={{ fontWeight: 700, fontSize: 13.5, color: "var(--text-heading)" }}>
                      {g.storage_type.replace("_", " ")}{" "}
                      <span style={{ color: "var(--text-muted)", fontWeight: 500 }}>({g.location_count})</span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                      Avg. utilization: {g.avg_utilization_pct}%
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <div className="chart-card-header">
              <h3>Product Size Analyzer</h3>
              <input
                className="select-pill"
                placeholder="Search products..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{ minWidth: 200 }}
              />
            </div>
            {products.loading && <LoadingState />}
            {products.error && <ErrorState message={products.error} onRetry={products.reload} />}
            {products.data && (
              <DataTable
                keyField="product_id"
                rows={products.data}
                columns={[
                  { key: "product_name", header: "Product" },
                  {
                    key: "dims",
                    header: "Size (L×W×H cm)",
                    render: (r) => `${r.length_cm} × ${r.width_cm} × ${r.height_cm}`,
                  },
                  { key: "weight_kg", header: "Weight (kg)", align: "right" },
                  { key: "storage_type", header: "Storage Type" },
                  { key: "fragility", header: "Fragility" },
                  { key: "stackable", header: "Stackable", render: (r) => (r.stackable ? "Yes" : "No") },
                ]}
              />
            )}
          </div>
        </div>

        <div className="grid-2">
          <div className="card">
            <div className="chart-card-header">
              <h3>Store Layout Heatmap</h3>
            </div>
            {heatmap.loading && <LoadingState />}
            {heatmap.error && <ErrorState message={heatmap.error} onRetry={heatmap.reload} />}
            {heatmap.data && <LayoutHeatmap data={heatmap.data} onCellClick={setSelectedLocationId} />}
          </div>

          <div className="card card-fixed-height" style={{ height: 560 }}>
            <div className="chart-card-header">
              <h3>Smart Placement Advisor</h3>
            </div>
            <div className="card-scroll-body">
              <PlacementAdvisor />
            </div>
          </div>
        </div>

        <ReorderSuggestionsPanel warehouseId={warehouseId} />

        <div className="grid-2">
          <TopMoversPanel warehouseId={warehouseId} />
          <MarginDensityPanel />
        </div>

        <div className="grid-2">
          <div className="card">
            <div className="chart-card-header">
              <h3>Overstocked Locations (&gt;90%)</h3>
            </div>
            {overstocked.loading && <LoadingState />}
            {overstocked.error && <ErrorState message={overstocked.error} onRetry={overstocked.reload} />}
            {overstocked.data && (
              <DataTable
                keyField="location_id"
                rows={overstocked.data}
                pageSize={10}
                emptyMessage="No overstocked locations."
                onRowClick={(r) => setSelectedLocationId(r.location_id)}
                activeRowKey={selectedLocationId ?? undefined}
                columns={[
                  { key: "location_code", header: "Location" },
                  { key: "storage_type", header: "Type" },
                  { key: "shelf_tier", header: "Tier", align: "right" },
                  { key: "utilization_pct", header: "Utilization", align: "right", render: (r) => `${r.utilization_pct}%` },
                ]}
              />
            )}
          </div>

          <div className="card">
            <div className="chart-card-header">
              <h3>Underutilized Locations (&lt;25%)</h3>
            </div>
            {underutilized.loading && <LoadingState />}
            {underutilized.error && <ErrorState message={underutilized.error} onRetry={underutilized.reload} />}
            {underutilized.data && (
              <DataTable
                keyField="location_id"
                rows={underutilized.data}
                pageSize={10}
                emptyMessage="No underutilized locations."
                onRowClick={(r) => setSelectedLocationId(r.location_id)}
                activeRowKey={selectedLocationId ?? undefined}
                columns={[
                  { key: "location_code", header: "Location" },
                  { key: "storage_type", header: "Type" },
                  { key: "shelf_tier", header: "Tier", align: "right" },
                  { key: "utilization_pct", header: "Utilization", align: "right", render: (r) => `${r.utilization_pct}%` },
                ]}
              />
            )}
          </div>
        </div>
      </div>

      <LocationDetailModal locationId={selectedLocationId} onClose={() => setSelectedLocationId(null)} />
    </AppLayout>
  );
}
