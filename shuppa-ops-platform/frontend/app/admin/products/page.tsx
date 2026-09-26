"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import { adminApi, returnsApi } from "../../../lib/api";
import CustomDropdown from "../../../components/CustomDropdown";

const FRAGILITY = ["LOW", "MEDIUM", "HIGH"];
const STORAGE_TYPES = ["AMBIENT", "CHILLED", "FROZEN", "VAPE_DRAWER"];

const initialForm = {
  product_name: "",
  description: "",
  selling_price: "",
  unit_cost: "",
  category: "",
  length_cm: "",
  width_cm: "",
  height_cm: "",
  weight_kg: "",
  fragility: "MEDIUM",
  storage_type: "AMBIENT",
  stackable: true,
};

export default function AdminAddProductPage() {
  // Pre-filled when arriving from a Supplier Return's "List as New Product"
  // action (see suppliers/SupplierReturnDetailModal.tsx) - read directly from
  // window.location (rather than next/navigation's useSearchParams) so this
  // page doesn't need a Suspense boundary just for an optional deep link.
  const [returnItemId] = useState<number | null>(() => {
    if (typeof window === "undefined") return null;
    const params = new URLSearchParams(window.location.search);
    const id = params.get("return_item_id");
    return id ? Number(id) : null;
  });
  const [form, setForm] = useState(() => {
    if (typeof window === "undefined") return initialForm;
    const params = new URLSearchParams(window.location.search);
    const name = params.get("product_name");
    return name ? { ...initialForm, product_name: name } : initialForm;
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);

  const update = (key: string, value: any) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    setSaving(true);
    setError(null);
    setResult(null);
    try {
      const res = await adminApi.addProduct({
        product_name: form.product_name,
        description: form.description || undefined,
        selling_price: Number(form.selling_price),
        unit_cost: Number(form.unit_cost),
        category: form.category || undefined,
        length_cm: Number(form.length_cm),
        width_cm: Number(form.width_cm),
        height_cm: Number(form.height_cm),
        weight_kg: Number(form.weight_kg),
        fragility: form.fragility,
        storage_type: form.storage_type,
        stackable: form.stackable,
      });
      if (returnItemId) {
        try {
          await returnsApi.resolveItem(returnItemId, {
            resolution: "LISTED_AS_NEW_PRODUCT",
            created_product_id: res.product_id,
          });
        } catch (e: any) {
          // The product itself was created successfully - surface this as a
          // secondary warning rather than losing that fact.
          setError(
            `Product added, but the return item couldn't be marked resolved: ${e?.message || "unknown error"}`
          );
        }
      }
      setResult(res);
      setForm(initialForm);
    } catch (e: any) {
      setError(e?.message || "Could not add product.");
    } finally {
      setSaving(false);
    }
  };

  const valid =
    form.product_name && form.selling_price && form.unit_cost && form.length_cm && form.width_cm && form.height_cm && form.weight_kg;

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Add Product" />
        <div className="content-area">
          <div className="card admin-form-card">
            <div className="chart-card-header">
              <h3>New Product</h3>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: -6, marginBottom: 10 }}>
              {
                "Height / width / length here are real, not synthetic - they're what the Stock Optimizer's Smart Placement Advisor uses. Once saved, this product shows up on every Stock Optimizer page under “New Products Awaiting Placement” until someone assigns it a slot."
              }
            </p>
            {returnItemId && (
              <p className="empty-state" style={{ marginTop: -4, marginBottom: 10 }}>
                Adding this product will also resolve supplier return item #{returnItemId} as "Listed as New Product".
              </p>
            )}
            <div className="form-grid">
              <div className="form-field">
                <label>Product Name</label>
                <input type="text" value={form.product_name} onChange={(e) => update("product_name", e.target.value)} />
              </div>
              <div className="form-field">
                <label>Description</label>
                <input type="text" value={form.description} onChange={(e) => update("description", e.target.value)} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div className="form-field">
                  <label>Selling Price (€)</label>
                  <input type="number" value={form.selling_price} onChange={(e) => update("selling_price", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>Unit Cost (€)</label>
                  <input type="number" value={form.unit_cost} onChange={(e) => update("unit_cost", e.target.value)} />
                </div>
              </div>
              <div className="form-field">
                <label>Category (optional – leave blank to default to General Merchandise)</label>
                <input type="text" value={form.category} onChange={(e) => update("category", e.target.value)} />
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div className="form-field">
                  <label>Height (cm)</label>
                  <input type="number" value={form.height_cm} onChange={(e) => update("height_cm", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>Width (cm)</label>
                  <input type="number" value={form.width_cm} onChange={(e) => update("width_cm", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>Length (cm)</label>
                  <input type="number" value={form.length_cm} onChange={(e) => update("length_cm", e.target.value)} />
                </div>
                <div className="form-field">
                  <label>Weight (kg)</label>
                  <input type="number" value={form.weight_kg} onChange={(e) => update("weight_kg", e.target.value)} />
                </div>
              </div>
              <div className="form-field">
                <label>Fragility</label>
                <CustomDropdown
                  value={form.fragility}
                  onChange={(v) => update("fragility", v)}
                  options={FRAGILITY.map((f) => ({ value: f, label: f }))}
                />
              </div>
              <div className="form-field">
                <label>Storage Type</label>
                <CustomDropdown
                  value={form.storage_type}
                  onChange={(v) => update("storage_type", v)}
                  options={STORAGE_TYPES.map((t) => ({ value: t, label: t }))}
                />
              </div>
              <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 8 }}>
                <input type="checkbox" checked={form.stackable} onChange={(e) => update("stackable", e.target.checked)} />
                Stackable
              </label>
              <button className="btn-primary" onClick={submit} disabled={saving || !valid}>
                {saving ? "Adding..." : "Add Product"}
              </button>
            </div>
            {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
            {result && (
              <p className="empty-state" style={{ color: "var(--status-good)" }}>
                Added "{result.product_name}" (product_id {result.product_id}) – now visible under New Products Awaiting
                Placement on the Stock Optimizer page.
              </p>
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
