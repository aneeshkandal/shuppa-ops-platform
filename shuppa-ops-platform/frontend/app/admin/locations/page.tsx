"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import { adminApi, WAREHOUSES } from "../../../lib/api";
import CustomDropdown from "../../../components/CustomDropdown";

const STORAGE_TYPES = ["AMBIENT", "CHILLED", "FROZEN", "VAPE_DRAWER"];

const initialForm = {
  warehouse_id: "1",
  location_code: "",
  storage_type: "AMBIENT",
  shelf_tier: "1",
  sub_location_start: "1",
  sub_location_count: "1",
  is_overstock_tier: false,
  max_weight_kg: "200",
  max_volume_cm3: "200000",
  note: "",
};

export default function AdminLocationsPage() {
  const [form, setForm] = useState(initialForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const update = (key: string, value: any) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    setSaving(true);
    setError(null);
    setResult(null);
    try {
      const res = await adminApi.addLocation({
        warehouse_id: Number(form.warehouse_id),
        location_code: Number(form.location_code),
        storage_type: form.storage_type,
        shelf_tier: Number(form.shelf_tier),
        sub_location_start: Number(form.sub_location_start),
        sub_location_count: Number(form.sub_location_count),
        is_overstock_tier: form.is_overstock_tier,
        max_weight_kg: Number(form.max_weight_kg),
        max_volume_cm3: Number(form.max_volume_cm3),
        note: form.note || undefined,
      });
      setResult(res);
      setForm(initialForm);
    } catch (e: any) {
      setError(e?.message || "Could not add location.");
    } finally {
      setSaving(false);
    }
  };

  const valid = form.location_code && form.max_weight_kg && form.max_volume_cm3;

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Locations" />
        <div className="content-area">
          <div className="card admin-form-card">
            <div className="chart-card-header">
              <h3>Add Location / Sub-Locations</h3>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: -6, marginBottom: 10 }}>
              Adds one location code with a range of sub-location slots underneath it (e.g. sub-locations 1-20 under
              shelf tier 3). Repeat this for each shelf tier the location has.
            </p>
            <div className="form-grid">
              <div className="form-field">
                <label>Warehouse</label>
                <CustomDropdown
                  value={form.warehouse_id}
                  onChange={(v) => update("warehouse_id", v)}
                  options={WAREHOUSES.filter((w) => w.id !== undefined).map((w) => ({ value: w.id!, label: w.name }))}
                />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div className="form-field">
                  <label>Location Code</label>
                  <input type="number" value={form.location_code} onChange={(e) => update("location_code", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>Shelf Tier</label>
                  <input type="number" value={form.shelf_tier} onChange={(e) => update("shelf_tier", e.target.value)} />
                </div>
              </div>
              <div className="form-field">
                <label>Storage Type</label>
                <CustomDropdown
                  value={form.storage_type}
                  onChange={(v) => update("storage_type", v)}
                  options={STORAGE_TYPES.map((t) => ({ value: t, label: t }))}
                />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div className="form-field">
                  <label>First Sub-Location #</label>
                  <input
                    type="number"
                    value={form.sub_location_start}
                    onChange={(e) => update("sub_location_start", e.target.value)}
                  />
                </div>
                <div className="form-field">
                  <label>How Many Slots</label>
                  <input
                    type="number"
                    value={form.sub_location_count}
                    onChange={(e) => update("sub_location_count", e.target.value)}
                  />
                </div>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div className="form-field">
                  <label>Max Weight (kg) per slot</label>
                  <input type="number" value={form.max_weight_kg} onChange={(e) => update("max_weight_kg", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>Max Volume (cm³) per slot</label>
                  <input
                    type="number"
                    value={form.max_volume_cm3}
                    onChange={(e) => update("max_volume_cm3", e.target.value)}
                  />
                </div>
              </div>
              <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={form.is_overstock_tier}
                  onChange={(e) => update("is_overstock_tier", e.target.checked)}
                />
                Overstock tier
              </label>
              <div className="form-field">
                <label>Note (optional)</label>
                <input type="text" value={form.note} onChange={(e) => update("note", e.target.value)} />
              </div>
              <button className="btn-primary" onClick={submit} disabled={saving || !valid}>
                {saving ? "Adding..." : "Add Location"}
              </button>
            </div>
            {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
            {result && (
              <p className="empty-state" style={{ color: "var(--status-good)" }}>
                Added location {result.location_code} ({result.storage_type}) with {result.sub_locations_added} sub-location
                slot(s) in warehouse {result.warehouse_id}.
              </p>
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
