"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { optimizerApi, returnsApi } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import { useAuth } from "../../lib/auth";
import { WAREHOUSES } from "../../lib/api";
import Icon from "../../components/Icon";
import CustomDropdown from "../../components/CustomDropdown";
import CustomDatePicker from "../../components/CustomDatePicker";

type LineItem = {
  product_id?: number;
  product_name_reported: string;
  quantity: string;
  reason: "WRONG_PRODUCT" | "EXTRA_PRODUCT";
};

const emptyItem = (): LineItem => ({ product_name_reported: "", quantity: "1", reason: "WRONG_PRODUCT" });

/**
 * Inline "is this actually a known catalog product?" search for one line
 * item - lets staff match a wrongly-delivered item to an existing product_id
 * (so it can later be resolved as PO_GENERATED) instead of always treating it
 * as brand-new. Mirrors GlobalSearch's debounce pattern, scoped to one row.
 */
function ProductMatchField({
  item,
  onChange,
}: {
  item: LineItem;
  onChange: (patch: Partial<LineItem>) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<any[] | null>(null);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [rect, setRect] = useState<{ top: number; left: number; width: number } | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    const handle = setTimeout(() => {
      optimizerApi
        .products(query.trim(), 8)
        .then((r) => setResults(r))
        .catch(() => setResults(null));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  const showDropdown = open && query.trim().length >= 2;

  // Portaled onto <body> (fixed position, computed from this field's own
  // bounding rect) rather than plain `position: absolute` - this field
  // lives inside FileReturnModal's .modal-card, which has
  // `overflow-y: auto; max-height: 85vh`, so an in-flow absolutely
  // positioned dropdown could get clipped by that scroll box whenever the
  // field sits near the bottom of the visible area. See
  // components/CustomDropdown.tsx for the fuller rationale (same fix,
  // different trigger - a scrollable overflow ancestor here rather than a
  // backdrop-filter one).
  useEffect(() => {
    if (!showDropdown) return;
    const computeRect = () => {
      const el = boxRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      setRect({ top: r.bottom + 4, left: r.left, width: r.width });
    };
    computeRect();
    const onScrollOrResize = (e: Event) => {
      if (panelRef.current && e.target instanceof Node && panelRef.current.contains(e.target)) return;
      setOpen(false);
    };
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [showDropdown]);

  useEffect(() => {
    const onClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (boxRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  if (item.product_id) {
    return (
      <div className="return-item-match matched">
        <Icon name="checkCircle" size={13} />
        <span>Matched to product #{item.product_id}</span>
        <button
          type="button"
          className="btn-secondary btn-small"
          onClick={() => onChange({ product_id: undefined })}
        >
          Unmatch
        </button>
      </div>
    );
  }

  return (
    <div className="return-item-match" ref={boxRef} style={{ position: "relative" }}>
      <input
        type="text"
        placeholder="Search to match an existing product (optional)..."
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
      />
      {mounted &&
        showDropdown &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="global-search-dropdown"
            style={{ position: "fixed", top: rect.top, left: rect.left, width: rect.width, right: "auto" }}
          >
            {results === null && <div className="global-search-empty">Searching...</div>}
            {results && results.length === 0 && <div className="global-search-empty">No matches.</div>}
            {results && results.length > 0 && (
              <div className="global-search-group">
                {results.map((p: any) => (
                  <button
                    key={p.product_id}
                    type="button"
                    className="global-search-item"
                    onClick={() => {
                      onChange({ product_id: p.product_id, product_name_reported: p.product_name });
                      setQuery("");
                      setOpen(false);
                    }}
                  >
                    <span>{p.product_name}</span>
                    <span className="global-search-item-meta">#{p.product_id}</span>
                  </button>
                ))}
              </div>
            )}
          </div>,
          document.body
        )}
    </div>
  );
}

export default function FileReturnModal({
  warehouseId,
  onClose,
  onFiled,
}: {
  /** Currently-selected dashboard warehouse filter, used as the default. */
  warehouseId?: number;
  onClose: () => void;
  onFiled: () => void;
}) {
  const { user } = useAuth();
  const [supplierId, setSupplierId] = useState<number | "">("");
  const [wh, setWh] = useState<number>(user?.role === "WAREHOUSE" ? user.warehouse_id! : warehouseId || 1);
  const [scheduledDate, setScheduledDate] = useState("");
  const [note, setNote] = useState("");
  const [items, setItems] = useState<LineItem[]>([emptyItem()]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const suppliers = useApi(() => returnsApi.suppliers(wh), [wh]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const updateItem = (idx: number, patch: Partial<LineItem>) =>
    setItems((rows) => rows.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const removeItem = (idx: number) => setItems((rows) => rows.filter((_, i) => i !== idx));

  const valid =
    supplierId !== "" &&
    items.length > 0 &&
    items.every((it) => it.product_name_reported.trim() && Number(it.quantity) > 0);

  const submit = async () => {
    if (!valid) return;
    setSaving(true);
    setError(null);
    try {
      await returnsApi.file({
        supplier_id: Number(supplierId),
        warehouse_id: wh,
        scheduled_return_date: scheduledDate || undefined,
        note: note || undefined,
        items: items.map((it) => ({
          product_id: it.product_id,
          product_name_reported: it.product_name_reported.trim(),
          quantity: Number(it.quantity),
          reason: it.reason,
        })),
      });
      onFiled();
    } catch (e: any) {
      setError(e?.message || "Could not file the return.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="modal-title">File a Supplier Return</div>
            <div className="modal-subtitle">Log wrong or extra items a supplier delivered so they can be resolved.</div>
          </div>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close" type="button">
            <Icon name="x" size={20} />
          </button>
        </div>

        <div className="form-grid">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div className="form-field">
              <label>Supplier</label>
              <CustomDropdown
                placeholder="Select a supplier..."
                value={supplierId}
                onChange={(v) => setSupplierId(v ? Number(v) : "")}
                options={(suppliers.data || []).map((s: any) => ({ value: s.supplier_id, label: s.supplier_name }))}
              />
            </div>
            <div className="form-field">
              <label>Warehouse</label>
              <CustomDropdown
                value={wh}
                onChange={(v) => setWh(Number(v))}
                disabled={user?.role === "WAREHOUSE"}
                options={WAREHOUSES.filter((w) => w.id).map((w) => ({ value: w.id!, label: w.name }))}
              />
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div className="form-field">
              <label>Scheduled Return Date (optional)</label>
              <CustomDatePicker ariaLabel="Scheduled Return Date" value={scheduledDate} onChange={setScheduledDate} />
            </div>
            <div className="form-field">
              <label>Note (optional)</label>
              <input type="text" value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
          </div>

          <div className="chart-card-header" style={{ marginTop: 4 }}>
            <h3>Items</h3>
            <button type="button" className="btn-secondary btn-small" onClick={() => setItems((r) => [...r, emptyItem()])}>
              + Add item
            </button>
          </div>

          {items.map((item, idx) => (
            <div key={idx} className="return-item-row">
              <div style={{ display: "grid", gridTemplateColumns: "2fr 0.7fr 1.3fr auto", gap: 8, alignItems: "end" }}>
                <div className="form-field">
                  <label>Product name (as delivered)</label>
                  <input
                    type="text"
                    value={item.product_name_reported}
                    onChange={(e) => updateItem(idx, { product_name_reported: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label>Quantity</label>
                  <input
                    type="number"
                    min={1}
                    value={item.quantity}
                    onChange={(e) => updateItem(idx, { quantity: e.target.value })}
                  />
                </div>
                <div className="form-field">
                  <label>Reason</label>
                  <CustomDropdown
                    value={item.reason}
                    onChange={(v) => updateItem(idx, { reason: v as any })}
                    options={[
                      { value: "WRONG_PRODUCT", label: "Wrong product" },
                      { value: "EXTRA_PRODUCT", label: "Extra product" },
                    ]}
                  />
                </div>
                {items.length > 1 && (
                  <button type="button" className="btn-secondary btn-small" onClick={() => removeItem(idx)}>
                    <Icon name="x" size={13} />
                  </button>
                )}
              </div>
              <ProductMatchField item={item} onChange={(patch) => updateItem(idx, patch)} />
            </div>
          ))}

          <button className="btn-primary" onClick={submit} disabled={saving || !valid}>
            {saving ? "Filing..." : "File Return"}
          </button>
        </div>
        {error && (
          <p className="empty-state" style={{ color: "var(--status-critical)" }}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
