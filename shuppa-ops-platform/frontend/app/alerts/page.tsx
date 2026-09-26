"use client";

import Link from "next/link";
import { useState } from "react";
import AppLayout from "../../components/AppLayout";
import TopBar from "../../components/TopBar";
import WarehouseSelect from "../../components/WarehouseSelect";
import KpiCard from "../../components/KpiCard";
import DataTable from "../../components/DataTable";
import Icon, { IconName } from "../../components/Icon";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import LastUpdated from "../../components/LastUpdated";
import { alertsApi, WAREHOUSES } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useAuth } from "../../lib/auth";
import { useFilters } from "../../lib/FilterContext";

// Re-poll every 30s so newly-fired alerts show up without a manual refresh -
// this is a fixed-interval poll, not a real push channel (see README for why).
const ALERTS_POLL_MS = 30_000;

const LEVEL_ICON: Record<string, IconName> = {
  critical: "alertOctagon",
  serious: "alertTriangle",
  warning: "alertTriangle",
};

const LEVEL_COLOR: Record<string, string> = {
  critical: "#d03b3b",
  serious: "#ec835a",
  warning: "#fab219",
};

const LEVEL_LABEL: Record<string, string> = {
  critical: "Critical",
  serious: "Serious",
  warning: "Warning",
};

export default function AlertsCenterPage() {
  const { warehouseId, setWarehouseId } = useFilters();
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";
  const alerts = useApi(() => alertsApi.all(warehouseId), [warehouseId], { refreshInterval: ALERTS_POLL_MS });

  // Only admins can resolve/roll back, so only fetch the Resolved tab's data
  // for them - it's a 403 for anyone else, and the tab itself isn't shown.
  const resolved = useApi(
    () => (isAdmin ? alertsApi.resolved(warehouseId) : Promise.resolve([])),
    [warehouseId, isAdmin]
  );

  const [tab, setTab] = useState<"active" | "resolved">("active");
  const [resolvingKey, setResolvingKey] = useState<string | null>(null);
  const [resolveErrors, setResolveErrors] = useState<Record<string, string>>({});
  const [rollingBackKey, setRollingBackKey] = useState<string | null>(null);
  const [rollbackErrors, setRollbackErrors] = useState<Record<string, string>>({});

  // Alerts have no id (they're recomputed live, not stored rows - see
  // alerts_service.get_all_alerts) - title is unique across the fixed set of
  // alert types this app produces. When "All Warehouses" is selected, the
  // backend now fans this out into each real warehouse's own alerts (see
  // alerts_service._compute_alerts), so an alert's OWN `warehouse_id` (not
  // just the page's filter) is part of what makes a row unique - the same
  // title can legitimately appear once per warehouse where it's actually
  // true. Falls back to the page's filter for a single selected warehouse,
  // where alerts aren't individually tagged since there's only one scope.
  const keyFor = (a: any) => `${a.title}::${a.warehouse_id ?? warehouseId ?? "all"}`;

  // A resolved row's own warehouse_id is always a real warehouse id now
  // (the merged "All Warehouses" view never writes to the old pseudo
  // "all warehouses" scope - see alerts_service.get_resolved_alerts).
  const warehouseLabel = (r: any): string | undefined =>
    r.warehouse_name || WAREHOUSES.find((w) => w.id === r.warehouse_id)?.name;

  const handleResolve = async (a: any) => {
    const key = keyFor(a);
    setResolvingKey(key);
    setResolveErrors((errs) => {
      const next = { ...errs };
      delete next[key];
      return next;
    });
    try {
      // Resolve against the alert's own real warehouse when it's tagged
      // with one (the merged "All Warehouses" view) so resolving one
      // warehouse's Overstocked Locations alert doesn't affect another's.
      await alertsApi.resolve(a.title, a.warehouse_id ?? warehouseId, a.count);
      alerts.reload();
      resolved.reload();
    } catch (e: any) {
      setResolveErrors((errs) => ({ ...errs, [key]: e?.message || "Could not resolve this alert." }));
    } finally {
      setResolvingKey(null);
    }
  };

  const handleRollback = async (r: any) => {
    const key = String(r.alert_resolution_id);
    setRollingBackKey(key);
    setRollbackErrors((errs) => {
      const next = { ...errs };
      delete next[key];
      return next;
    });
    try {
      await alertsApi.rollback(r.title, r.warehouse_id ?? warehouseId);
      resolved.reload();
      alerts.reload();
    } catch (e: any) {
      setRollbackErrors((errs) => ({ ...errs, [key]: e?.message || "Could not roll back this alert." }));
    } finally {
      setRollingBackKey(null);
    }
  };

  const resolvedStatus = (r: any): { label: string; color: string } => {
    if (r.current_count === null || r.current_count === undefined) {
      return { label: "Condition cleared", color: "var(--status-good)" };
    }
    if (r.reappeared) {
      return { label: "Reappeared automatically", color: "var(--status-warning)" };
    }
    return { label: "Still hidden", color: "var(--text-muted)" };
  };

  const counts = (alerts.data || []).reduce(
    (acc: Record<string, number>, a: any) => {
      acc[a.level] = (acc[a.level] || 0) + 1;
      return acc;
    },
    {}
  );

  return (
    <AppLayout>
      <TopBar title="Alerts Center">
        <WarehouseSelect value={warehouseId} onChange={setWarehouseId} />
        <LastUpdated timestamp={alerts.lastUpdated} onRefresh={() => alerts.reload()} />
      </TopBar>
      <div className="content-area">
        <div className="kpi-row">
          <KpiCard icon="alertOctagon" label="Critical" value={String(counts.critical || 0)} accent={LEVEL_COLOR.critical} />
          <KpiCard icon="alertTriangle" label="Serious" value={String(counts.serious || 0)} accent={LEVEL_COLOR.serious} />
          <KpiCard icon="alertTriangle" label="Warning" value={String(counts.warning || 0)} accent={LEVEL_COLOR.warning} />
          <KpiCard icon="bell" label="Total Active Alerts" value={String(alerts.data?.length ?? 0)} />
        </div>

        <div className="card">
          <div className="chart-card-header">
            <h3>{tab === "active" ? "All Alerts (across every domain, sorted by severity)" : "Resolved Alerts"}</h3>
          </div>

          {isAdmin && (
            <div className="insight-tabs">
              <button
                type="button"
                className={`insight-tab${tab === "active" ? " active" : ""}`}
                onClick={() => setTab("active")}
              >
                Active{alerts.data && alerts.data.length > 0 ? ` (${alerts.data.length})` : ""}
              </button>
              <button
                type="button"
                className={`insight-tab${tab === "resolved" ? " active" : ""}`}
                onClick={() => setTab("resolved")}
              >
                Resolved{resolved.data && resolved.data.length > 0 ? ` (${resolved.data.length})` : ""}
              </button>
            </div>
          )}

          {tab === "resolved" ? (
            <>
              {resolved.loading && <LoadingState label="Loading resolved alerts..." />}
              {resolved.error && <ErrorState message={resolved.error} onRetry={resolved.reload} />}
              {resolved.data && (
                <DataTable
                  keyField="alert_resolution_id"
                  rows={resolved.data}
                  emptyMessage="No alerts have been resolved yet."
                  columns={[
                    { key: "title", header: "Alert" },
                    {
                      key: "warehouse",
                      header: "Warehouse",
                      sortable: false,
                      render: (r) => warehouseLabel(r) || <span style={{ color: "var(--text-muted)" }}>—</span>,
                    },
                    { key: "resolved_count", header: "Count when resolved", align: "center" },
                    {
                      key: "status",
                      header: "Status",
                      sortable: false,
                      render: (r) => {
                        const s = resolvedStatus(r);
                        return (
                          <span className="status-pill" style={{ borderColor: s.color, color: s.color }}>
                            {s.label}
                          </span>
                        );
                      },
                    },
                    { key: "resolved_by", header: "Resolved by" },
                    {
                      key: "resolved_at",
                      header: "Resolved at",
                      render: (r) => new Date(r.resolved_at).toLocaleString(),
                    },
                    {
                      key: "actions",
                      header: "",
                      sortable: false,
                      render: (r) => (
                        <>
                          <button
                            type="button"
                            className="btn-secondary btn-small"
                            disabled={rollingBackKey === String(r.alert_resolution_id)}
                            onClick={() => handleRollback(r)}
                            title="Undo this resolution - the alert shows again immediately if its condition still holds"
                          >
                            {rollingBackKey === String(r.alert_resolution_id) ? (
                              "Rolling back..."
                            ) : (
                              <>
                                <Icon name="refreshCw" size={12} /> Roll back
                              </>
                            )}
                          </button>
                          {rollbackErrors[String(r.alert_resolution_id)] && (
                            <div style={{ marginTop: 4, color: "var(--status-critical)", fontSize: 11.5 }}>
                              {rollbackErrors[String(r.alert_resolution_id)]}
                            </div>
                          )}
                        </>
                      ),
                    },
                  ]}
                />
              )}
            </>
          ) : (
            <>
              {alerts.loading && <LoadingState label="Checking every domain for active alerts..." />}
              {alerts.error && <ErrorState message={alerts.error} onRetry={alerts.reload} />}
              {alerts.data && alerts.data.length === 0 && (
                <p className="empty-state">Nothing needs attention right now.</p>
              )}
              {alerts.data?.map((a: any, i: number) => (
                <div className="alert-item" key={i}>
                  <span
                    className="alert-icon"
                    style={{
                      color: LEVEL_COLOR[a.level] || "#8a869c",
                      background: `${LEVEL_COLOR[a.level] || "#8a869c"}1f`,
                    }}
                  >
                    <Icon name={LEVEL_ICON[a.level] || "alertTriangle"} size={15} />
                  </span>
                  <div style={{ flex: 1 }}>
                    <div className="alert-title">
                      {a.title}
                      <span
                        className="status-pill"
                        style={{
                          marginLeft: 8,
                          fontSize: 10.5,
                          verticalAlign: "middle",
                          borderColor: a.level === "critical" ? "#d03b3b" : a.level === "serious" ? "#ec835a" : "#fab219",
                          color: a.level === "critical" ? "#d03b3b" : a.level === "serious" ? "#ec835a" : "#fab219",
                        }}
                      >
                        {LEVEL_LABEL[a.level] || a.level}
                      </span>
                      {/* Only set when viewing "All Warehouses" - each alert
                          is tagged with the real warehouse it actually fired
                          in (see alerts_service._compute_alerts), since the
                          same alert title can be true at more than one
                          warehouse at once. */}
                      {a.warehouse_name && (
                        <span
                          className="reason-tag"
                          style={{
                            marginLeft: 6,
                            verticalAlign: "middle",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 4,
                            fontWeight: 600,
                          }}
                        >
                          <Icon name="building" size={11} />
                          {a.warehouse_name}
                        </span>
                      )}
                    </div>
                    <div className="alert-detail">{a.detail}</div>
                    {a.hint && (
                      <div
                        className="alert-detail"
                        style={{ marginTop: 4, fontStyle: "italic", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 5 }}
                      >
                        <Icon name="lightbulb" size={12} /> {a.hint}
                      </div>
                    )}
                    <div className="alert-detail" style={{ marginTop: 4, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                      <Link href={a.link || "#"} className="btn-secondary btn-small" style={{ textDecoration: "none" }}>
                        View in {a.source} <Icon name="arrowRight" size={12} />
                      </Link>
                      {isAdmin && (
                        <button
                          type="button"
                          className="btn-secondary btn-small"
                          disabled={resolvingKey === keyFor(a)}
                          onClick={() => handleResolve(a)}
                          title="Hide this alert until its numbers change"
                        >
                          {resolvingKey === keyFor(a) ? (
                            "Resolving..."
                          ) : (
                            <>
                              <Icon name="check" size={12} /> Resolve
                            </>
                          )}
                        </button>
                      )}
                    </div>
                    {resolveErrors[keyFor(a)] && (
                      <div className="alert-detail" style={{ marginTop: 4, color: "var(--status-critical)" }}>
                        {resolveErrors[keyFor(a)]}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
