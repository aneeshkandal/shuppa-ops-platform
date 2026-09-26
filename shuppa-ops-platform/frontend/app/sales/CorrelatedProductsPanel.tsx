"use client";

import { useState } from "react";
import { ErrorState } from "../../components/LoadingState";
import { optimizerApi, salesApi } from "../../lib/api";

/**
 * "Products with a similar demand pattern" - search for a product, see which
 * others' daily sales tend to rise and fall together with it.
 *
 * IMPORTANT: this is NOT market-basket / "customers who bought this also
 * bought" analysis - the dataset has no order-level transactions, only daily
 * per-product totals, so there's no way to know what was actually bought
 * together in one basket. This is a same-day sales-correlation proxy,
 * labeled as such below - useful as a co-location hint, not real basket
 * data. See backend/app/services/sales_service.py:get_correlated_products.
 */
export default function CorrelatedProductsPanel({ warehouseId }: { warehouseId?: number }) {
  const [search, setSearch] = useState("");
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selected, setSelected] = useState<{ product_id: number; product_name: string } | null>(null);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async (q: string) => {
    setSearch(q);
    setSelected(null);
    setResult(null);
    if (!q.trim()) {
      setCandidates([]);
      return;
    }
    try {
      const rows = await optimizerApi.products(q, 8);
      setCandidates(rows);
    } catch {
      setCandidates([]);
    }
  };

  const pick = async (c: any) => {
    setSelected({ product_id: c.product_id, product_name: c.product_name });
    setCandidates([]);
    setSearch(c.product_name);
    setLoading(true);
    setError(null);
    try {
      const res = await salesApi.correlatedProducts(c.product_id, warehouseId, 5);
      setResult(res);
    } catch (e: any) {
      setError(e?.message || "Could not compute demand-pattern correlation.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Products with a Similar Demand Pattern</h3>
      </div>
      <p className="empty-state" style={{ padding: "0 0 8px" }}>
        Not real "bought together" data - the sales data only has daily per-product totals, not individual orders,
        so there's no way to know what was actually purchased in the same basket. This instead finds products whose
        daily sales tend to rise and fall on the same days, which can still hint at natural co-location candidates.
      </p>
      <div className="form-field" style={{ maxWidth: 320, position: "relative" }}>
        <label>Search for a product</label>
        <input
          type="text"
          value={search}
          onChange={(e) => runSearch(e.target.value)}
          placeholder="e.g. Sparkling Water"
        />
        {candidates.length > 0 && (
          <div className="card" style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 5, padding: 6 }}>
            {candidates.map((c) => (
              <div
                key={c.product_id}
                onClick={() => pick(c)}
                style={{ padding: "6px 8px", cursor: "pointer", fontSize: 13 }}
                className="nav-item"
              >
                {c.product_name}
              </div>
            ))}
          </div>
        )}
      </div>

      {loading && <p className="empty-state">Comparing demand patterns...</p>}
      {error && <ErrorState message={error} onRetry={() => selected && pick(selected)} />}
      {result && result.note && <p className="empty-state">{result.note}</p>}
      {result && result.correlated?.length > 0 && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          {result.correlated.map((c: any) => (
            <div className="suggestion-card" key={c.product_id}>
              <div className="suggestion-header">
                <span>
                  {c.product_name} {c.category ? `(${c.category})` : ""}
                </span>
                <span className="fit-score">{Math.round(c.correlation * 100)}% pattern match</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
