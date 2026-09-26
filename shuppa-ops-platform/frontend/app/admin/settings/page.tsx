"use client";

import { useEffect, useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import { ErrorState, LoadingState } from "../../../components/LoadingState";
import Icon, { IconName } from "../../../components/Icon";
import KpiCard from "../../../components/KpiCard";
import { settingsApi } from "../../../lib/api";
import { useApi } from "../../../lib/useApi";

// Same icon/color roles as the Alerts Center's critical/serious/warning
// breakdown, so this "what would change" preview reads as the same visual
// language rather than a bespoke card style of its own.
const LEVEL_ICON: Record<string, IconName> = {
  critical: "alertOctagon",
  serious: "alertTriangle",
  warning: "alertTriangle",
  total: "bell",
};
const LEVEL_ACCENT: Record<string, string | undefined> = {
  critical: "#d03b3b",
  serious: "#ec835a",
  warning: "#fab219",
  total: undefined,
};

// Friendly labels/help text for the known setting keys - see
// backend/app/migrations.py's DEFAULT_SETTINGS for the source of truth on
// which keys exist. Any key not listed here still renders with its raw name
// so a newly added setting is never hidden.
const SETTING_META: Record<string, { label: string; help: string; suffix?: string }> = {
  stockout_pct_threshold: {
    label: "Stockout % Alert Threshold",
    help: "Stock Summary raises a Critical alert when the stockout rate exceeds this.",
    suffix: "%",
  },
  overstock_value_threshold: {
    label: "Excess Inventory Value Threshold",
    help: "Stock Summary raises an alert when overstock value exceeds this.",
    suffix: "€",
  },
  supplier_late_pct_medium_threshold: {
    label: "Supplier Risk – Medium Threshold",
    help: "Suppliers with a late-delivery % above this are rated Medium risk.",
    suffix: "%",
  },
  supplier_late_pct_high_threshold: {
    label: "Supplier Risk – High Threshold",
    help: "Suppliers with a late-delivery % above this are rated High risk (and flagged in Alerts Center).",
    suffix: "%",
  },
  delivery_high_risk_alert_count: {
    label: "Delivery Delay Spike Alert Count",
    help: "Alerts Center flags a delivery spike once this many severely-late orders are seen recently.",
  },
  optimizer_overstocked_threshold: {
    label: "Storage Overstocked Threshold",
    help: "Stock Optimizer / Alerts Center flags storage locations above this % of capacity.",
    suffix: "%",
  },
};

export default function AdminSettingsPage() {
  const settings = useApi(() => settingsApi.getAll(), []);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const [preview, setPreview] = useState<{ current: Record<string, number>; proposed: Record<string, number> } | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    if (settings.data) {
      const v: Record<string, string> = {};
      settings.data.forEach((s) => (v[s.setting_key] = s.setting_value));
      setValues(v);
    }
  }, [settings.data]);

  // Any edit invalidates a stale preview rather than leaving a mismatched
  // one on screen - the person has to re-run it to see the current numbers.
  const updateValue = (key: string, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setPreview(null);
  };

  const runPreview = async () => {
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const res = await settingsApi.preview(values);
      setPreview(res);
    } catch (e: any) {
      setPreviewError(e?.message || "Could not compute the preview.");
    } finally {
      setPreviewLoading(false);
    }
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      await settingsApi.update(values);
      setOk(true);
      setPreview(null);
      settings.reload();
    } catch (e: any) {
      setError(e?.message || "Could not save settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Settings" />
        <div className="content-area">
          <div className="card admin-form-card" style={{ maxWidth: 640 }}>
            <div className="chart-card-header">
              <h3>Dashboard Alert Thresholds</h3>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: -6, marginBottom: 10 }}>
              These used to be hardcoded constants - tune them here instead and every page (Stock Summary, Supplier
              Summary, Stock Optimizer, Alerts Center) picks up the new value immediately.
            </p>
            {settings.loading && <LoadingState />}
            {settings.error && <ErrorState message={settings.error} onRetry={settings.reload} />}
            {settings.data && (
              <div className="form-grid">
                {settings.data.map((s) => {
                  const meta = SETTING_META[s.setting_key] || { label: s.setting_key, help: "" };
                  return (
                    <div className="form-field" key={s.setting_key}>
                      <label>
                        {meta.label}
                        {meta.suffix ? ` (${meta.suffix})` : ""}
                      </label>
                      <input
                        type="number"
                        value={values[s.setting_key] ?? ""}
                        onChange={(e) => updateValue(s.setting_key, e.target.value)}
                      />
                      {meta.help && <span style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{meta.help}</span>}
                    </div>
                  );
                })}
                <div style={{ display: "flex", gap: 8 }}>
                  <button className="btn-secondary" type="button" onClick={runPreview} disabled={previewLoading}>
                    {previewLoading ? "Checking..." : "Preview Impact"}
                  </button>
                  <button className="btn-primary" onClick={save} disabled={saving}>
                    {saving ? "Saving..." : "Save Changes"}
                  </button>
                </div>
              </div>
            )}
            {previewError && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{previewError}</p>}
            {preview && (
              <div className="card" style={{ marginTop: 14, background: "rgba(139, 92, 246, 0.06)" }}>
                <div className="chart-card-header">
                  <h3>What would change</h3>
                </div>
                <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: -4, marginBottom: 10 }}>
                  Active-alert counts under today's saved thresholds vs. the values above, without saving anything.
                </p>
                <div className="kpi-row">
                  {(["critical", "serious", "warning", "total"] as const).map((level) => {
                    const before = preview.current[level] ?? 0;
                    const after = preview.proposed[level] ?? 0;
                    const changed = before !== after;
                    return (
                      <KpiCard
                        key={level}
                        icon={LEVEL_ICON[level]}
                        accent={LEVEL_ACCENT[level]}
                        label={level.charAt(0).toUpperCase() + level.slice(1)}
                        value={
                          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                            {before} <Icon name="arrowRight" size={14} /> {after}
                          </span>
                        }
                        delta={changed ? `${after > before ? "+" : ""}${after - before}` : undefined}
                        deltaGood={after <= before}
                      />
                    );
                  })}
                </div>
              </div>
            )}
            {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
            {ok && <p className="empty-state" style={{ color: "var(--status-good)" }}>Settings saved.</p>}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
