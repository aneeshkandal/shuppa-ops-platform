"use client";

import { useEffect, useState } from "react";
import { deliveryApi } from "../../lib/api";
import { riskLevelColor } from "../../lib/theme";
import { LoadingState } from "../../components/LoadingState";
import CustomDropdown from "../../components/CustomDropdown";

export default function PredictorForm() {
  const [options, setOptions] = useState<any>(null);
  const [form, setForm] = useState({
    supplier_id: "",
    warehouse_id: "",
    product_id: "",
    order_quantity: "200",
    lead_time_days: "10",
  });
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    deliveryApi
      .options()
      .then((o) => {
        setOptions(o);
        setForm((f) => ({
          ...f,
          supplier_id: o.suppliers[0]?.supplier_id?.toString() || "",
          warehouse_id: o.warehouses[0]?.warehouse_id?.toString() || "",
          product_id: o.products[0]?.product_id?.toString() || "",
        }));
      })
      .catch((e) => setError(e?.message || "Could not load form options."));
  }, []);

  const update = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await deliveryApi.predict({
        supplier_id: Number(form.supplier_id),
        warehouse_id: Number(form.warehouse_id),
        product_id: form.product_id ? Number(form.product_id) : undefined,
        order_quantity: Number(form.order_quantity),
        lead_time_days: Number(form.lead_time_days),
      });
      setResult(res);
    } catch (e: any) {
      setError(e?.message || "Could not score this order.");
    } finally {
      setLoading(false);
    }
  };

  if (!options) return <LoadingState label="Loading suppliers, warehouses & products..." />;

  return (
    <div className="grid-2">
      <div className="card">
        <div className="chart-card-header">
          <h3>Predict Delivery Risk</h3>
        </div>
        <div className="form-grid">
          <div className="form-field">
            <label>Supplier</label>
            <CustomDropdown
              value={form.supplier_id}
              onChange={(v) => update("supplier_id", v)}
              options={options.suppliers.map((s: any) => ({ value: s.supplier_id, label: s.supplier_name }))}
            />
          </div>
          <div className="form-field">
            <label>Product</label>
            <CustomDropdown
              value={form.product_id}
              onChange={(v) => update("product_id", v)}
              options={options.products.map((p: any) => ({ value: p.product_id, label: p.product_name }))}
            />
          </div>
          <div className="form-field">
            <label>Warehouse</label>
            <CustomDropdown
              value={form.warehouse_id}
              onChange={(v) => update("warehouse_id", v)}
              options={options.warehouses.map((w: any) => ({ value: w.warehouse_id, label: w.warehouse_name }))}
            />
          </div>
          <div className="form-field">
            <label>Order Quantity: {form.order_quantity} units</label>
            <input
              type="range"
              min={10}
              max={1000}
              value={form.order_quantity}
              onChange={(e) => update("order_quantity", e.target.value)}
            />
          </div>
          <div className="form-field">
            <label>Lead Time: {form.lead_time_days} days</label>
            <input
              type="range"
              min={1}
              max={20}
              value={form.lead_time_days}
              onChange={(e) => update("lead_time_days", e.target.value)}
            />
          </div>
          <button className="btn-primary" onClick={submit} disabled={loading}>
            {loading ? "Scoring..." : "Predict Risk"}
          </button>
        </div>
        {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
      </div>

      <div className="card">
        <div className="chart-card-header">
          <h3>Delivery Risk Analysis</h3>
        </div>
        {!result && <p className="empty-state">Fill in the form and click Predict Risk.</p>}
        {result && (
          <div>
            <div className="risk-gauge-value" style={{ color: riskLevelColor[result.risk_level] }}>
              {Math.round(result.risk_probability * 100)}%
            </div>
            <div className="risk-gauge-label" style={{ color: riskLevelColor[result.risk_level] }}>
              {result.risk_level} RISK
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 12 }}>{result.note}</p>

            <div className="chart-card-header" style={{ marginTop: 16 }}>
              <h3>Risk Explanation</h3>
            </div>
            {result.explanation.map((f: any) => (
              <div key={f.name} className="alert-item">
                <div style={{ flex: 1 }}>
                  <div className="alert-title">
                    {f.name} <span style={{ fontWeight: 500 }}>{f.display}</span>
                  </div>
                  <div className="alert-detail" style={{ color: f.is_unfavorable ? "var(--status-critical)" : "var(--status-good)" }}>
                    {f.comparison}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
