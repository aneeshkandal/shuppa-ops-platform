"use client";

import { useState } from "react";
import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import DateRangeFilter from "../../components/DateRangeFilter";
import KpiCard from "../../components/KpiCard";
import ChartCard from "../../components/ChartCard";
import DataTable from "../../components/DataTable";
import StatusPill from "../../components/StatusPill";
import Icon from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { SkeletonChart, SkeletonKpiRow } from "../../components/Skeleton";
import TrendLine from "../../components/charts/TrendLine";
import DonutChart from "../../components/charts/DonutChart";
import { insightsApi, supplierApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";
import { riskLevelColor } from "../../lib/theme";
import { formatDelta } from "../../lib/format";
import KeyInsightsCard from "../../components/KeyInsightsCard";
import SupplierReturnsCard from "./SupplierReturnsCard";

const money = (v: number) => `€${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function SupplierSummaryPage() {
  const { warehouseId, setWarehouseId, range, setRange, hydrated } = useFilters();

  // Pre-filled when arriving from the global search bar's "jump to supplier"
  // link. Read directly from window.location (rather than
  // next/navigation's useSearchParams) so this page doesn't need a Suspense
  // boundary just for an optional deep link.
  const [selectedSupplier, setSelectedSupplier] = useState<{ id: number; name: string } | undefined>(() => {
    if (typeof window === "undefined") return undefined;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("supplier_id");
    const name = params.get("supplier_name");
    return id ? { id: Number(id), name: name || `Supplier #${id}` } : undefined;
  });

  const kpis = useApi(() => supplierApi.kpis(warehouseId, range), [warehouseId, range]);
  const performance = useApi(() => supplierApi.performance(warehouseId, range), [warehouseId, range]);
  const trend = useApi(() => supplierApi.trend(warehouseId, range), [warehouseId, range]);
  const riskDist = useApi(() => supplierApi.riskDistribution(warehouseId, range), [warehouseId, range]);
  const topByValue = useApi(() => supplierApi.topByValue(5, warehouseId, range), [warehouseId, range]);
  const recentLate = useApi(
    () => supplierApi.recentLate(selectedSupplier ? 50 : 6, warehouseId, range, selectedSupplier?.id),
    [warehouseId, range, selectedSupplier]
  );

  return (
    <AppLayout>
      <TopBar title="Supplier Summary">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
        <DateRangeFilter value={range} hydrated={hydrated} onChange={setRange} />
      </TopBar>
      <div className="content-area">
        {kpis.loading && <SkeletonKpiRow />}
        {kpis.error && <ErrorState message={kpis.error} onRetry={kpis.reload} />}
        {kpis.data && (() => {
          const d = kpis.data.comparison?.deltas || {};
          const onTimeDelta = formatDelta(d.on_time_delivery_pct, { higherIsBetter: true, isPercentagePoints: true });
          const lateDelta = formatDelta(d.late_delivery_pct, { higherIsBetter: false, isPercentagePoints: true });
          const ordersDelta = formatDelta(d.total_orders, { higherIsBetter: true });
          const valueDelta = formatDelta(d.total_order_value, { higherIsBetter: true, isCurrency: true });
          return (
            <div className="kpi-row">
              <KpiCard
                icon="truck"
                label="On-Time Delivery %"
                value={`${kpis.data.on_time_delivery_pct}%`}
                accent="#0ca30c"
                delta={onTimeDelta?.text}
                deltaGood={onTimeDelta?.good}
              />
              <KpiCard
                icon="clock"
                label="Late Delivery %"
                value={`${kpis.data.late_delivery_pct}%`}
                accent="#d03b3b"
                delta={lateDelta?.text}
                deltaGood={lateDelta?.good}
              />
              <KpiCard
                icon="clipboardList"
                label="Total Orders"
                value={Number(kpis.data.total_orders).toLocaleString()}
                delta={ordersDelta?.text}
                deltaGood={ordersDelta?.good}
              />
              <KpiCard
                icon="coins"
                label="Order Value"
                value={money(kpis.data.total_order_value)}
                delta={valueDelta?.text}
                deltaGood={valueDelta?.good}
              />
            </div>
          );
        })()}

        <KeyInsightsCard fetcher={() => insightsApi.supplier(warehouseId, range)} deps={[warehouseId, range]} />

        <div className="grid-2">
          <div className="card">
            <div className="chart-card-header">
              <h3>Supplier Performance</h3>
            </div>
            {performance.loading && <LoadingState />}
            {performance.error && <ErrorState message={performance.error} onRetry={performance.reload} />}
            {performance.data && (
              <>
                <p className="empty-state" style={{ padding: "0 0 8px" }}>
                  Click a supplier to filter its late deliveries on the right.
                </p>
                <DataTable
                  keyField="supplier_id"
                  rows={performance.data}
                  pageSize={10}
                  csvFilename="supplier-performance"
                  onRowClick={(r) => setSelectedSupplier({ id: r.supplier_id, name: r.supplier_name })}
                  activeRowKey={selectedSupplier?.id}
                  columns={[
                    { key: "supplier_name", header: "Supplier" },
                    { key: "on_time_delivery_pct", header: "On-Time %", align: "right", render: (r) => `${r.on_time_delivery_pct}%` },
                    { key: "late_delivery_pct", header: "Late %", align: "right", render: (r) => `${r.late_delivery_pct}%` },
                    { key: "orders_completed", header: "Orders", align: "right" },
                    { key: "order_value", header: "Order Value", align: "right", render: (r) => money(r.order_value) },
                    { key: "risk_level", header: "Reliability", render: (r) => <StatusPill status={r.risk_level} /> },
                  ]}
                />
              </>
            )}
          </div>

          <div className="card">
            <div className="chart-card-header">
              <h3>
                {selectedSupplier ? `Late Deliveries – ${selectedSupplier.name}` : "Recent Late Deliveries"}
              </h3>
              {selectedSupplier && (
                <button className="btn-secondary btn-small" onClick={() => setSelectedSupplier(undefined)} type="button">
                  Clear filter
                </button>
              )}
            </div>
            {recentLate.loading && <LoadingState />}
            {recentLate.error && <ErrorState message={recentLate.error} onRetry={recentLate.reload} />}
            {recentLate.data && (
              <DataTable
                keyField="po_id"
                rows={recentLate.data}
                pageSize={selectedSupplier ? 10 : undefined}
                csvFilename={selectedSupplier ? `late-deliveries-${selectedSupplier.name}` : undefined}
                emptyMessage="No late deliveries recorded."
                columns={[
                  { key: "po_id", header: "PO" },
                  { key: "supplier_name", header: "Supplier" },
                  { key: "warehouse_name", header: "Warehouse" },
                  { key: "delay_days", header: "Days Late", align: "right" },
                ]}
              />
            )}
          </div>
        </div>

        <SupplierReturnsCard warehouseId={warehouseId} />

        <div className="grid-3">
          <ChartCard title="On-Time Delivery Rate (by month)">
            {trend.loading && <SkeletonChart />}
            {trend.error && <ErrorState message={trend.error} onRetry={trend.reload} />}
            {trend.data && (
              <TrendLine data={trend.data} xKey="month" yKey="on_time_pct" valueFormatter={(v) => `${v}%`} />
            )}
          </ChartCard>

          <ChartCard title="Supplier Risk Distribution">
            {riskDist.loading && <SkeletonChart />}
            {riskDist.error && <ErrorState message={riskDist.error} onRetry={riskDist.reload} />}
            {riskDist.data && (
              <DonutChart
                data={riskDist.data}
                nameKey="risk_level"
                valueKey="supplier_count"
                colors={riskDist.data.map((d: any) => riskLevelColor[d.risk_level] || "#2a78d6")}
              />
            )}
          </ChartCard>

          <div className="card">
            <div className="chart-card-header">
              <h3>Top Suppliers by Order Value</h3>
            </div>
            {topByValue.loading && <LoadingState />}
            {topByValue.error && <ErrorState message={topByValue.error} onRetry={topByValue.reload} />}
            {topByValue.data && (
              <DataTable
                keyField="supplier_id"
                rows={topByValue.data}
                columns={[
                  { key: "supplier_name", header: "Supplier" },
                  { key: "order_value", header: "Order Value", align: "right", render: (r) => money(r.order_value) },
                ]}
              />
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
