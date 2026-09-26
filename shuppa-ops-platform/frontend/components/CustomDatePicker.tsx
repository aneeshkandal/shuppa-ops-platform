"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";

type Variant = "form" | "pill" | "inline";

const WEEKDAY_LABELS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Parses a native-date-input-style "YYYY-MM-DD" string into a local Date
 * (midnight local time) - deliberately NOT `new Date(str)`, which parses a
 * bare "YYYY-MM-DD" as UTC midnight and can silently read back as the
 * previous day once `.getDate()` runs in a negative-UTC-offset timezone. */
function parseISODate(value: string | undefined): Date | null {
  if (!value) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return null;
  const [, y, mo, d] = m;
  return new Date(Number(y), Number(mo) - 1, Number(d));
}

function formatISODate(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function sameDay(a: Date | null, b: Date | null): boolean {
  if (!a || !b) return false;
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function daysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

type Cell = { date: Date; inMonth: boolean };

/** Monday-first 6-or-fewer-row grid, padded with the trailing days of the
 * previous/next month (grayed out, but still clickable - clicking one just
 * navigates to that month, standard date-picker behavior) so every row is a
 * complete week. */
function buildGrid(viewYear: number, viewMonth: number): Cell[] {
  const firstWeekday = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7; // Mon=0..Sun=6
  const total = daysInMonth(viewYear, viewMonth);
  const cells: Cell[] = [];
  for (let i = firstWeekday; i > 0; i--) {
    cells.push({ date: new Date(viewYear, viewMonth, 1 - i), inMonth: false });
  }
  for (let d = 1; d <= total; d++) {
    cells.push({ date: new Date(viewYear, viewMonth, d), inMonth: true });
  }
  let next = 1;
  while (cells.length % 7 !== 0) {
    cells.push({ date: new Date(viewYear, viewMonth + 1, next), inMonth: false });
    next += 1;
  }
  return cells;
}

/**
 * Custom-built replacement for a native <input type="date">: same
 * value/onChange contract as the native input (an ISO "YYYY-MM-DD" string,
 * or "" for no date), but renders its own trigger button plus a floating
 * calendar panel, so every date field in the app shares one look instead of
 * each browser/OS drawing its own native picker (see CustomDropdown.tsx,
 * which this mirrors closely, for the sibling rollout on <select>s).
 *
 * The panel is rendered through a React portal onto <body>, positioned with
 * `position: fixed` computed from the trigger's own bounding rect - for the
 * same reason as CustomDropdown: a `position: fixed` descendant of any
 * `.card`'s `backdrop-filter` would otherwise anchor itself to that card's
 * box instead of the real viewport, which is what used to trap floating
 * panels behind later cards. Portaling to `document.body` sidesteps that
 * regardless of how deeply nested the trigger is.
 *
 * Keyboard handling lives entirely on the trigger button, not the panel -
 * DOM focus never leaves the trigger while the panel is open, matching
 * CustomDropdown's approach (an `activeDate` in state drives the visual
 * "which day is focused" highlight instead of moving real focus between 42
 * day cells).
 */
export default function CustomDatePicker({
  value,
  onChange,
  variant = "form",
  placeholder = "Select date...",
  disabled,
  className,
  ariaLabel,
  id,
}: {
  value: string | undefined;
  onChange: (value: string) => void;
  variant?: Variant;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
  id?: string;
}) {
  const selected = parseISODate(value);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [rect, setRect] = useState<{ top: number; bottom: number; left: number; width: number; openUp: boolean } | null>(null);
  const [viewDate, setViewDate] = useState<Date>(selected || new Date());
  const [activeDate, setActiveDate] = useState<Date>(selected || new Date());
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const computeRect = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < 340 && r.top > spaceBelow;
    setRect({ top: r.top, bottom: r.bottom, left: r.left, width: r.width, openUp });
  }, []);

  const closePanel = useCallback(() => setOpen(false), []);

  const openPanel = () => {
    if (disabled) return;
    const base = selected || new Date();
    setViewDate(new Date(base.getFullYear(), base.getMonth(), 1));
    setActiveDate(base);
    computeRect();
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      closePanel();
    };
    const onScrollOrResize = (e: Event) => {
      // Ignore scrolling inside the panel itself; only close for scrolling
      // elsewhere on the page, which would otherwise leave the panel
      // visually detached from its trigger (position is computed on open).
      if (panelRef.current && e.target instanceof Node && panelRef.current.contains(e.target)) return;
      closePanel();
    };
    document.addEventListener("mousedown", onDocMouseDown);
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open, closePanel]);

  const pickDate = (date: Date) => {
    onChange(formatISODate(date));
    closePanel();
    triggerRef.current?.focus();
  };

  const clearDate = () => {
    onChange("");
    closePanel();
    triggerRef.current?.focus();
  };

  const shiftMonth = (delta: number) => {
    setViewDate((d) => new Date(d.getFullYear(), d.getMonth() + delta, 1));
    setActiveDate((a) => {
      const targetMonth = viewDate.getMonth() + delta;
      const targetYear = viewDate.getFullYear() + Math.floor(targetMonth / 12);
      const normalizedMonth = ((targetMonth % 12) + 12) % 12;
      return new Date(targetYear, normalizedMonth, Math.min(a.getDate(), daysInMonth(targetYear, normalizedMonth)));
    });
  };

  const shiftActiveDay = (deltaDays: number) => {
    setActiveDate((a) => {
      const next = new Date(a.getFullYear(), a.getMonth(), a.getDate() + deltaDays);
      if (next.getMonth() !== viewDate.getMonth() || next.getFullYear() !== viewDate.getFullYear()) {
        setViewDate(new Date(next.getFullYear(), next.getMonth(), 1));
      }
      return next;
    });
  };

  const onTriggerKeyDown = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openPanel();
      }
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      shiftActiveDay(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      shiftActiveDay(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      shiftActiveDay(-7);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      shiftActiveDay(7);
    } else if (e.key === "PageUp") {
      e.preventDefault();
      shiftMonth(-1);
    } else if (e.key === "PageDown") {
      e.preventDefault();
      shiftMonth(1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      pickDate(activeDate);
    } else if (e.key === "Escape") {
      e.preventDefault();
      closePanel();
      triggerRef.current?.focus();
    } else if (e.key === "Tab") {
      closePanel();
    }
  };

  const grid = buildGrid(viewDate.getFullYear(), viewDate.getMonth());
  const today = new Date();

  const triggerClass = ["cdp-trigger", `cdp-trigger-${variant}`, disabled ? "cdp-trigger-disabled" : "", className || ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={`cdp cdp-${variant}`}>
      <button
        type="button"
        ref={triggerRef}
        id={id}
        className={triggerClass}
        onClick={() => (open ? closePanel() : openPanel())}
        onKeyDown={onTriggerKeyDown}
        disabled={disabled}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel}
      >
        <span className={`cdp-value${!selected ? " cdp-placeholder" : ""}`}>
          {selected ? selected.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : placeholder}
        </span>
        <Icon name="calendar" size={variant === "inline" ? 12 : 14} strokeWidth={2} className="cdp-icon" />
      </button>

      {mounted &&
        open &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="cdp-panel"
            role="dialog"
            aria-label="Choose a date"
            style={{
              position: "fixed",
              left: rect.left,
              ...(rect.openUp ? { bottom: window.innerHeight - rect.top + 6 } : { top: rect.bottom + 6 }),
              minWidth: Math.max(rect.width, 260),
              maxWidth: "calc(100vw - 24px)",
            }}
          >
            <div className="cdp-header">
              <button type="button" className="cdp-nav" onClick={() => shiftMonth(-1)} aria-label="Previous month">
                <Icon name="chevronLeft" size={14} strokeWidth={2.4} />
              </button>
              <span className="cdp-month-label">
                {viewDate.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
              </span>
              <button type="button" className="cdp-nav" onClick={() => shiftMonth(1)} aria-label="Next month">
                <Icon name="chevronRight" size={14} strokeWidth={2.4} />
              </button>
            </div>

            <div className="cdp-weekdays">
              {WEEKDAY_LABELS.map((w) => (
                <span key={w}>{w}</span>
              ))}
            </div>

            <div className="cdp-grid">
              {grid.map(({ date, inMonth }, idx) => {
                const isSelected = sameDay(date, selected);
                const isToday = sameDay(date, today);
                const isActive = sameDay(date, activeDate);
                return (
                  <button
                    key={idx}
                    type="button"
                    className={`cdp-day${inMonth ? "" : " cdp-day-outside"}${isSelected ? " cdp-day-selected" : ""}${
                      isToday && !isSelected ? " cdp-day-today" : ""
                    }${isActive && !isSelected ? " cdp-day-active" : ""}`}
                    aria-selected={isSelected}
                    aria-label={date.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
                    onClick={() => pickDate(date)}
                    onMouseEnter={() => setActiveDate(date)}
                  >
                    {date.getDate()}
                  </button>
                );
              })}
            </div>

            <div className="cdp-footer">
              <button type="button" className="cdp-footer-btn" onClick={() => pickDate(new Date())}>
                Today
              </button>
              {selected && (
                <button type="button" className="cdp-footer-btn" onClick={clearDate}>
                  Clear
                </button>
              )}
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
