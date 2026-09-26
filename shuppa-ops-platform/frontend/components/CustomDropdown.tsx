"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { createPortal } from "react-dom";
import Icon from "./Icon";

export type DropdownOption = {
  value: string | number;
  label: string;
  disabled?: boolean;
};

type Variant = "form" | "pill" | "inline";

/**
 * Custom-built replacement for a native <select>: same value/onChange
 * contract (onChange gets the option's value as a string, matching a native
 * select's e.target.value), but renders its own trigger button plus a
 * floating options panel - which is what lets it show a checkmark on the
 * selected option, an open/close animation, and an exact accent-color hover
 * that a native <select>'s OS-drawn popup can't be styled to do.
 *
 * The options panel is rendered through a React portal onto <body>,
 * positioned with `position: fixed` computed from the trigger's own
 * bounding rect - deliberately, not incidentally. Several places in this
 * app (any .card) use `backdrop-filter`, which per the CSS spec makes a
 * `position: fixed` *descendant* position itself relative to that
 * ancestor's box instead of the real viewport - the exact bug that trapped
 * the Supplier Returns modals behind later cards (see
 * app/suppliers/SupplierReturnsCard.tsx's comment on this). Portaling to
 * `document.body` sidesteps that trap entirely, so this dropdown's panel
 * can never end up rendered behind a card no matter how deeply nested the
 * trigger is.
 */
export default function CustomDropdown({
  value,
  onChange,
  options,
  placeholder = "Select...",
  variant = "form",
  disabled,
  className,
  ariaLabel,
  id,
}: {
  value: string | number | undefined;
  onChange: (value: string) => void;
  options: DropdownOption[];
  placeholder?: string;
  variant?: Variant;
  disabled?: boolean;
  className?: string;
  ariaLabel?: string;
  id?: string;
}) {
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [rect, setRect] = useState<{ top: number; bottom: number; left: number; width: number; openUp: boolean } | null>(null);
  const [activeIndex, setActiveIndex] = useState(-1);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => setMounted(true), []);

  const selectedIndex = options.findIndex((o) => String(o.value) === String(value ?? ""));
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;

  const computeRect = useCallback(() => {
    const el = triggerRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const spaceBelow = window.innerHeight - r.bottom;
    const openUp = spaceBelow < 260 && r.top > spaceBelow;
    setRect({ top: r.top, bottom: r.bottom, left: r.left, width: r.width, openUp });
  }, []);

  const closePanel = useCallback(() => setOpen(false), []);

  const openPanel = () => {
    if (disabled || options.length === 0) return;
    computeRect();
    setActiveIndex(selectedIndex >= 0 ? selectedIndex : 0);
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
      // Ignore scrolling that happens inside the panel itself (a long
      // option list scrolling) - only close for scrolling elsewhere on the
      // page, which would leave the panel visually detached from its
      // trigger since position is computed once on open.
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

  const selectIndex = (idx: number) => {
    const opt = options[idx];
    if (!opt || opt.disabled) return;
    onChange(String(opt.value));
    closePanel();
    triggerRef.current?.focus();
  };

  const moveActive = (dir: 1 | -1) => {
    setActiveIndex((i) => {
      if (options.length === 0) return i;
      let next = i;
      for (let step = 0; step < options.length; step++) {
        next = (next + dir + options.length) % options.length;
        if (!options[next]?.disabled) return next;
      }
      return i;
    });
  };

  const onTriggerKeyDown = (e: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (!open) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openPanel();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      moveActive(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      moveActive(-1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      selectIndex(activeIndex);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveIndex(options.length - 1);
    } else if (e.key === "Escape") {
      e.preventDefault();
      closePanel();
      triggerRef.current?.focus();
    } else if (e.key === "Tab") {
      closePanel();
    }
  };

  const triggerClass = ["cd-trigger", `cd-trigger-${variant}`, disabled ? "cd-trigger-disabled" : "", className || ""]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={`cd cd-${variant}`}>
      <button
        type="button"
        ref={triggerRef}
        id={id}
        className={triggerClass}
        onClick={() => (open ? closePanel() : openPanel())}
        onKeyDown={onTriggerKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
      >
        <span className={`cd-value${!selected ? " cd-placeholder" : ""}`}>{selected ? selected.label : placeholder}</span>
        <Icon
          name="chevronDown"
          size={variant === "inline" ? 12 : 14}
          strokeWidth={2}
          className={`cd-chevron${open ? " cd-chevron-open" : ""}`}
        />
      </button>

      {mounted &&
        open &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            className="cd-panel"
            role="listbox"
            style={{
              position: "fixed",
              left: rect.left,
              ...(rect.openUp
                ? { bottom: window.innerHeight - rect.top + 6 }
                : { top: rect.bottom + 6 }),
              minWidth: rect.width,
              maxWidth: "calc(100vw - 24px)",
            }}
          >
            {options.map((opt, idx) => (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={String(opt.value) === String(value ?? "")}
                disabled={opt.disabled}
                className={`cd-option${idx === activeIndex ? " cd-option-active" : ""}${
                  String(opt.value) === String(value ?? "") ? " cd-option-selected" : ""
                }`}
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => selectIndex(idx)}
              >
                <span>{opt.label}</span>
                {String(opt.value) === String(value ?? "") && <Icon name="check" size={13} strokeWidth={2.4} className="cd-check" />}
              </button>
            ))}
          </div>,
          document.body
        )}
    </div>
  );
}
