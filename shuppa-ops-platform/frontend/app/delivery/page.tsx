"use client";

import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import DateRangeFilter from "../../components/DateRangeFilter";
import KpiCard from "../../components/KpiCard";
import DataTable from "../../components/DataTable";
import StatusPill from "../../components/StatusPill";
import Icon from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { SkeletonKpiRow } from "../../components/Skeleton";
import { deliveryApi, insightsApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useFilters } from "../../lib/FilterContext";
import PredictorForm from "./PredictorForm";
import { formatDelta } from "../../lib/format";
import KeyInsightsCard from "../../components/KeyInsightsCard";

export default function DeliveryRiskPage() {
  const { warehouseId, setWarehouseId, range, setRange, hydrated } = useFilters();

  const kpis = useApi(() => deliveryApi.kpis(warehouseId, range), [warehouseId, range]);
  const risky = useApi(() => deliveryApi.riskyOrders(8, warehouseId, range), [warehouseId, range]);

  return (
    <AppLayout>
      <TopBar title="Delivery Risk Predictor">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
        <DateRangeFilter value={range} hydrated={hydrated} onChange={setRange} />
      </TopBar>
      <div className="content-area">
        {kpis.loading && <SkeletonKpiRow />}
        {kpis.error && <ErrorState message={kpis.error} onRetry={kpis.reload} />}
        {kpis.data && (() => {
          const d = kpis.data.comparison?.deltas || {};
          const lateRateDelta = formatDelta(d.late_rate_pct, { higherIsBetter: false, isPercentagePoints: true });
          const delayDelta = formatDelta(d.avg_delay_days, { higherIsBetter: false });
          return (
            <div className="kpi-row">
              <KpiCard
                icon="clock"
                label="Historical Late Rate"
                value={`${kpis.data.late_rate_pct}%`}
                accent="#d03b3b"
                delta={lateRateDelta?.text}
                deltaGood={lateRateDelta?.good}
              />
              <KpiCard
                icon="calendar"
                label="Avg. Delay (when late)"
                value={`${Number(kpis.data.avg_delay_days).toFixed(1)} days`}
                delta={delayDelta?.text}
                deltaGood={delayDelta?.good}
              />
              <KpiCard
                icon="target"
                label="Model Accuracy"
                value={`${(kpis.data.model.train_accuracy * 100).toFixed(1)}%`}
                delta={`AUC ${kpis.data.model.train_auc}`}
              />
              <KpiCard icon="barChart" label="Trained On" value={`${Number(kpis.data.model.n_training_rows).toLocaleString()} orders`} />
            </div>
          );
        })()}

        <KeyInsightsCard fetcher={() => insightsApi.delivery(warehouseId, range)} deps={[warehouseId, range]} />

        <PredictorForm />

        <div className="card">
          <div className="chart-card-header">
            <h3>Historically Riskiest Purchase Orders</h3>
          </div>
          {risky.loading && <LoadingState />}
          {risky.error && <ErrorState message={risky.error} onRetry={risky.reload} />}
          {risky.data && (
            <DataTable
              keyField="po_id"
              rows={risky.data}
              emptyMessage="No late orders on record."
              columns={[
                { key: "po_id", header: "Order ID" },
                { key: "supplier_name", header: "Supplier" },
                { key: "product_name", header: "Product" },
                { key: "warehouse_name", header: "Warehouse" },
                { key: "order_quantity", header: "Quantity", align: "right" },
                { key: "delay_days", header: "Days Late", align: "right" },
                { key: "risk_level", header: "Severity", render: (r) => <StatusPill status={r.risk_level} /> },
              ]}
            />
          )}
        </div>
      </div>
    </AppLayout>
  );
}
