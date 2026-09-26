"use client";

import { useState } from "react";
import { returnsApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import DataTable from "../../components/DataTable";
import StatusPill from "../../components/StatusPill";
import FileReturnModal from "./FileReturnModal";
import SupplierReturnDetailModal from "./SupplierReturnDetailModal";

/**
 * "Supplier Returns" card for the Supplier Summary page - tracks deliveries
 * that included wrong or extra items and still need resolving (returned to
 * the supplier, generated as a proper PO, or onboarded as a new catalog
 * product). Unlike this dashboard's other tables, this one starts genuinely
 * empty: it's only ever populated by real filings, not synthetic/backfilled
 * data - see backend/app/services/returns_service.py.
 */
export default function SupplierReturnsCard({ warehouseId }: { warehouseId?: number }) {
  const [fileOpen, setFileOpen] = useState(false);
  const [selectedReturnId, setSelectedReturnId] = useState<number | null>(null);

  const returns = useApi(() => returnsApi.list(warehouseId), [warehouseId]);

  return (
    <>
    <div className="card">
      <div className="chart-card-header">
        <h3>Supplier Returns</h3>
        <button type="button" className="btn-primary btn-small" onClick={() => setFileOpen(true)}>
          File a Return
        </button>
      </div>

      {returns.loading && <LoadingState />}
      {returns.error && <ErrorState message={returns.error} onRetry={returns.reload} />}
      {returns.data && (
        <DataTable
          keyField="return_id"
          rows={returns.data}
          pageSize={10}
          emptyMessage="No supplier returns filed yet."
          onRowClick={(r) => setSelectedReturnId(r.return_id)}
          activeRowKey={selectedReturnId ?? undefined}
          columns={[
            { key: "return_id", header: "Return ID" },
            { key: "supplier_name", header: "Supplier" },
            {
              key: "filed_at",
              header: "Form Filled",
              render: (r) => new Date(r.filed_at).toLocaleDateString(),
            },
            {
              key: "scheduled_return_date",
              header: "Return Scheduled",
              render: (r) => (r.scheduled_return_date ? new Date(r.scheduled_return_date).toLocaleDateString() : "—"),
            },
            { key: "item_count", header: "Items", align: "right" },
            {
              key: "pending_count",
              header: "Status",
              render: (r) => (
                <StatusPill status={r.pending_count > 0 ? "PENDING" : "RESOLVED"} />
              ),
            },
          ]}
        />
      )}
      <p className="empty-state" style={{ padding: "8px 0 0" }}>
        Click a row to see or resolve its items.
      </p>
    </div>

    {/* Rendered outside the .card wrapper on purpose: .card has
        backdrop-filter (for its glass look), and per the CSS spec, filter/
        backdrop-filter/transform on an ancestor makes a `position: fixed`
        descendant position itself relative to THAT ancestor's box instead of
        the real viewport - trapping the modal inside the card instead of
        overlaying the whole page (this is exactly what LocationDetailModal
        already avoids by living outside every .card, at the page's top
        level - see app/storage/page.tsx). */}
    {fileOpen && (
      <FileReturnModal
        warehouseId={warehouseId}
        onClose={() => setFileOpen(false)}
        onFiled={() => {
          setFileOpen(false);
          returns.reload();
        }}
      />
    )}

    <SupplierReturnDetailModal
      returnId={selectedReturnId}
      onClose={() => setSelectedReturnId(null)}
      onResolved={returns.reload}
    />
    </>
  );
}
