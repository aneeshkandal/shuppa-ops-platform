/**
 * A small, original set of line icons used throughout the app in place of
 * emoji (sidebar nav, KPI cards, alerts, status pills, buttons). All icons
 * share the same 24x24 grid, stroke-based style (currentColor, round caps)
 * so they inherit whatever text color surrounds them and stay crisp at any
 * size - drawn from scratch for this app, not pulled from an icon library.
 */
"use client";

import type { ReactElement } from "react";

export type IconName =
  | "home"
  | "package"
  | "packagePlus"
  | "trendingUp"
  | "truck"
  | "users"
  | "grid"
  | "bell"
  | "smartphone"
  | "building"
  | "clipboardList"
  | "upload"
  | "map"
  | "settings"
  | "fileText"
  | "search"
  | "lock"
  | "alertTriangle"
  | "alertOctagon"
  | "lightbulb"
  | "coins"
  | "award"
  | "calendar"
  | "clock"
  | "target"
  | "barChart"
  | "checkCircle"
  | "check"
  | "moon"
  | "sun"
  | "x"
  | "refreshCw"
  | "chevronUp"
  | "chevronDown"
  | "chevronLeft"
  | "chevronRight"
  | "arrowRight"
  | "download";

const PATHS: Record<IconName, ReactElement> = {
  home: (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
    </>
  ),
  package: (
    <>
      <path d="M3 8l9-5 9 5-9 5-9-5Z" />
      <path d="M3 8v9l9 5 9-5V8" />
      <path d="M12 13v9" />
    </>
  ),
  packagePlus: (
    <>
      <path d="M3 8l8-4.5 5 2.8" />
      <path d="M3 8v9l8 4.5V13" />
      <path d="M11 13 3 8" />
      <circle cx="18" cy="8" r="4.5" />
      <path d="M18 6v4M16 8h4" />
    </>
  ),
  trendingUp: (
    <>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </>
  ),
  truck: (
    <>
      <rect x="1.5" y="7" width="13" height="9" rx="1.2" />
      <path d="M14.5 10h4l3.5 3.2V16h-7.5" />
      <circle cx="6" cy="18.2" r="1.7" />
      <circle cx="17.3" cy="18.2" r="1.7" />
    </>
  ),
  users: (
    <>
      <circle cx="8.5" cy="7.8" r="3.1" />
      <path d="M2.7 20c0-3.3 2.6-5.9 5.8-5.9s5.8 2.6 5.8 5.9" />
      <circle cx="17.2" cy="9" r="2.3" />
      <path d="M15 14.6c2.5.4 4.3 2.6 4.3 5.4" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.3" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.3" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.3" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.3" />
    </>
  ),
  bell: (
    <>
      <path d="M6 9.5a6 6 0 0 1 12 0c0 4.8 1.8 5.8 1.8 5.8H4.2S6 14.3 6 9.5Z" />
      <path d="M10 19.8a2 2 0 0 0 4 0" />
    </>
  ),
  smartphone: (
    <>
      <rect x="6.5" y="2" width="11" height="20" rx="2" />
      <line x1="11" y1="18.2" x2="13" y2="18.2" />
    </>
  ),
  building: (
    <>
      <path d="M3.5 21V9.8L11 5.5v15.5" />
      <path d="M11 21v-8.3l6.5-3v11.3" />
      <path d="M17.5 21v-5.5H21V21" />
      <line x1="2.5" y1="21" x2="21.5" y2="21" />
    </>
  ),
  clipboardList: (
    <>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <rect x="9" y="2.2" width="6" height="3.6" rx="1" />
      <line x1="8" y1="11.5" x2="16" y2="11.5" />
      <line x1="8" y1="15.5" x2="16" y2="15.5" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="M7 9l5-5 5 5" />
      <path d="M4.5 16v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3" />
    </>
  ),
  map: (
    <>
      <path d="M9 3.2 3 5.5v15l6-2.3 6 2.3 6-2.3v-15l-6 2.3-6-2.3Z" />
      <line x1="9" y1="3.2" x2="9" y2="18.5" />
      <line x1="15" y1="5.5" x2="15" y2="20.8" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3.1" />
      <path d="M12 3.5v2.6M12 17.9v2.6M4.5 12h2.6M16.9 12h2.6" />
      <path d="M6.8 6.8l1.8 1.8M15.4 15.4l1.8 1.8M6.8 17.2l1.8-1.8M15.4 8.6l1.8-1.8" />
    </>
  ),
  fileText: (
    <>
      <path d="M7 3h6.5L18 7.5V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" />
      <path d="M13.5 3v4.5H18" />
      <line x1="8.3" y1="12.5" x2="14.5" y2="12.5" />
      <line x1="8.3" y1="16" x2="14.5" y2="16" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <line x1="19.8" y1="19.8" x2="15.3" y2="15.3" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10.3" width="14" height="10" rx="2" />
      <path d="M8 10.3V7.3a4 4 0 0 1 8 0v3" />
    </>
  ),
  alertTriangle: (
    <>
      <path d="M12 3.2 2.2 20.5h19.6L12 3.2Z" />
      <line x1="12" y1="9.3" x2="12" y2="14.3" />
      <circle cx="12" cy="17.3" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  alertOctagon: (
    <>
      <path d="M8 2.5h8L21.5 8v8L16 21.5H8L2.5 16V8Z" />
      <line x1="12" y1="7.8" x2="12" y2="12.8" />
      <circle cx="12" cy="16" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  lightbulb: (
    <>
      <path d="M12 3a6 6 0 0 0-3.4 10.9c.6.5 1 1.2 1 2v.4h4.8v-.4c0-.8.4-1.5 1-2A6 6 0 0 0 12 3Z" />
      <line x1="10" y1="18.7" x2="14" y2="18.7" />
      <line x1="10.6" y1="21" x2="13.4" y2="21" />
    </>
  ),
  coins: (
    <>
      <ellipse cx="12" cy="6.3" rx="7" ry="3" />
      <path d="M5 6.3v5c0 1.66 3.13 3 7 3s7-1.34 7-3v-5" />
      <path d="M5 11.3v5c0 1.66 3.13 3 7 3s7-1.34 7-3v-5" />
    </>
  ),
  award: (
    <>
      <circle cx="12" cy="8" r="5" />
      <path d="M8.4 12.6 7 21.3l5-2.6 5 2.6-1.4-8.7" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="8" y1="3" x2="8" y2="7" />
      <line x1="16" y1="3" x2="16" y2="7" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5.5l3.8 2.2" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.7" />
      <circle cx="12" cy="12" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  barChart: (
    <>
      <rect x="4" y="12" width="4" height="8" />
      <rect x="10" y="7" width="4" height="13" />
      <rect x="16" y="3" width="4" height="17" />
    </>
  ),
  checkCircle: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.3 10.5 14.8 16 9.3" />
    </>
  ),
  check: <path d="M5 13 10 18 19 7" />,
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z" />,
  sun: (
    <>
      <circle cx="12" cy="12" r="4.3" />
      <path d="M12 2.5v2.6M12 18.9v2.6M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2.5 12H5M19 12h2.5M4.2 19.8 6 18M18 6l1.8-1.8" />
    </>
  ),
  x: (
    <>
      <line x1="5.5" y1="5.5" x2="18.5" y2="18.5" />
      <line x1="18.5" y1="5.5" x2="5.5" y2="18.5" />
    </>
  ),
  refreshCw: (
    <>
      <path d="M21 12a9 9 0 0 1-15.5 6.3L3 16" />
      <path d="M3 12a9 9 0 0 1 15.5-6.3L21 8" />
      <path d="M3 16v4h4" />
      <path d="M21 8V4h-4" />
    </>
  ),
  chevronUp: <polyline points="6,15 12,9 18,15" />,
  chevronDown: <polyline points="6,9 12,15 18,9" />,
  chevronLeft: <polyline points="15,6 9,12 15,18" />,
  chevronRight: <polyline points="9,6 15,12 9,18" />,
  arrowRight: (
    <>
      <line x1="4" y1="12" x2="17" y2="12" />
      <polyline points="11,6 17,12 11,18" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12" />
      <polyline points="7,11 12,16 17,11" />
      <path d="M4.5 19h15" />
    </>
  ),
};

export default function Icon({
  name,
  size = 16,
  strokeWidth = 1.8,
  className,
}: {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
