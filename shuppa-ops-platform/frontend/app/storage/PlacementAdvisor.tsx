"use client";

import { useState } from "react";
import { optimizerApi } from "../../lib/api";
import CustomDropdown from "../../components/CustomDropdown";

const FRAGILITY = ["LOW", "MEDIUM", "HIGH"];
const STORAGE_TYPES = ["AMBIENT", "CHILLED", "FROZEN", "VAPE_DRAWER"];

export default function PlacementAdvisor() {
  const [form, setForm] = useState({
    length_cm: "30",
    width_cm: "15",
    height_cm: "20",
    weight_kg: "2",
    fragility: "MEDIUM",
    storage_type: "",
  });
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const update = (key: string, value: string) => setForm((f) => ({ ...f, [key]: value }));

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await optimizerApi.suggest({
        length_cm: Number(form.length_cm),
        width_cm: Number(form.width_cm),
        height_cm: Number(form.height_cm),
        weight_kg: Number(form.weight_kg),
        fragility: form.fragility,
        storage_type: form.storage_type || undefined,
        top_n: 3,
      });
      setResult(res);
    } catch (e: any) {
      setError(e?.message || "Could not get a suggestion.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="form-grid">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <div className="form-field">
            <label>Length (cm)</label>
            <input type="number" value={form.length_cm} onChange={(e) => update("length_cm", e.target.value)} />
          </div>
          <div className="form-field">
            <label>Width (cm)</label>
            <input type="number" value={form.width_cm} onChange={(e) => update("width_cm", e.target.value)} />
          </div>
          <div className="form-field">
            <label>Height (cm)</label>
            <input type="number" value={form.height_cm} onChange={(e) => update("height_cm", e.target.value)} />
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
          <label>Storage Type (leave blank to auto-detect)</label>
          <CustomDropdown
            value={form.storage_type}
            onChange={(v) => update("storage_type", v)}
            options={[{ value: "", label: "Auto-detect" }, ...STORAGE_TYPES.map((t) => ({ value: t, label: t }))]}
          />
        </div>
        <button className="btn-primary" onClick={submit} disabled={loading}>
          {loading ? "Scoring locations..." : "Suggest Location"}
        </button>
      </div>

      {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}

      {result && (
        <div style={{ marginTop: 18 }}>
          <div className="chart-card-header">
            <h3>Suggested Locations</h3>
          </div>
          {result.message && <p className="empty-state">{result.message}</p>}
          {result.suggestions.map((s: any) => (
            <div className="suggestion-card" key={s.location_id}>
              <div className="suggestion-header">
                <span>
                  {s.storage_type} - Location {s.location_code} / Tier {s.shelf_tier}
                </span>
                <span className="fit-score">{s.fit_score}% fit</span>
              </div>
              <div className="reason-tags">
                {s.reasons.map((r: string, i: number) => (
                  <span className="reason-tag" key={i}>
                    {r}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
