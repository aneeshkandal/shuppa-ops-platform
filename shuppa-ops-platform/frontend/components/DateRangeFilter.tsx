"use client";

import { useEffect, useRef, useState } from "react";
import type { DateRange } from "../lib/api";
import Icon from "./Icon";
import CustomDropdown from "./CustomDropdown";
import CustomDatePicker from "./CustomDatePicker";

type Mode = "all" | "before" | "after" | "between";

function deriveModeAndDates(range: DateRange): { mode: Mode; date1: string; date2: string } {
  if (range.from && range.to) return { mode: "between", date1: range.from, date2: range.to };
  if (range.to && !range.from) return { mode: "before", date1: range.to, date2: "" };
  if (range.from && !range.to) return { mode: "after", date1: range.from, date2: "" };
  return { mode: "all", date1: "", date2: "" };
}

/**
 * Dashboard-wide date filter: "Before" (a single date - shows everything up
 * to and including it), "After" (a single date - everything from it
 * onwards) and "Between" (two dates, inclusive). Always resolves down to a
 * plain {from, to} DateRange that every API call on the page accepts.
 *
 * `value`/`hydrated` are optional and come from FilterContext - when
 * provided, this component syncs its internal mode/date fields from the
 * shared (localStorage-persisted) range exactly once, right after
 * hydration completes. It deliberately does NOT keep re-syncing from
 * `value` on every change after that: `onChange` fires mid-selection (e.g.
 * "Between" with only the first date picked yet), which would otherwise
 * bounce the UI back to a different mode before the user finishes.
 */
export default function DateRangeFilter({
  onChange,
  value,
  hydrated,
}: {
  onChange: (range: DateRange) => void;
  value?: DateRange;
  hydrated?: boolean;
}) {
  const [mode, setMode] = useState<Mode>("all");
  const [date1, setDate1] = useState("");
  const [date2, setDate2] = useState("");
  const syncedRef = useRef(false);

  useEffect(() => {
    if (hydrated && !syncedRef.current) {
      syncedRef.current = true;
      const derived = deriveModeAndDates(value || {});
      setMode(derived.mode);
      setDate1(derived.date1);
      setDate2(derived.date2);
    }
  }, [hydrated, value]);

  const emit = (nextMode: Mode, d1: string, d2: string) => {
    if (nextMode === "all" || (nextMode === "before" && !d1) || (nextMode === "after" && !d1)) {
      onChange({});
      return;
    }
    if (nextMode === "before") {
      onChange({ to: d1 });
    } else if (nextMode === "after") {
      onChange({ from: d1 });
    } else if (nextMode === "between") {
      onChange({ from: d1 || undefined, to: d2 || undefined });
    }
  };

  const handleModeChange = (nextMode: Mode) => {
    setMode(nextMode);
    emit(nextMode, date1, date2);
  };

  const handleDate1Change = (value: string) => {
    setDate1(value);
    emit(mode, value, date2);
  };

  const handleDate2Change = (value: string) => {
    setDate2(value);
    emit(mode, date1, value);
  };

  const clear = () => {
    setMode("all");
    setDate1("");
    setDate2("");
    onChange({});
  };

  return (
    <div className="date-filter">
      <CustomDropdown
        variant="inline"
        ariaLabel="Date filter mode"
        value={mode}
        onChange={(v) => handleModeChange(v as Mode)}
        options={[
          { value: "all", label: "All dates" },
          { value: "before", label: "Before" },
          { value: "after", label: "After" },
          { value: "between", label: "Between" },
        ]}
      />
      {(mode === "before" || mode === "after" || mode === "between") && (
        <CustomDatePicker variant="inline" ariaLabel="Date" value={date1} onChange={handleDate1Change} />
      )}
      {mode === "between" && (
        <>
          <span style={{ color: "var(--text-muted)", fontSize: 12 }}>and</span>
          <CustomDatePicker variant="inline" ariaLabel="End date" value={date2} onChange={handleDate2Change} />
        </>
      )}
      {mode !== "all" && (
        <button
          className="date-filter-clear"
          onClick={clear}
          type="button"
          title="Clear date filter"
          aria-label="Clear date filter"
        >
          <Icon name="x" size={12} strokeWidth={2.4} />
        </button>
      )}
    </div>
  );
}
