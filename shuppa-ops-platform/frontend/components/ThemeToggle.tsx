"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Icon from "./Icon";

const STORAGE_KEY = "shuppa_theme"; // "light" | "dark" - absent means "follow system"

function applyTheme(theme: "light" | "dark") {
  document.documentElement.setAttribute("data-theme", theme);
}

/**
 * Dark mode toggle shown in the sidebar. Defaults to the OS's
 * prefers-color-scheme when the user hasn't picked one explicitly yet, and
 * persists an explicit choice to localStorage from then on (see the inline
 * script in app/layout.tsx, which applies that choice before first paint so
 * there's no flash of the wrong theme).
 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // The inline head script already set document.documentElement's
    // data-theme before this component mounts - just read it back so the
    // icon matches, rather than re-deriving it (and potentially racing the
    // script's own localStorage read).
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "dark" : "light");
    setReady(true);
  }, []);

  const toggle = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore - the toggle still works for this page load, just won't persist */
    }
  };

  // Avoid rendering the wrong icon for a frame before we've read the
  // already-applied theme back off the DOM.
  if (!ready) return <span className="theme-toggle" aria-hidden style={{ visibility: "hidden" }} />;

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ rotate: -90, opacity: 0, scale: 0.5 }}
          animate={{ rotate: 0, opacity: 1, scale: 1 }}
          exit={{ rotate: 90, opacity: 0, scale: 0.5 }}
          transition={{ duration: 0.2 }}
          style={{ display: "inline-flex" }}
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
