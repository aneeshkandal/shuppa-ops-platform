"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { searchApi } from "../lib/api";
import Icon from "./Icon";

type Results = { products: any[]; suppliers: any[] };

/**
 * App-wide "jump to" search (products/suppliers by name) - rendered inside
 * TopBar (alongside each page's own filters) so it's part of the same
 * sticky header bar on every page, rather than floating in a separate strip
 * above it. Not a full-text search engine, just a quick way to get to the
 * page that has more detail on a given product or supplier (see
 * backend/app/services/search_service.py).
 */
export default function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [rect, setRect] = useState<{ top: number; left: number } | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    setLoading(true);
    const handle = setTimeout(() => {
      searchApi
        .search(query.trim())
        .then((r) => setResults(r))
        .catch(() => setResults(null))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  const showDropdown = open && query.trim().length >= 2;

  // Positioned via a portal onto <body> (fixed, computed from the search
  // box's own bounding rect) rather than the plain `position: absolute`
  // this used before - so it can never end up clipped by an ancestor
  // .card's or .modal-card's overflow/backdrop-filter (see
  // components/CustomDropdown.tsx for the full rationale; this dropdown
  // predates that component but gets the same fix here).
  useEffect(() => {
    if (!showDropdown) return;
    const computeRect = () => {
      const el = boxRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const panelWidth = 320;
      const left = Math.max(12, Math.min(r.right - panelWidth, window.innerWidth - panelWidth - 12));
      setRect({ top: r.bottom + 6, left });
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

  const goToProduct = (p: any) => {
    setOpen(false);
    setQuery("");
    router.push(`/storage?search=${encodeURIComponent(p.product_name)}`);
  };

  const goToSupplier = (s: any) => {
    setOpen(false);
    setQuery("");
    router.push(`/suppliers?supplier_id=${s.supplier_id}&supplier_name=${encodeURIComponent(s.supplier_name)}`);
  };

  const hasResults = results && (results.products.length > 0 || results.suppliers.length > 0);

  return (
    <div className="global-search" ref={boxRef}>
      <span className="global-search-icon">
        <Icon name="search" size={15} />
      </span>
      <input
        type="text"
        className="global-search-input"
        placeholder="Search products or suppliers..."
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
            style={{ position: "fixed", top: rect.top, left: rect.left, right: "auto" }}
          >
            {loading && <div className="global-search-empty">Searching...</div>}
            {!loading && !hasResults && <div className="global-search-empty">No matches for "{query}".</div>}
            {!loading && results && results.products.length > 0 && (
              <div className="global-search-group">
                <div className="global-search-group-label">Products</div>
                {results.products.map((p: any) => (
                  <button key={p.product_id} type="button" className="global-search-item" onClick={() => goToProduct(p)}>
                    <span>{p.product_name}</span>
                    <span className="global-search-item-meta">{p.category || ""}</span>
                  </button>
                ))}
              </div>
            )}
            {!loading && results && results.suppliers.length > 0 && (
              <div className="global-search-group">
                <div className="global-search-group-label">Suppliers</div>
                {results.suppliers.map((s: any) => (
                  <button key={s.supplier_id} type="button" className="global-search-item" onClick={() => goToSupplier(s)}>
                    <span>{s.supplier_name}</span>
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
