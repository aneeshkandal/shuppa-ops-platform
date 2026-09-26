import type { ReactNode } from "react";
import "./globals.css";
import { AuthProvider } from "../lib/auth";
import { FilterProvider } from "../lib/FilterContext";

export const metadata = {
  title: "Shuppa Operations Intelligence Platform",
  description: "Warehouse & operations analytics for Shuppa's quick-delivery network.",
};

// Applies the saved (or OS-preferred) theme to <html data-theme="..."> before
// first paint, so the page never flashes light-then-dark (or vice versa)
// while React hydrates. Kept tiny and defensive (try/catch, no dependency on
// anything else having loaded yet) since it runs before any bundled JS.
const THEME_INIT_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem("shuppa_theme");
    var theme = stored === "light" || stored === "dark"
      ? stored
      : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {
    /* localStorage/matchMedia unavailable - default (light) styling applies */
  }
})();
`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <AuthProvider>
          <FilterProvider>{children}</FilterProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
