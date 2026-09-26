"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import DataTable from "../../../components/DataTable";
import { ErrorState, LoadingState } from "../../../components/LoadingState";
import { adminApi, WAREHOUSES } from "../../../lib/api";
import { useApi } from "../../../lib/useApi";
import CustomDropdown from "../../../components/CustomDropdown";

export default function AdminSuppliersPage() {
  const suppliers = useApi(() => adminApi.getSuppliers(), []);
  const [name, setName] = useState("");
  const [warehouseId, setWarehouseId] = useState<string>("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      await adminApi.addSupplier({ supplier_name: name, warehouse_id: warehouseId ? Number(warehouseId) : undefined });
      setName("");
      setOk(true);
      suppliers.reload();
    } catch (e: any) {
      setError(e?.message || "Could not add supplier.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Suppliers" />
        <div className="content-area">
          <div className="card admin-form-card">
            <div className="chart-card-header">
              <h3>Add Supplier</h3>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Supplier Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="form-field">
                <label>Scope</label>
                <CustomDropdown
                  value={warehouseId}
                  onChange={setWarehouseId}
                  options={[
                    { value: "", label: "Common (all warehouses)" },
                    ...WAREHOUSES.filter((w) => w.id !== undefined).map((w) => ({ value: w.id!, label: `${w.name} only` })),
                  ]}
                />
              </div>
              <button className="btn-primary" onClick={submit} disabled={saving || !name}>
                {saving ? "Adding..." : "Add Supplier"}
              </button>
            </div>
            {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
            {ok && <p className="empty-state" style={{ color: "var(--status-good)" }}>Supplier added.</p>}
          </div>

          <div className="card admin-table-wrap">
            <div className="chart-card-header">
              <h3>Existing Suppliers</h3>
            </div>
            {suppliers.loading && <LoadingState />}
            {suppliers.error && <ErrorState message={suppliers.error} onRetry={suppliers.reload} />}
            {suppliers.data && (
              <DataTable
                keyField="supplier_id"
                rows={suppliers.data}
                columns={[
                  { key: "supplier_id", header: "ID" },
                  { key: "supplier_name", header: "Name" },
                  {
                    key: "warehouse_id",
                    header: "Scope",
                    render: (r) =>
                      r.warehouse_id == null
                        ? "Common"
                        : WAREHOUSES.find((w) => w.id === r.warehouse_id)?.name || `Warehouse ${r.warehouse_id}`,
                  },
                  { key: "has_order_history", header: "Has Orders", render: (r) => (r.has_order_history ? "Yes" : "No") },
                ]}
              />
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
