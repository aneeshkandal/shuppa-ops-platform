"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import type { DateRange } from "./api";

const WAREHOUSE_KEY = "shuppa_filter_warehouse_id";
const RANGE_KEY = "shuppa_filter_range";

interface FilterContextValue {
  warehouseId: number | undefined;
  setWarehouseId: (id: number | undefined) => void;
  range: DateRange;
  setRange: (range: DateRange) => void;
  /** True once the one-time localStorage read (see below) has completed -
   * components that keep their own derived local state from `range` (only
   * DateRangeFilter does this) use it to sync themselves exactly once. */
  hydrated: boolean;
}

const FilterContext = createContext<FilterContextValue | undefined>(undefined);

/**
 * Shared warehouse + date-range filter state, persisted to localStorage so
 * picking "Kimmage" + "Last 30 days" on one page carries over when the user
 * switches to another dashboard page (previously every page re-derived its
 * own filters from scratch via a local useState, defaulting back to "All
 * Warehouses" / "All dates" on every navigation).
 *
 * localStorage can't be read during server-side rendering, so this starts
 * with the same defaults SSR would use and corrects itself in an effect
 * right after mount - a brief flash of "All Warehouses" before the saved
 * value applies, which is an acceptable trade-off for an internal tool
 * versus the complexity of avoiding a hydration mismatch entirely.
 */
export function FilterProvider({ children }: { children: ReactNode }) {
  const [warehouseId, setWarehouseIdState] = useState<number | undefined>(undefined);
  const [range, setRangeState] = useState<DateRange>({});
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const storedWarehouse = window.localStorage.getItem(WAREHOUSE_KEY);
      if (storedWarehouse && storedWarehouse !== "all") {
        const parsed = Number(storedWarehouse);
        if (!Number.isNaN(parsed)) setWarehouseIdState(parsed);
      }
      const storedRange = window.localStorage.getItem(RANGE_KEY);
      if (storedRange) {
        const parsed = JSON.parse(storedRange);
        if (parsed && typeof parsed === "object") setRangeState(parsed);
      }
    } catch {
      /* localStorage unavailable/blocked - fall back to defaults silently */
    } finally {
      setHydrated(true);
    }
  }, []);

  const setWarehouseId = (id: number | undefined) => {
    setWarehouseIdState(id);
    try {
      window.localStorage.setItem(WAREHOUSE_KEY, id === undefined ? "all" : String(id));
    } catch {
      /* ignore */
    }
  };

  const setRange = (r: DateRange) => {
    setRangeState(r);
    try {
      window.localStorage.setItem(RANGE_KEY, JSON.stringify(r));
    } catch {
      /* ignore */
    }
  };

  return (
    <FilterContext.Provider value={{ warehouseId, setWarehouseId, range, setRange, hydrated }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error("useFilters must be used within FilterProvider");
  return ctx;
}
