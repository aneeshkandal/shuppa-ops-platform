"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { returnsApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useAuth } from "../../lib/auth";
import { LoadingState, ErrorState } from "../../components/LoadingState";
import StatusPill from "../../components/StatusPill";
import Icon from "../../components/Icon";

/**
 * Detail view for one filed supplier return - opened by clicking a supplier
 * name in SupplierReturnsCard. Shows every line item with its resolution
 * state; an ADMIN sees action buttons to resolve a still-PENDING item:
 *
 *  - "Mark Returned" - always available.
 *  - "Generate PO" - only when the item is a recognized catalog product
 *    (product_id is set) - reuses the Draft PO mechanism.
 *  - "List as New Product" - only when the item has NO product_id - sends
 *    the admin to the Add Product form pre-filled with the reported name;
 *    once that form succeeds it calls back here to finish the resolution
 *    (see admin/products/page.tsx's ?return_item_id handling).
 *
 * A WAREHOUSE user sees the same detail (read-only) but never the resolve
 * buttons - resolving is explicitly an admin action per the feature request.
 */
export default function SupplierReturnDetailModal({
  returnId,
  onClose,
  onResolved,
}: {
  returnId: number | null;
  onClose: () => void;
  onResolved: () => void;
}) {
  const { user } = useAuth();
  const router = useRouter();
  const [actionError, setActionError] = useState<string | null>(null);
  const [resolvingId, setResolvingId] = useState<number | null>(null);

  const detail = useApi(() => (returnId ? returnsApi.detail(returnId) : Promise.resolve(null)), [returnId]);

  useEffect(() => {
    if (!returnId) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [returnId, onClose]);

  if (!returnId) return null;

  const r = detail.data;
  const isAdmin = user?.role === "ADMIN";

  const resolve = async (returnItemId: number, resolution: "RETURNED" | "PO_GENERATED") => {
    setActionError(null);
    setResolvingId(returnItemId);
    try {
      await returnsApi.resolveItem(returnItemId, { resolution });
      detail.reload();
      onResolved();
    } catch (e: any) {
      setActionError(e?.message || "Could not resolve this item.");
    } finally {
      setResolvingId(null);
    }
  };

  const listAsNewProduct = (item: any) => {
    router.push(
      `/admin/products?product_name=${encodeURIComponent(item.product_name_reported)}&return_item_id=${item.return_item_id}`
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">{r ? `Return #${r.return_id} – ${r.supplier_name}` : "Return details"}</div>
            {r && (
              <div className="modal-subtitle">
                Filed by {r.filed_by} on {new Date(r.filed_at).toLocaleDateString()}
                {r.scheduled_return_date ? ` · Return scheduled ${new Date(r.scheduled_return_date).toLocaleDateString()}` : ""}
              </div>
            )}
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close" type="button">
            <Icon name="x" size={20} />
          </button>
        </div>

        {detail.loading && <LoadingState />}
        {detail.error && <ErrorState message={detail.error} onRetry={detail.reload} />}

        {r && (
          <>
            {r.note && (
              <p className="empty-state" style={{ padding: "0 0 10px" }}>
                Note: {r.note}
              </p>
            )}
            {actionError && (
              <p className="empty-state" style={{ color: "var(--status-critical)" }}>
                {actionError}
              </p>
            )}
            <div className="chart-card-header">
              <h3>Items ({r.items.length})</h3>
            </div>
            {r.items.map((item: any) => (
              <div className="location-product-row" key={item.return_item_id} style={{ alignItems: "flex-start" }}>
                <div>
                  <div className="location-product-name">
                    {item.product_name_reported}
                    {item.product_id ? ` (product #${item.product_id})` : ""}
                  </div>
                  <div className="location-product-meta">
                    Qty {item.quantity} · {item.reason === "WRONG_PRODUCT" ? "Wrong product" : "Extra product"}
                    {item.linked_draft_po_id ? ` · Draft PO #${item.linked_draft_po_id}` : ""}
                    {item.created_product_id ? ` · Listed as product #${item.created_product_id}` : ""}
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                  <StatusPill status={item.resolution} />
                  {isAdmin && item.resolution === "PENDING" && (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        type="button"
                        className="btn-secondary btn-small"
                        disabled={resolvingId === item.return_item_id}
                        onClick={() => resolve(item.return_item_id, "RETURNED")}
                      >
                        Mark Returned
                      </button>
                      {item.product_id ? (
                        <button
                          type="button"
                          className="btn-secondary btn-small"
                          disabled={resolvingId === item.return_item_id}
                          onClick={() => resolve(item.return_item_id, "PO_GENERATED")}
                        >
                          Generate PO
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn-secondary btn-small"
                          disabled={resolvingId === item.return_item_id}
                          onClick={() => listAsNewProduct(item)}
                        >
                          List as New Product
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
