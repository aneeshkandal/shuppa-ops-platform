"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import DataTable from "../../../components/DataTable";
import { ErrorState, LoadingState } from "../../../components/LoadingState";
import { adminApi } from "../../../lib/api";
import { useApi } from "../../../lib/useApi";

export default function AdminWarehousesPage() {
  const warehouses = useApi(() => adminApi.getWarehouses(), []);
  const [name, setName] = useState("");
  const [city, setCity] = useState("Dublin");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      await adminApi.addWarehouse({ warehouse_name: name, city });
      setName("");
      setOk(true);
      warehouses.reload();
    } catch (e: any) {
      setError(e?.message || "Could not add warehouse.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Warehouses" />
        <div className="content-area">
          <div className="card admin-form-card">
            <div className="chart-card-header">
              <h3>Add Warehouse</h3>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Warehouse Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Swords" />
              </div>
              <div className="form-field">
                <label>City</label>
                <input type="text" value={city} onChange={(e) => setCity(e.target.value)} />
              </div>
              <button className="btn-primary" onClick={submit} disabled={saving || !name}>
                {saving ? "Adding..." : "Add Warehouse"}
              </button>
            </div>
            {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
            {ok && <p className="empty-state" style={{ color: "var(--status-good)" }}>Warehouse added.</p>}
          </div>

          <div className="card admin-table-wrap">
            <div className="chart-card-header">
              <h3>Existing Warehouses</h3>
            </div>
            {warehouses.loading && <LoadingState />}
            {warehouses.error && <ErrorState message={warehouses.error} onRetry={warehouses.reload} />}
            {warehouses.data && (
              <DataTable
                keyField="warehouse_id"
                rows={warehouses.data}
                columns={[
                  { key: "warehouse_id", header: "ID" },
                  { key: "warehouse_name", header: "Name" },
                  { key: "city", header: "City" },
                ]}
              />
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
