"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { alertsApi } from "../lib/api";
import ThemeToggle from "./ThemeToggle";
import Icon, { IconName } from "./Icon";

// Poll the alerts feed for the sidebar badge so a newly-fired critical alert
// shows up without needing to visit the Alerts Center page.
const SIDEBAR_ALERTS_POLL_MS = 30_000;

const NAV_ITEMS: { name: string; path: string; icon: IconName }[] = [
  { name: "Overview", path: "/overview", icon: "home" },
  { name: "Stock Summary", path: "/stock", icon: "package" },
  { name: "Sales Analytics", path: "/sales", icon: "trendingUp" },
  { name: "Delivery Risk Predictor", path: "/delivery", icon: "truck" },
  { name: "Supplier Summary", path: "/suppliers", icon: "users" },
  { name: "Stock Optimizer", path: "/storage", icon: "grid" },
];

const ADMIN_NAV_ITEMS: { name: string; path: string; icon: IconName }[] = [
  { name: "Warehouses", path: "/admin/warehouses", icon: "building" },
  { name: "Suppliers", path: "/admin/suppliers", icon: "clipboardList" },
  { name: "Add Product", path: "/admin/products", icon: "packagePlus" },
  { name: "Bulk Upload", path: "/admin/bulk-upload", icon: "upload" },
  { name: "Locations", path: "/admin/locations", icon: "map" },
  { name: "Manage Users", path: "/admin/users", icon: "users" },
  { name: "Settings", path: "/admin/settings", icon: "settings" },
  { name: "Audit Log", path: "/admin/audit-log", icon: "fileText" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  // Polls the unified alerts feed just for a sidebar badge count - the
  // Alerts Center page itself fetches its own full detail.
  const alerts = useApi(
    () => alertsApi.all(user?.role === "WAREHOUSE" ? user.warehouse_id ?? undefined : undefined),
    [user?.user_id],
    { refreshInterval: SIDEBAR_ALERTS_POLL_MS }
  );
  const criticalCount = (alerts.data || []).filter((a: any) => a.level === "critical").length;

  return (
    <aside className="sidebar">
      <div className="sidebar-logo" style={{ justifyContent: "space-between" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="sidebar-logo-badge">S</span>
          Shuppa
        </span>
        <ThemeToggle />
      </div>
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.path;
        return (
          <Link key={item.path} href={item.path} className={`nav-item ${active ? "active" : ""}`}>
            {active && (
              <motion.span
                layoutId="nav-active-pill"
                className="nav-item-pill"
                transition={{ type: "spring", stiffness: 420, damping: 34 }}
              />
            )}
            <span className="nav-icon">
              <Icon name={item.icon} size={17} />
            </span>
            {item.name}
          </Link>
        );
      })}
      <Link href="/alerts" className={`nav-item ${pathname === "/alerts" ? "active" : ""}`}>
        {pathname === "/alerts" && (
          <motion.span
            layoutId="nav-active-pill"
            className="nav-item-pill"
            transition={{ type: "spring", stiffness: 420, damping: 34 }}
          />
        )}
        <span className="nav-icon">
          <Icon name="bell" size={17} />
        </span>
        Alerts Center
        {criticalCount > 0 && <span className="nav-badge">{criticalCount}</span>}
      </Link>
      <Link href="/floor" className={`nav-item ${pathname === "/floor" ? "active" : ""}`}>
        {pathname === "/floor" && (
          <motion.span
            layoutId="nav-active-pill"
            className="nav-item-pill"
            transition={{ type: "spring", stiffness: 420, damping: 34 }}
          />
        )}
        <span className="nav-icon">
          <Icon name="smartphone" size={17} />
        </span>
        Floor View
      </Link>

      {user?.role === "ADMIN" && (
        <>
          <div className="sidebar-section-label">Admin</div>
          {ADMIN_NAV_ITEMS.map((item) => {
            const active = pathname === item.path;
            return (
              <Link key={item.path} href={item.path} className={`nav-item ${active ? "active" : ""}`}>
                {active && (
                  <motion.span
                    layoutId="nav-active-pill"
                    className="nav-item-pill"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="nav-icon">
                  <Icon name={item.icon} size={17} />
                </span>
                {item.name}
              </Link>
            );
          })}
        </>
      )}

      <div className="sidebar-user">
        <div className="sidebar-user-info">
          <div className="sidebar-user-name">{user?.username}</div>
          <div className="sidebar-user-scope">
            {user?.role === "ADMIN" ? "Admin – all warehouses" : user?.warehouse_name}
          </div>
        </div>
        <button className="sidebar-logout" onClick={logout} type="button">
          Log out
        </button>
      </div>
    </aside>
  );
}
