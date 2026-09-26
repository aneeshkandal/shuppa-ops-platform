"use client";

import { useState } from "react";
import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import DateRangeFilter from "../../components/DateRangeFilter";
import CustomDropdown from "../../components/CustomDropdown";
import KpiCard from "../../components/KpiCard";
import ChartCard from "../../components/ChartCard";
import DataTable from "../../components/DataTable";
import Icon from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { SkeletonChart, SkeletonKpiRow } from "../../components/Skeleton";
import TrendLine from "../../components/charts/TrendLine";
import DonutChart from "../../components/charts/DonutChart";
import RankedBars from "../../components/charts/RankedBars";
import ForecastTrend from "../../components/charts/ForecastTrend";
import { insightsApi, salesApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";
import { categorical, formatHourLabel } from "../../lib/theme";
import { formatDelta } from "../../lib/format";
import CorrelatedProductsPanel from "./CorrelatedProductsPanel";
import KeyInsightsCard from "../../components/KeyInsightsCard";

const money = (v: number) => `€${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function SalesAnalyticsPage() {
  const { warehouseId, setWarehouseId, range, setRange, hydrated } = useFilters();
  const [forecastCategory, setForecastCategory] = useState<string>("");

  const kpis = useApi(() => salesApi.kpis(warehouseId, range), [warehouseId, range]);
  const trend = useApi(() => salesApi.trend("day", 31, warehouseId, range), [warehouseId, range]);
  const topProducts = useApi(() => salesApi.topProducts(6, warehouseId, range), [warehouseId, range]);
  const byCategory = useApi(() => salesApi.byCategory(warehouseId, range), [warehouseId, range]);
  const byWarehouse = useApi(() => salesApi.byWarehouse(range), [range]);
  const avgOrderValue = useApi(() => salesApi.avgOrderValue(warehouseId, range), [warehouseId, range]);
  const orderTrend = useApi(() => salesApi.orderTrend("day", 31, warehouseId, range), [warehouseId, range]);
  const orderTime = useApi(() => salesApi.orderTimeDistribution(warehouseId, range), [warehouseId, range]);
  const customerGrowth = useApi(() => salesApi.customerGrowth(90, warehouseId, range), [warehouseId, range]);
  const deliveryPerformance = useApi(() => salesApi.deliveryPerformance(31, warehouseId, range), [warehouseId, range]);
  const returnCancellation = useApi(() => salesApi.returnCancellation(31, warehouseId, range), [warehouseId, range]);
  const categories = useApi(() => salesApi.categories(), []);
  const forecast = useApi(
    () => salesApi.forecast(7, 30, warehouseId, range, forecastCategory || undefined),
    [warehouseId, range, forecastCategory]
  );

  return (
    <AppLayout>
      <TopBar title="Sales Analytics">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
        <DateRangeFilter value={range} hydrated={hydrated} onChange={setRange} />
      </TopBar>
      <div className="content-area">
        {kpis.loading && <SkeletonKpiRow />}
        {kpis.error && <ErrorState message={kpis.error} onRetry={kpis.reload} />}
        {kpis.data && (() => {
          const d = kpis.data.comparison?.deltas || {};
          const revenueDelta = formatDelta(d.total_revenue, { higherIsBetter: true, isCurrency: true });
          const unitsDelta = formatDelta(d.total_units_sold, { higherIsBetter: true });
          const profitDelta = formatDelta(d.total_profit, { higherIsBetter: true, isCurrency: true });
          return (
            <div className="kpi-row">
              <KpiCard
                icon="coins"
                label="Total Revenue"
                value={money(kpis.data.total_revenue)}
                delta={revenueDelta?.text}
                deltaGood={revenueDelta?.good}
              />
              <KpiCard
                icon="package"
                label="Total Units Sold"
                value={Number(kpis.data.total_units_sold).toLocaleString()}
                delta={unitsDelta?.text}
                deltaGood={unitsDelta?.good}
              />
              <KpiCard
                icon="trendingUp"
                label="Total Profit"
                value={money(kpis.data.total_profit)}
                accent="#0ca30c"
                delta={profitDelta?.text}
                deltaGood={profitDelta?.good}
              />
              <KpiCard
                icon="award"
                label="Top Product"
                value={kpis.data.top_product_name || "—"}
                delta={kpis.data.top_product_units ? `${Number(kpis.data.top_product_units).toLocaleString()} units` : undefined}
                deltaGood
              />
            </div>
          );
        })()}

        <KeyInsightsCard fetcher={() => insightsApi.sales(warehouseId, range)} deps={[warehouseId, range]} />

        <div className="grid-2">
          <ChartCard title="Sales Performance - Revenue (last 31 days)">
            {trend.loading && <SkeletonChart />}
            {trend.error && <ErrorState message={trend.error} onRetry={trend.reload} />}
            {trend.data && (
              <TrendLine data={trend.data} xKey="bucket" yKey="revenue" color={categorical.magenta} valueFormatter={money} />
            )}
          </ChartCard>

          <div className="card">
            <div className="chart-card-header">
              <h3>Top Revenue Products</h3>
            </div>
            {topProducts.loading && <LoadingState />}
            {topProducts.error && <ErrorState message={topProducts.error} onRetry={topProducts.reload} />}
            {topProducts.data && (
              <DataTable
                keyField="product_name"
                rows={topProducts.data}
                columns={[
                  { key: "product_name", header: "Product" },
                  { key: "revenue", header: "Revenue", align: "right", render: (r) => money(r.revenue) },
                  { key: "units_sold", header: "Units Sold", align: "right" },
                ]}
              />
            )}
          </div>
        </div>

        <div className="grid-2">
          <ChartCard title="Order Volume Trend (last 31 days)">
            {orderTrend.loading && <SkeletonChart />}
            {orderTrend.error && <ErrorState message={orderTrend.error} onRetry={orderTrend.reload} />}
            {orderTrend.data && (
              <TrendLine
                data={orderTrend.data}
                xKey="bucket"
                yKey="order_count"
                color={categorical.aqua}
                valueFormatter={(v) => Number(v).toLocaleString()}
              />
            )}
            <p className="empty-state" style={{ padding: "8px 0 0" }}>
              Order counts are an estimate - the source data has no order_id, so this derives a plausible order
              count from real daily units sold (see the Avg. Order Value card for the assumption used).
            </p>
          </ChartCard>

          <ChartCard title="Peak Order Time">
            {orderTime.loading && <SkeletonChart />}
            {orderTime.error && <ErrorState message={orderTime.error} onRetry={orderTime.reload} />}
            {orderTime.data && (
              <TrendLine
                data={orderTime.data.map((d: any) => ({ ...d, hour_label: formatHourLabel(d.hour_of_day) }))}
                xKey="hour_label"
                yKey="order_count"
                color={categorical.magenta}
                valueFormatter={(v) => Number(v).toLocaleString()}
              />
            )}
            <p className="empty-state" style={{ padding: "8px 0 0" }}>
              A generic quick-delivery demand curve (lunch and dinner peaks) applied evenly across every day - not
              measured from real order timestamps, since none exist in the source data.
            </p>
          </ChartCard>
        </div>

        <div className="card">
          <div className="chart-card-header">
            <h3>
              Revenue Forecast (next 7 days){forecastCategory ? ` – ${forecastCategory}` : ""}
            </h3>
            <CustomDropdown
              variant="pill"
              ariaLabel="Scope forecast to a category"
              value={forecastCategory}
              onChange={setForecastCategory}
              options={[{ value: "", label: "All categories" }, ...(categories.data || []).map((c) => ({ value: c, label: c }))]}
            />
          </div>
          <p className="empty-state" style={{ padding: "0 0 8px" }}>
            A simple straight-line projection from the trailing 30 days - not seasonality-aware, so treat it as a
            directional signal rather than a precise demand plan.
          </p>
          {forecast.loading && <LoadingState />}
          {forecast.error && <ErrorState message={forecast.error} onRetry={forecast.reload} />}
          {forecast.data && (
            <ForecastTrend history={forecast.data.history} forecast={forecast.data.forecast} valueFormatter={money} />
          )}
          {forecast.data?.note && <p className="empty-state">{forecast.data.note}</p>}
        </div>

        <div className="grid-3">
          <ChartCard title="Revenue by Category">
            {byCategory.loading && <SkeletonChart />}
            {byCategory.error && <ErrorState message={byCategory.error} onRetry={byCategory.reload} />}
            {byCategory.data && <DonutChart data={byCategory.data} nameKey="category" valueKey="revenue" />}
          </ChartCard>

          <div className="card" style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
            <div className="chart-card-header" style={{ alignSelf: "flex-start" }}>
              <h3>Avg. Order Value</h3>
            </div>
            {avgOrderValue.loading && <LoadingState />}
            {avgOrderValue.error && <ErrorState message={avgOrderValue.error} onRetry={avgOrderValue.reload} />}
            {avgOrderValue.data && (
              <>
                <div className="kpi-value" style={{ fontSize: 40, padding: "24px 0 4px" }}>
                  {avgOrderValue.data.avg_order_value != null ? money(avgOrderValue.data.avg_order_value) : "—"}
                </div>
                <p className="empty-state" style={{ padding: 0 }}>
                  ~{Number(avgOrderValue.data.total_orders).toLocaleString()} estimated orders this period
                </p>
              </>
            )}
          </div>

          <ChartCard title="Sales by Warehouse">
            {byWarehouse.loading && <SkeletonChart />}
            {byWarehouse.error && <ErrorState message={byWarehouse.error} onRetry={byWarehouse.reload} />}
            {byWarehouse.data && (
              <RankedBars data={byWarehouse.data} xKey="warehouse_name" yKey="revenue" color={categorical.aqua} valueFormatter={money} />
            )}
          </ChartCard>
        </div>

        {customerGrowth.loading && <SkeletonKpiRow />}
        {customerGrowth.error && <ErrorState message={customerGrowth.error} onRetry={customerGrowth.reload} />}
        {customerGrowth.data && (
          <div className="kpi-row">
            <KpiCard
              icon="users"
              label="Active Customers"
              value={Number(customerGrowth.data.active_customers).toLocaleString()}
            />
            <KpiCard
              icon="packagePlus"
              label="New Customers"
              value={Number(customerGrowth.data.new_customers).toLocaleString()}
              accent="#0ca30c"
            />
            <KpiCard
              icon="checkCircle"
              label="Returning Customers"
              value={customerGrowth.data.returning_pct != null ? `${customerGrowth.data.returning_pct}%` : "—"}
              delta={`${Number(customerGrowth.data.returning_customers).toLocaleString()} customers`}
              deltaGood
            />
            <KpiCard
              icon="target"
              label="Avg. Orders / Active Customer"
              value={customerGrowth.data.avg_orders_per_active_customer ?? "—"}
            />
          </div>
        )}

        <div className="grid-2">
          <ChartCard title="New Customers Trend (last 90 days)">
            {customerGrowth.loading && <SkeletonChart />}
            {customerGrowth.error && <ErrorState message={customerGrowth.error} onRetry={customerGrowth.reload} />}
            {customerGrowth.data && (
              <TrendLine
                data={customerGrowth.data.trend}
                xKey="bucket"
                yKey="new_customers"
                color={categorical.aqua}
                valueFormatter={(v) => Number(v).toLocaleString()}
              />
            )}
            <p className="empty-state" style={{ padding: "8px 0 0" }}>
              Customer identity is synthetic - there is no real customer entity anywhere in Shuppa's source data.
              "New" means this synthetic customer's first-ever order falls in the selected window.
            </p>
          </ChartCard>

          <ChartCard title="New vs Returning Customers">
            {customerGrowth.loading && <SkeletonChart />}
            {customerGrowth.error && <ErrorState message={customerGrowth.error} onRetry={customerGrowth.reload} />}
            {customerGrowth.data && (
              <DonutChart
                data={[
                  { segment: "New", count: customerGrowth.data.new_customers },
                  { segment: "Returning", count: customerGrowth.data.returning_customers },
                ]}
                nameKey="segment"
                valueKey="count"
              />
            )}
          </ChartCard>
        </div>

        {deliveryPerformance.loading && <SkeletonKpiRow />}
        {deliveryPerformance.error && (
          <ErrorState message={deliveryPerformance.error} onRetry={deliveryPerformance.reload} />
        )}
        {deliveryPerformance.data && (
          <div className="kpi-row">
            <KpiCard
              icon="truck"
              label="Total Orders (last 31 days)"
              value={Number(deliveryPerformance.data.total_orders).toLocaleString()}
            />
            <KpiCard
              icon="checkCircle"
              label="On-Time Delivery"
              value={deliveryPerformance.data.on_time_pct != null ? `${deliveryPerformance.data.on_time_pct}%` : "—"}
              accent="#0ca30c"
            />
            <KpiCard
              icon="clock"
              label="Avg. Delivery Time"
              value={
                deliveryPerformance.data.avg_delivery_minutes != null
                  ? `${deliveryPerformance.data.avg_delivery_minutes} min`
                  : "—"
              }
            />
            <KpiCard
              icon="alertTriangle"
              label="Late Orders"
              value={Number(deliveryPerformance.data.late).toLocaleString()}
              accent="#d9822b"
            />
          </div>
        )}

        <div className="grid-2">
          <ChartCard title="On-Time Delivery Trend">
            {deliveryPerformance.loading && <SkeletonChart />}
            {deliveryPerformance.error && (
              <ErrorState message={deliveryPerformance.error} onRetry={deliveryPerformance.reload} />
            )}
            {deliveryPerformance.data && (
              <TrendLine
                data={deliveryPerformance.data.trend}
                xKey="bucket"
                yKey="on_time_pct"
                color={categorical.magenta}
                valueFormatter={(v) => `${v}%`}
              />
            )}
            <p className="empty-state" style={{ padding: "8px 0 0" }}>
              This is last-mile, customer-facing delivery from the fabricated order layer - a separate concept from
              the Delivery Risk Predictor page, which models real supplier-to-warehouse purchase order deliveries.
            </p>
          </ChartCard>

          <ChartCard title="Delivery Outcome Breakdown">
            {deliveryPerformance.loading && <SkeletonChart />}
            {deliveryPerformance.error && (
              <ErrorState message={deliveryPerformance.error} onRetry={deliveryPerformance.reload} />
            )}
            {deliveryPerformance.data && (
              <RankedBars
                data={[
                  { status: "On Time", count: deliveryPerformance.data.total_orders - deliveryPerformance.data.late - deliveryPerformance.data.cancelled - deliveryPerformance.data.returned },
                  { status: "Late", count: deliveryPerformance.data.late },
                  { status: "Cancelled", count: deliveryPerformance.data.cancelled },
                  { status: "Returned", count: deliveryPerformance.data.returned },
                ]}
                xKey="status"
                yKey="count"
                color={categorical.violet}
                valueFormatter={(v) => Number(v).toLocaleString()}
              />
            )}
          </ChartCard>
        </div>

        {returnCancellation.loading && <SkeletonKpiRow />}
        {returnCancellation.error && (
          <ErrorState message={returnCancellation.error} onRetry={returnCancellation.reload} />
        )}
        {returnCancellation.data && (
          <div className="kpi-row">
            <KpiCard
              icon="package"
              label="Return Rate"
              value={returnCancellation.data.return_pct != null ? `${returnCancellation.data.return_pct}%` : "—"}
              delta={`${Number(returnCancellation.data.returned).toLocaleString()} orders`}
            />
            <KpiCard
              icon="alertOctagon"
              label="Cancellation Rate"
              value={returnCancellation.data.cancellation_pct != null ? `${returnCancellation.data.cancellation_pct}%` : "—"}
              delta={`${Number(returnCancellation.data.cancelled).toLocaleString()} orders`}
            />
            <KpiCard
              icon="coins"
              label="Est. Lost Revenue"
              value={money(returnCancellation.data.lost_revenue)}
              accent="#c0392b"
            />
            <KpiCard
              icon="clipboardList"
              label="Total Orders (last 31 days)"
              value={Number(returnCancellation.data.total_orders).toLocaleString()}
            />
          </div>
        )}

        <div className="grid-2">
          <ChartCard title="Return Rate Trend">
            {returnCancellation.loading && <SkeletonChart />}
            {returnCancellation.error && (
              <ErrorState message={returnCancellation.error} onRetry={returnCancellation.reload} />
            )}
            {returnCancellation.data && (
              <TrendLine
                data={returnCancellation.data.trend}
                xKey="bucket"
                yKey="return_pct"
                color={categorical.aqua}
                valueFormatter={(v) => `${v}%`}
              />
            )}
          </ChartCard>

          <ChartCard title="Cancellation Rate Trend">
            {returnCancellation.loading && <SkeletonChart />}
            {returnCancellation.error && (
              <ErrorState message={returnCancellation.error} onRetry={returnCancellation.reload} />
            )}
            {returnCancellation.data && (
              <TrendLine
                data={returnCancellation.data.trend}
                xKey="bucket"
                yKey="cancellation_pct"
                color={categorical.magenta}
                valueFormatter={(v) => `${v}%`}
              />
            )}
            <p className="empty-state" style={{ padding: "8px 0 0" }}>
              Fabricated rates (see the Delivery Outcome Breakdown above) - there is no real returns/cancellations
              data anywhere in Shuppa's source data.
            </p>
          </ChartCard>
        </div>

        <CorrelatedProductsPanel warehouseId={warehouseId} />
      </div>
    </AppLayout>
  );
}
