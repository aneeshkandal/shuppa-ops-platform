"use client";

import Link from "next/link";
import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import KpiCard from "../../components/KpiCard";
import Icon from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { alertsApi, deliveryApi, salesApi, stockApi, supplierApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";
import { formatDelta } from "../../lib/format";

const money = (v: number) => `€${Number(v ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

export default function ExecutiveOverviewPage() {
  const { warehouseId, setWarehouseId } = useFilters();

  const stock = useApi(() => stockApi.summary(warehouseId), [warehouseId]);
  const sales = useApi(() => salesApi.kpis(warehouseId), [warehouseId]);
  const suppliers = useApi(() => supplierApi.kpis(warehouseId), [warehouseId]);
  const delivery = useApi(() => deliveryApi.kpis(warehouseId), [warehouseId]);
  const alerts = useApi(() => alertsApi.all(warehouseId), [warehouseId]);

  const anyLoading = stock.loading || sales.loading || suppliers.loading || delivery.loading;
  const criticalAlerts = (alerts.data || []).filter((a: any) => a.level === "critical");
  const otherAlerts = (alerts.data || []).filter((a: any) => a.level !== "critical");

  return (
    <AppLayout>
      <TopBar title="Executive Overview">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
      </TopBar>
      <div className="content-area">
        {anyLoading && <LoadingState label="Pulling the headline numbers from every page..." />}

        <div className="card">
          <div className="chart-card-header">
            <h3><Icon name="package" size={16} /> Stock Summary</h3>
            <Link href="/stock" className="btn-secondary btn-small" style={{ textDecoration: "none" }}>
              Open page <Icon name="arrowRight" size={13} />
            </Link>
          </div>
          {stock.error && <ErrorState message={stock.error} onRetry={stock.reload} />}
          {stock.data && (() => {
            const d = stock.data.comparison?.deltas || {};
            const stockoutDelta = formatDelta(d.stockout_pct, { higherIsBetter: false, isPercentagePoints: true });
            return (
              <div className="kpi-row">
                <KpiCard icon="package" label="Total Products" value={String(stock.data.total_products)} />
                <KpiCard
                  icon="alertTriangle"
                  label="Stockout %"
                  value={`${stock.data.stockout_pct}%`}
                  accent="#ec835a"
                  delta={stockoutDelta?.text}
                  deltaGood={stockoutDelta?.good}
                />
                <KpiCard icon="coins" label="Inventory at Risk" value={money(stock.data.inventory_at_risk_value)} accent="#d03b3b" />
                <KpiCard icon="coins" label="Total Inventory Value" value={money(stock.data.total_inventory_value)} />
              </div>
            );
          })()}
        </div>

        <div className="card">
          <div className="chart-card-header">
            <h3><Icon name="trendingUp" size={16} /> Sales Analytics</h3>
            <Link href="/sales" className="btn-secondary btn-small" style={{ textDecoration: "none" }}>
              Open page <Icon name="arrowRight" size={13} />
            </Link>
          </div>
          {sales.error && <ErrorState message={sales.error} onRetry={sales.reload} />}
          {sales.data && (() => {
            const d = sales.data.comparison?.deltas || {};
            const revenueDelta = formatDelta(d.total_revenue, { higherIsBetter: true, isCurrency: true });
            return (
              <div className="kpi-row">
                <KpiCard
                  icon="coins"
                  label="Total Revenue"
                  value={money(sales.data.total_revenue)}
                  delta={revenueDelta?.text}
                  deltaGood={revenueDelta?.good}
                />
                <KpiCard icon="package" label="Units Sold" value={Number(sales.data.total_units_sold).toLocaleString()} />
                <KpiCard icon="trendingUp" label="Total Profit" value={money(sales.data.total_profit)} accent="#0ca30c" />
                <KpiCard icon="award" label="Top Product" value={sales.data.top_product_name || "—"} />
              </div>
            );
          })()}
        </div>

        <div className="card">
          <div className="chart-card-header">
            <h3><Icon name="users" size={16} /> Supplier Summary</h3>
            <Link href="/suppliers" className="btn-secondary btn-small" style={{ textDecoration: "none" }}>
              Open page <Icon name="arrowRight" size={13} />
            </Link>
          </div>
          {suppliers.error && <ErrorState message={suppliers.error} onRetry={suppliers.reload} />}
          {suppliers.data && (() => {
            const d = suppliers.data.comparison?.deltas || {};
            const onTimeDelta = formatDelta(d.on_time_delivery_pct, { higherIsBetter: true, isPercentagePoints: true });
            return (
              <div className="kpi-row">
                <KpiCard
                  icon="truck"
                  label="On-Time Delivery %"
                  value={`${suppliers.data.on_time_delivery_pct}%`}
                  accent="#0ca30c"
                  delta={onTimeDelta?.text}
                  deltaGood={onTimeDelta?.good}
                />
                <KpiCard icon="clock" label="Late Delivery %" value={`${suppliers.data.late_delivery_pct}%`} accent="#d03b3b" />
                <KpiCard icon="clipboardList" label="Total Orders" value={Number(suppliers.data.total_orders).toLocaleString()} />
                <KpiCard icon="coins" label="Order Value" value={money(suppliers.data.total_order_value)} />
              </div>
            );
          })()}
        </div>

        <div className="card">
          <div className="chart-card-header">
            <h3><Icon name="truck" size={16} /> Delivery Risk Predictor</h3>
            <Link href="/delivery" className="btn-secondary btn-small" style={{ textDecoration: "none" }}>
              Open page <Icon name="arrowRight" size={13} />
            </Link>
          </div>
          {delivery.error && <ErrorState message={delivery.error} onRetry={delivery.reload} />}
          {delivery.data && (
            <div className="kpi-row">
              <KpiCard icon="clock" label="Historical Late Rate" value={`${delivery.data.late_rate_pct}%`} accent="#d03b3b" />
              <KpiCard icon="calendar" label="Avg. Delay (when late)" value={`${Number(delivery.data.avg_delay_days).toFixed(1)} days`} />
              <KpiCard icon="target" label="Model Accuracy" value={`${(delivery.data.model.train_accuracy * 100).toFixed(1)}%`} />
            </div>
          )}
        </div>

        <div className="card">
          <div className="chart-card-header">
            <h3><Icon name="bell" size={16} /> Needs Attention</h3>
            <Link href="/alerts" className="btn-secondary btn-small" style={{ textDecoration: "none" }}>
              Open Alerts Center <Icon name="arrowRight" size={13} />
            </Link>
          </div>
          {alerts.loading && <LoadingState />}
          {alerts.error && <ErrorState message={alerts.error} onRetry={alerts.reload} />}
          {alerts.data && alerts.data.length === 0 && <p className="empty-state">Nothing needs attention right now.</p>}
          {[...criticalAlerts, ...otherAlerts].slice(0, 5).map((a: any, i: number) => (
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
    </AppLayout>
  );
}
