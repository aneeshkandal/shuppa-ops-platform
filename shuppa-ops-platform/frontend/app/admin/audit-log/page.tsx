"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import DataTable from "../../../components/DataTable";
import Icon from "../../../components/Icon";
import { ErrorState, LoadingState } from "../../../components/LoadingState";
import { adminApi } from "../../../lib/api";
import { useApi } from "../../../lib/useApi";
import CustomDropdown from "../../../components/CustomDropdown";
import CustomDatePicker from "../../../components/CustomDatePicker";

export default function AdminAuditLogPage() {
  const [username, setUsername] = useState("");
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const filterOptions = useApi(() => adminApi.getAuditLogFilters(), []);
  const log = useApi(
    () => adminApi.getAuditLog(200, { username: username || undefined, action: action || undefined, dateFrom: dateFrom || undefined, dateTo: dateTo || undefined }),
    [username, action, dateFrom, dateTo]
  );

  const clearFilters = () => {
    setUsername("");
    setAction("");
    setDateFrom("");
    setDateTo("");
  };
  const hasFilters = Boolean(username || action || dateFrom || dateTo);

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Audit Log">
          <button className="btn-secondary btn-small" onClick={() => log.reload()} type="button">
            <Icon name="refreshCw" size={13} /> Refresh
          </button>
        </TopBar>
        <div className="content-area">
          <div className="card admin-table-wrap">
            <div className="chart-card-header">
              <h3>Recent Admin Actions</h3>
            </div>
            <p style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: -6, marginBottom: 10 }}>
              Every admin mutation (adding a warehouse, supplier, product, location, user, or changing settings) is
              recorded here with who did it and when - see backend/app/services/audit_service.py.
            </p>

            <div className="date-filter" style={{ flexWrap: "wrap", marginBottom: 12 }}>
              <CustomDropdown
                variant="inline"
                ariaLabel="Filter by user"
                value={username}
                onChange={setUsername}
                options={[{ value: "", label: "All users" }, ...(filterOptions.data?.usernames || []).map((u) => ({ value: u, label: u }))]}
              />
              <CustomDropdown
                variant="inline"
                ariaLabel="Filter by action"
                value={action}
                onChange={setAction}
                options={[{ value: "", label: "All actions" }, ...(filterOptions.data?.actions || []).map((a) => ({ value: a, label: a }))]}
              />
              <CustomDatePicker variant="inline" ariaLabel="From date" value={dateFrom} onChange={setDateFrom} />
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>to</span>
              <CustomDatePicker variant="inline" ariaLabel="To date" value={dateTo} onChange={setDateTo} />
              {hasFilters && (
                <button
                  className="date-filter-clear"
                  onClick={clearFilters}
                  type="button"
                  title="Clear filters"
                  aria-label="Clear filters"
                >
                  <Icon name="x" size={12} strokeWidth={2.4} />
                </button>
              )}
            </div>

            {log.loading && <LoadingState />}
            {log.error && <ErrorState message={log.error} onRetry={log.reload} />}
            {log.data && (
              <DataTable
                keyField="audit_id"
                rows={log.data}
                pageSize={25}
                csvFilename="admin-audit-log"
                emptyMessage="No admin actions recorded yet."
                columns={[
                  {
                    key: "created_at",
                    header: "When",
                    render: (r) => new Date(r.created_at).toLocaleString(),
                  },
                  { key: "username", header: "User" },
                  { key: "action", header: "Action" },
                  { key: "entity_type", header: "Entity Type" },
                  { key: "entity_id", header: "Entity ID" },
                  { key: "details", header: "Details" },
                ]}
              />
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
