"use client";

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
import StackedAreaTrend from "../../components/charts/StackedAreaTrend";
import DonutChart from "../../components/charts/DonutChart";
import { insightsApi, stockApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";
import { stockStatusColor } from "../../lib/theme";
import { formatDelta } from "../../lib/format";
import DeadStockPanel from "./DeadStockPanel";
import RebalancingSuggestionsPanel from "./RebalancingSuggestionsPanel";
import KeyInsightsCard from "../../components/KeyInsightsCard";

const money = (v: number) => `€${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function StockSummaryPage() {
  const { warehouseId, setWarehouseId, range, setRange, hydrated } = useFilters();

  const summary = useApi(() => stockApi.summary(warehouseId, range), [warehouseId, range]);
  const alerts = useApi(() => stockApi.alerts(warehouseId, range), [warehouseId, range]);
  const trend = useApi(() => stockApi.trend(31, warehouseId, range), [warehouseId, range]);
  const distribution = useApi(() => stockApi.distribution(warehouseId, range), [warehouseId, range]);
  const lowStock = useApi(() => stockApi.lowStock(8, warehouseId, range), [warehouseId, range]);

  return (
    <AppLayout>
      <TopBar title="Stock Summary">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
        <DateRangeFilter value={range} hydrated={hydrated} onChange={setRange} />
      </TopBar>
      <div className="content-area">
        {summary.loading && <SkeletonKpiRow />}
        {summary.error && <ErrorState message={summary.error} onRetry={summary.reload} />}
        {summary.data && (() => {
          const d = summary.data.comparison?.deltas || {};
          const stockoutDelta = formatDelta(d.stockout_pct, { higherIsBetter: false, isPercentagePoints: true });
          const healthyDelta = formatDelta(d.healthy_count, { higherIsBetter: true });
          const riskDelta = formatDelta(d.inventory_at_risk_value, { higherIsBetter: false, isCurrency: true });
          return (
            <div className="kpi-row">
              <KpiCard icon="package" label="Total Products" value={String(summary.data.total_products)} />
              <KpiCard
                icon="alertTriangle"
                label="Stockout %"
                value={`${summary.data.stockout_pct}%`}
                accent="#ec835a"
                delta={stockoutDelta?.text}
                deltaGood={stockoutDelta?.good}
              />
              <KpiCard
                icon="checkCircle"
                label="Healthy Stock"
                value={String(summary.data.healthy_count)}
                accent="#0ca30c"
                delta={healthyDelta?.text}
                deltaGood={healthyDelta?.good}
              />
              <KpiCard
                icon="coins"
                label="Inventory at Risk"
                value={money(summary.data.inventory_at_risk_value)}
                accent="#d03b3b"
                delta={riskDelta?.text}
                deltaGood={riskDelta?.good}
              />
            </div>
          );
        })()}

        <KeyInsightsCard fetcher={() => insightsApi.stock(warehouseId, range)} deps={[warehouseId, range]} />

        <div className="grid-2">
          <ChartCard title="Stock Health Overview (last 31 days)">
            {trend.loading && <SkeletonChart />}
            {trend.error && <ErrorState message={trend.error} onRetry={trend.reload} />}
            {trend.data && (
              <StackedAreaTrend
                data={trend.data}
                xKey="date_id"
                series={[
                  { key: "healthy", label: "Healthy" },
                  { key: "low", label: "Low Stock" },
                  { key: "overstock", label: "Overstock" },
                  { key: "critical", label: "Critical" },
                ]}
              />
            )}
          </ChartCard>

          <div className="card">
            <div className="chart-card-header">
              <h3>Alerts Panel</h3>
            </div>
            {alerts.loading && <LoadingState />}
            {alerts.error && <ErrorState message={alerts.error} onRetry={alerts.reload} />}
            {alerts.data && alerts.data.length === 0 && <p className="empty-state">No active alerts.</p>}
            {alerts.data?.map((a: any, i: number) => (
              <div className="alert-item" key={i}>
                <span
                  className="alert-icon"
                  style={
                    a.level === "critical"
                      ? { color: "var(--status-critical)", background: "rgba(208, 59, 59, 0.12)" }
                      : { color: "#eb6834", background: "rgba(235, 104, 52, 0.12)" }
                  }
                >
                  <Icon name={a.level === "critical" ? "alertOctagon" : "alertTriangle"} size={15} />
                </span>
                <div>
                  <div className="alert-title">{a.title}</div>
                  <div className="alert-detail">{a.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid-2">
          <div className="card">
            <div className="chart-card-header">
              <h3>Low Stock Products</h3>
            </div>
            {lowStock.loading && <LoadingState />}
            {lowStock.error && <ErrorState message={lowStock.error} onRetry={lowStock.reload} />}
            {lowStock.data && (
              <DataTable
                keyField="product_name"
                rows={lowStock.data}
                emptyMessage="Nothing is low or critical right now."
                columns={[
                  { key: "product_name", header: "Product" },
                  { key: "warehouse_id", header: "Warehouse", align: "center" },
                  {
                    key: "stock_status",
                    header: "Status",
                    render: (r) => <StatusPill status={r.stock_status} />,
                  },
                  { key: "stock_on_hand", header: "Stock on Hand", align: "right" },
                  {
                    key: "days_of_stock_left",
                    header: "Days of Stock Left",
                    align: "right",
                    render: (r) => (r.days_of_stock_left != null ? r.days_of_stock_left : "—"),
                  },
                ]}
              />
            )}
          </div>

          <ChartCard title="Inventory Distribution">
            {distribution.loading && <SkeletonChart />}
            {distribution.error && <ErrorState message={distribution.error} onRetry={distribution.reload} />}
            {distribution.data && (
              <DonutChart
                data={distribution.data}
                nameKey="stock_status"
                valueKey="count"
                colors={distribution.data.map((d: any) => stockStatusColor[d.stock_status] || "#2a78d6")}
              />
            )}
          </ChartCard>
        </div>

        <div className="grid-2">
          <DeadStockPanel warehouseId={warehouseId} />
          <RebalancingSuggestionsPanel warehouseId={warehouseId} />
        </div>
      </div>
    </AppLayout>
  );
}
