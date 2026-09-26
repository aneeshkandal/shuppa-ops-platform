// Thin typed client over the FastAPI backend. Base URL is configurable via
// NEXT_PUBLIC_API_BASE_URL (see .env.local) so the frontend can point at a
// deployed API later without code changes.
//
// Auth note (login-security hardening pass): this used to read a JWT out of
// localStorage and attach it as an Authorization header on every request -
// simple, but a JS-readable token in localStorage is exactly what an XSS bug
// wants to steal. The backend now sets an httpOnly cookie on login instead
// (see app/routers/auth.py's login()), which JavaScript can't read at all.
// Every fetch below just needs `credentials: "include"` so the browser
// attaches that cookie automatically - there's no token for this file to
// read, store, or attach by hand anymore.

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  /** True when the backend responded 403 with X-Password-Change-Required -
   * see app/auth.py's get_current_user. AuthProvider uses this to redirect
   * to /change-password instead of treating it like a normal auth failure. */
  passwordChangeRequired: boolean;
  constructor(message: string, status: number, passwordChangeRequired = false) {
    super(message);
    this.status = status;
    this.passwordChangeRequired = passwordChangeRequired;
  }
}

/** Turns a FastAPI error response body's `detail` into a plain, readable
 * string. Most endpoints raise HTTPException(detail="a plain string"), but a
 * 422 from Pydantic request validation (e.g. a bulk-upload row with an
 * invalid enum value) sends `detail` as an ARRAY of {loc, msg, type}
 * objects instead - passing that straight to `new Error()`/`new ApiError()`
 * silently stringifies it via the array's default toString(), which joins
 * each object's own default toString() ("[object Object]") with commas
 * instead of raising a real error, so every field-validation failure ends
 * up rendered verbatim as "[object Object],[object Object]" in the UI. This
 * turns each validation error into a "products.4.storage_type: String
 * should match pattern..." style line instead, and falls back to the
 * response's own statusText when there's no usable detail at all (a
 * non-JSON error body, a network-level failure, etc). */
function extractErrorDetail(body: any, fallback: string): string {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    const lines = body.detail.map((err: any) => {
      const loc = Array.isArray(err?.loc) ? err.loc.filter((p: any) => p !== "body").join(".") : "";
      const msg = typeof err?.msg === "string" ? err.msg : JSON.stringify(err);
      return loc ? `${loc}: ${msg}` : msg;
    });
    if (lines.length > 0) return lines.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const passwordChangeRequired = res.headers.get("X-Password-Change-Required") === "true";
  if (
    res.status === 401 &&
    typeof window !== "undefined" &&
    !path.startsWith("/auth/") &&
    window.location.pathname !== "/login"
  ) {
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = extractErrorDetail(body, detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status, passwordChangeRequired);
  }
  return res.json();
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "");
  if (entries.length === 0) return "";
  return "?" + entries.map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
}

// A date range resolved from the dashboard-wide Before/After/Between filter.
export type DateRange = { from?: string; to?: string };

function dateParams(range?: DateRange) {
  return { date_from: range?.from, date_to: range?.to };
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
type AuthUserResponse = {
  user_id: number;
  username: string;
  role: string;
  warehouse_id: number | null;
  warehouse_name: string | null;
  must_change_password?: boolean;
};

export const authApi = {
  login: async (username: string, password: string) => {
    const body = new URLSearchParams();
    body.set("username", username);
    body.set("password", password);
    const res = await fetch(`${BASE_URL}/auth/login`, {
      method: "POST",
      credentials: "include", // required so the Set-Cookie from the response is actually stored
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
    if (!res.ok) {
      let detail = "Login failed";
      try {
        const b = await res.json();
        detail = extractErrorDetail(b, detail);
      } catch {
        /* ignore */
      }
      throw new ApiError(detail, res.status);
    }
    return res.json() as Promise<{
      access_token: string;
      token_type: string;
      user: AuthUserResponse;
    }>;
  },
  logout: () => request<{ logged_out: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<AuthUserResponse>("/auth/me"),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<{ changed: boolean }>("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  register: (body: { username: string; password: string; email: string; warehouse_id: number }) =>
    request<{ message: string; user_id: number; username: string; pending_approval: boolean }>("/auth/register", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  forgotPassword: (email: string) =>
    request<{ message: string }>("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email }) }),
  resetPassword: (token: string, newPassword: string) =>
    request<{ reset: boolean }>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
  // Public warehouse list for the /register page's dropdown - unauthenticated,
  // deliberately separate from adminApi.getWarehouses() which requires an
  // Admin session.
  warehousesPublic: () => request<Array<{ warehouse_id: number; warehouse_name: string }>>("/auth/warehouses"),
};

// ---------------------------------------------------------------------------
// Stock Summary
// ---------------------------------------------------------------------------
export const stockApi = {
  summary: (warehouseId?: number, range?: DateRange) =>
    request<any>(`/stock/summary${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  alerts: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/stock/alerts${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  trend: (days = 31, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/stock/trend${qs({ days, warehouse_id: warehouseId, ...dateParams(range) })}`),
  distribution: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/stock/distribution${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  lowStock: (limit = 20, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/stock/low-stock${qs({ limit, warehouse_id: warehouseId, ...dateParams(range) })}`),
  reorderSuggestions: (limit = 50, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/stock/reorder-suggestions${qs({ limit, warehouse_id: warehouseId, ...dateParams(range) })}`),
  draftPo: (body: { product_id: number; supplier_id?: number; warehouse_id: number; quantity: number; note?: string }) =>
    request<any>("/stock/reorder-suggestions/draft-po", { method: "POST", body: JSON.stringify(body) }),
  draftPos: (limit = 100, warehouseId?: number) =>
    request<any[]>(`/stock/draft-pos${qs({ limit, warehouse_id: warehouseId })}`),
  rebalancingSuggestions: (limit = 50, warehouseId?: number) =>
    request<any[]>(`/stock/rebalancing-suggestions${qs({ limit, warehouse_id: warehouseId })}`),
  deadStock: (limit = 50, warehouseId?: number) =>
    request<{ items: any[]; total_value_tied_up: number; dead_stock_days_threshold: number }>(
      `/stock/dead-stock${qs({ limit, warehouse_id: warehouseId })}`
    ),
  marginDensity: (limit = 50, category?: string) =>
    request<any[]>(`/stock/margin-density${qs({ limit, category })}`),
};

// ---------------------------------------------------------------------------
// Supplier Summary
// ---------------------------------------------------------------------------
export const supplierApi = {
  kpis: (warehouseId?: number, range?: DateRange) =>
    request<any>(`/suppliers/kpis${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  performance: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/suppliers/performance${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  trend: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/suppliers/trend${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  riskDistribution: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/suppliers/risk-distribution${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  topByValue: (limit = 5, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/suppliers/top-by-value${qs({ limit, warehouse_id: warehouseId, ...dateParams(range) })}`),
  recentLate: (limit = 10, warehouseId?: number, range?: DateRange, supplierId?: number) =>
    request<any[]>(
      `/suppliers/recent-late${qs({ limit, warehouse_id: warehouseId, supplier_id: supplierId, ...dateParams(range) })}`
    ),
};

// ---------------------------------------------------------------------------
// Stock Optimizer
// ---------------------------------------------------------------------------
export const optimizerApi = {
  tree: (warehouseId?: number) => request<any[]>(`/optimizer/tree${qs({ warehouse_id: warehouseId })}`),
  products: (search?: string, limit = 50) =>
    request<any[]>(`/optimizer/products${qs({ search, limit })}`),
  pendingPlacement: (limit = 100) => request<any[]>(`/optimizer/pending-placement${qs({ limit })}`),
  markPlaced: (productId: number, locationId: number) =>
    request<any>("/optimizer/mark-placed", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, location_id: locationId }),
    }),
  /** "Confirm Putaway for All Locations" - one location_id per warehouse
   * (the New Products Awaiting Placement panel's putaway grid), confirmed
   * together as a single atomic action - see
   * storage_optimizer.mark_placed_bulk. */
  markPlacedBulk: (productId: number, locationIds: number[]) =>
    request<any>("/optimizer/mark-placed-bulk", {
      method: "POST",
      body: JSON.stringify({ product_id: productId, location_ids: locationIds }),
    }),
  heatmap: (warehouseId?: number) => request<any[]>(`/optimizer/heatmap${qs({ warehouse_id: warehouseId })}`),
  /** Powers the Store Layout Heatmap's click-to-inspect popup - see
   * app/services/storage_optimizer.py's get_location_detail for what's real
   * vs. backfilled in the returned product list. */
  locationDetail: (locationId: number) => request<any>(`/optimizer/locations/${locationId}`),
  overstocked: (threshold = 90, warehouseId?: number) =>
    request<any[]>(`/optimizer/overstocked${qs({ threshold, warehouse_id: warehouseId })}`),
  underutilized: (threshold = 30, warehouseId?: number) =>
    request<any[]>(`/optimizer/underutilized${qs({ threshold, warehouse_id: warehouseId })}`),
  suggest: (body: {
    product_id?: number;
    length_cm?: number;
    width_cm?: number;
    height_cm?: number;
    weight_kg?: number;
    fragility?: string;
    storage_type?: string;
    warehouse_id?: number;
    top_n?: number;
  }) => request<any>("/optimizer/suggest", { method: "POST", body: JSON.stringify(body) }),
  topMovers: (warehouseId?: number, limit = 20) =>
    request<any[]>(`/optimizer/top-movers${qs({ warehouse_id: warehouseId, limit })}`),
};

// ---------------------------------------------------------------------------
// Sales Analytics
// ---------------------------------------------------------------------------
export const salesApi = {
  kpis: (warehouseId?: number, range?: DateRange) =>
    request<any>(`/sales/kpis${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  trend: (granularity: "day" | "month" = "day", days = 31, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/sales/trend${qs({ granularity, days, warehouse_id: warehouseId, ...dateParams(range) })}`),
  forecast: (forecastDays = 7, historyDays = 30, warehouseId?: number, range?: DateRange, category?: string) =>
    request<any>(
      `/sales/forecast${qs({
        forecast_days: forecastDays,
        history_days: historyDays,
        warehouse_id: warehouseId,
        category,
        ...dateParams(range),
      })}`
    ),
  topProducts: (limit = 10, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/sales/top-products${qs({ limit, warehouse_id: warehouseId, ...dateParams(range) })}`),
  byCategory: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/sales/by-category${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  byWarehouse: (range?: DateRange) => request<any[]>(`/sales/by-warehouse${qs({ ...dateParams(range) })}`),
  avgOrderValue: (warehouseId?: number, range?: DateRange) =>
    request<any>(`/sales/avg-order-value${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  // Order Trends / Peak Order Time / Customer Growth / Delivery Performance /
  // Return & Cancellation Insights are all built on the same synthetic
  // per-order + per-customer layer (dim_customers / fact_orders), since the
  // real data has never had an order_id, a time-of-day, or a customer entity
  // - see backend/app/services/sales_service.py's backfill_synthetic_orders()
  // for exactly what's real vs. estimated.
  orderTrend: (granularity: "day" | "month" = "day", days = 31, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/sales/order-trend${qs({ granularity, days, warehouse_id: warehouseId, ...dateParams(range) })}`),
  orderTimeDistribution: (warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/sales/order-time-distribution${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  customerGrowth: (days = 90, warehouseId?: number, range?: DateRange) =>
    request<any>(`/sales/customer-growth${qs({ days, warehouse_id: warehouseId, ...dateParams(range) })}`),
  deliveryPerformance: (days = 31, warehouseId?: number, range?: DateRange) =>
    request<any>(`/sales/delivery-performance${qs({ days, warehouse_id: warehouseId, ...dateParams(range) })}`),
  returnCancellation: (days = 31, warehouseId?: number, range?: DateRange) =>
    request<any>(`/sales/return-cancellation${qs({ days, warehouse_id: warehouseId, ...dateParams(range) })}`),
  categories: () => request<string[]>("/sales/categories"),
  correlatedProducts: (productId: number, warehouseId?: number, limit = 5) =>
    request<{ product_id: number; correlated: any[]; note?: string }>(
      `/sales/correlated-products${qs({ product_id: productId, warehouse_id: warehouseId, limit })}`
    ),
};

// ---------------------------------------------------------------------------
// Key Business Insights - one small card per page (Stock Summary, Sales
// Analytics, Supplier Summary, Stock Optimizer, Delivery Risk Predictor), a
// tabs/pills row inside the card filters which insight shows. Every insight
// is derived from data that page's own KPIs/tables already show - see
// backend/app/services/insights_service.py for exactly what each one
// computes. Each endpoint takes the same warehouse_id/date filter shape as
// that page's other endpoints, so the card always reflects the same scope.
// ---------------------------------------------------------------------------
export type Insight = { key: string; label: string; text: string };
export type InsightsResponse = { insights: Insight[] };

export const insightsApi = {
  stock: (warehouseId?: number, range?: DateRange) =>
    request<InsightsResponse>(`/insights/stock${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  sales: (warehouseId?: number, range?: DateRange) =>
    request<InsightsResponse>(`/insights/sales${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  supplier: (warehouseId?: number, range?: DateRange) =>
    request<InsightsResponse>(`/insights/supplier${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  // Stock Optimizer has no date-range filter on its own page (see
  // storage/page.tsx) - matches storage_optimizer's own get_heatmap/
  // get_top_movers/get_pending_placement, none of which take date_from/
  // date_to either.
  storage: (warehouseId?: number) => request<InsightsResponse>(`/insights/storage${qs({ warehouse_id: warehouseId })}`),
  delivery: (warehouseId?: number, range?: DateRange) =>
    request<InsightsResponse>(`/insights/delivery${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
};

// ---------------------------------------------------------------------------
// Delivery Risk Predictor
// ---------------------------------------------------------------------------
export const deliveryApi = {
  kpis: (warehouseId?: number, range?: DateRange) =>
    request<any>(`/delivery/kpis${qs({ warehouse_id: warehouseId, ...dateParams(range) })}`),
  options: () => request<{ suppliers: any[]; warehouses: any[]; products: any[] }>("/delivery/options"),
  predict: (body: {
    supplier_id: number;
    warehouse_id: number;
    order_quantity: number;
    lead_time_days: number;
    product_id?: number;
  }) => request<any>("/delivery/predict", { method: "POST", body: JSON.stringify(body) }),
  riskyOrders: (limit = 15, warehouseId?: number, range?: DateRange) =>
    request<any[]>(`/delivery/risky-orders${qs({ limit, warehouse_id: warehouseId, ...dateParams(range) })}`),
};

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------
export const adminApi = {
  getWarehouses: () => request<any[]>("/admin/warehouses"),
  addWarehouse: (body: { warehouse_name: string; city?: string }) =>
    request<any>("/admin/warehouses", { method: "POST", body: JSON.stringify(body) }),
  getSuppliers: () => request<any[]>("/admin/suppliers"),
  addSupplier: (body: { supplier_name: string; warehouse_id?: number }) =>
    request<any>("/admin/suppliers", { method: "POST", body: JSON.stringify(body) }),
  bulkAddSuppliers: (suppliers: Array<Record<string, any>>) =>
    request<{ created: any[]; count: number }>("/admin/suppliers/bulk", {
      method: "POST",
      body: JSON.stringify({ suppliers }),
    }),
  addProduct: (body: {
    product_name: string;
    description?: string;
    selling_price: number;
    unit_cost: number;
    category?: string;
    length_cm: number;
    width_cm: number;
    height_cm: number;
    weight_kg: number;
    fragility?: string;
    storage_type?: string;
    stackable?: boolean;
  }) => request<any>("/admin/products", { method: "POST", body: JSON.stringify(body) }),
  addLocation: (body: {
    warehouse_id: number;
    location_code: number;
    storage_type: string;
    shelf_tier?: number;
    sub_location_start?: number;
    sub_location_count?: number;
    is_overstock_tier?: boolean;
    max_weight_kg: number;
    max_volume_cm3: number;
    note?: string;
  }) => request<any>("/admin/locations", { method: "POST", body: JSON.stringify(body) }),
  bulkAddLocations: (locations: Array<Record<string, any>>) =>
    request<{ created: any[]; count: number }>("/admin/locations/bulk", {
      method: "POST",
      body: JSON.stringify({ locations }),
    }),

  // -- Manage Users --
  listUsers: () => request<any[]>("/admin/users"),
  addUser: (body: {
    username: string;
    password: string;
    role: "ADMIN" | "WAREHOUSE";
    warehouse_id?: number;
    email?: string;
  }) => request<any>("/admin/users", { method: "POST", body: JSON.stringify(body) }),
  updateUser: (userId: number, body: { is_active?: boolean; password?: string; email?: string }) =>
    request<any>(`/admin/users/${userId}`, { method: "PATCH", body: JSON.stringify(body) }),

  // -- Bulk product upload --
  bulkAddProducts: (products: Array<Record<string, any>>) =>
    request<{ created: any[]; count: number }>("/admin/products/bulk", {
      method: "POST",
      body: JSON.stringify({ products }),
    }),

  // -- Audit log --
  getAuditLog: (
    limit = 100,
    filters?: { username?: string; action?: string; dateFrom?: string; dateTo?: string }
  ) =>
    request<any[]>(
      `/admin/audit-log${qs({
        limit,
        username: filters?.username,
        action: filters?.action,
        date_from: filters?.dateFrom,
        date_to: filters?.dateTo,
      })}`
    ),
  getAuditLogFilters: () => request<{ actions: string[]; usernames: string[] }>("/admin/audit-log/filters"),
};

// ---------------------------------------------------------------------------
// Supplier Returns (Supplier Summary page) - wrong/extra items a supplier
// delivered that need resolving. Filing a return is available to any
// authenticated user (warehouse-scoped, same as Draft PO/mark-placed);
// resolving a line item is admin-only - see backend/app/routers/returns.py.
// ---------------------------------------------------------------------------
export type SupplierReturnItem = {
  return_item_id: number;
  return_id: number;
  product_id: number | null;
  product_name_reported: string;
  quantity: number;
  reason: "WRONG_PRODUCT" | "EXTRA_PRODUCT";
  resolution: "PENDING" | "RETURNED" | "LISTED_AS_NEW_PRODUCT" | "PO_GENERATED";
  resolved_at: string | null;
  resolved_by: string | null;
  linked_draft_po_id: number | null;
  created_product_id: number | null;
};

export type SupplierReturn = {
  return_id: number;
  supplier_id: number;
  supplier_name: string;
  warehouse_id: number;
  filed_at: string;
  filed_by: string;
  scheduled_return_date: string | null;
  note: string | null;
  item_count: number;
  pending_count: number;
};

export type SupplierReturnDetail = Omit<SupplierReturn, "item_count" | "pending_count"> & {
  items: SupplierReturnItem[];
};

export const returnsApi = {
  suppliers: (warehouseId?: number) =>
    request<Array<{ supplier_id: number; supplier_name: string }>>(
      `/supplier-returns/suppliers${qs({ warehouse_id: warehouseId })}`
    ),
  list: (warehouseId?: number) => request<SupplierReturn[]>(`/supplier-returns${qs({ warehouse_id: warehouseId })}`),
  detail: (returnId: number) => request<SupplierReturnDetail>(`/supplier-returns/${returnId}`),
  file: (body: {
    supplier_id: number;
    warehouse_id: number;
    scheduled_return_date?: string;
    note?: string;
    items: Array<{
      product_id?: number;
      product_name_reported: string;
      quantity: number;
      reason: "WRONG_PRODUCT" | "EXTRA_PRODUCT";
    }>;
  }) => request<SupplierReturnDetail>("/supplier-returns", { method: "POST", body: JSON.stringify(body) }),
  resolveItem: (
    returnItemId: number,
    body: { resolution: "RETURNED" | "LISTED_AS_NEW_PRODUCT" | "PO_GENERATED"; quantity?: number; note?: string; created_product_id?: number }
  ) =>
    request<SupplierReturnItem>(`/supplier-returns/items/${returnItemId}/resolve`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

// ---------------------------------------------------------------------------
// Unified Alerts Center
// ---------------------------------------------------------------------------
export const alertsApi = {
  all: (warehouseId?: number) => request<any[]>(`/alerts${qs({ warehouse_id: warehouseId })}`),
  /** Admin-only. `count` must be the alert's own current count - it's
   * snapshotted so the alert can reappear automatically later if it
   * recomputes with a different count. See backend/app/services/
   * alerts_service.py's resolve_alert() for the full behavior. */
  resolve: (title: string, warehouseId: number | undefined, count: number) =>
    request<{ title: string; warehouse_id?: number; resolved_count: number }>(`/alerts/resolve`, {
      method: "POST",
      body: JSON.stringify({ title, warehouse_id: warehouseId, count }),
    }),
  /** Admin-only, same as resolve. */
  resolved: (warehouseId?: number) =>
    request<any[]>(`/alerts/resolved${qs({ warehouse_id: warehouseId })}`),
  /** Admin-only. Undoes an earlier resolve - e.g. resolved the wrong alert
   * by mistake. See backend/app/services/alerts_service.py's
   * rollback_alert() for the full behavior. */
  rollback: (title: string, warehouseId: number | undefined) =>
    request<{ title: string; warehouse_id?: number; rolled_back: boolean }>(`/alerts/rollback`, {
      method: "POST",
      body: JSON.stringify({ title, warehouse_id: warehouseId }),
    }),
};

// ---------------------------------------------------------------------------
// Global search
// ---------------------------------------------------------------------------
export const searchApi = {
  search: (q: string) => request<{ products: any[]; suppliers: any[] }>(`/search${qs({ q })}`),
};

// ---------------------------------------------------------------------------
// Dashboard-configurable settings (Admin)
// ---------------------------------------------------------------------------
export const settingsApi = {
  getAll: () => request<Array<{ setting_key: string; setting_value: string; updated_at: string }>>("/admin/settings"),
  update: (settings: Record<string, string>) =>
    request<Record<string, string>>("/admin/settings", { method: "PUT", body: JSON.stringify({ settings }) }),
  preview: (settings: Record<string, string>, warehouseId?: number) =>
    request<{ current: Record<string, number>; proposed: Record<string, number> }>(
      `/admin/settings/preview${qs({ warehouse_id: warehouseId })}`,
      { method: "POST", body: JSON.stringify({ settings }) }
    ),
};

// The 3 real Dublin warehouses this project models. { id: undefined } is the
// "All Warehouses" option shown only to ADMIN users - WAREHOUSE-role users
// never see this selector at all (they're locked to their own warehouse).
export const WAREHOUSES = [
  { id: undefined, name: "All Warehouses" },
  { id: 1, name: "Lombard" },
  { id: 2, name: "Kimmage" },
  { id: 3, name: "Finglas" },
];
