# Shuppa Operations Intelligence Platform

A 5-page analytics dashboard for Shuppa's quick-delivery warehouse operations
across **3 real Dublin warehouses - Lombard, Kimmage, Finglas**:
**Stock Summary**, **Supplier Summary**, **Stock Optimizer**, **Sales Analytics**,
and **Delivery Risk Predictor**, plus an **Executive Overview** home page, a
cross-domain **Alerts Center**, and an **Admin** section (warehouses/suppliers/
products/locations/users/settings/audit log) with per-warehouse login. Backend
is FastAPI + Postgres (Neon); frontend is Next.js (App Router) + Recharts. All
money in the app is in **EUR (€)**.

## Architecture

```
backend/    FastAPI app (app/), one router+service per dashboard page
  app/auth.py                JWT auth + role scoping (ADMIN vs WAREHOUSE)
  app/migrations.py          idempotent startup migrations (new tables/columns
                              added after the first seed - safe on every restart)
  app/routers/auth.py        login/logout/me/change-password, plus self-service
                              register + forgot/reset-password (Session 7)
  app/services/email_service.py  stdlib smtplib sender for reset-link emails,
                              degrades to console logging if SMTP isn't set
  app/routers/admin.py       Admin-only CRUD: warehouses/suppliers/products/
                              locations/users, plus bulk product upload
  app/routers/alerts.py      GET /alerts - unified cross-domain alerts feed
  app/routers/search.py      GET /search - global product/supplier search
  app/routers/settings.py    GET/PUT /admin/settings - configurable thresholds
  app/services/audit_service.py     every admin mutation logged to dim_audit_log
  app/services/storage_optimizer.py Smart Placement Advisor scoring, the
                              heatmap/overstocked/underutilized endpoints, and
                              get_location_detail (Session 8 - what's really
                              stored at one specific slot)
  scripts/seed_database.py   one-off ETL: loads your CSVs into Postgres,
                              generates the synthetic data the Stock Optimizer
                              needs, seeds login accounts, and trains the
                              delivery-risk model
frontend/   Next.js app (app/), one route per dashboard page
  app/login/                 login page
  app/overview/              Executive Overview home page (aggregates all 5 pages)
  app/alerts/                Alerts Center (unified alerts feed)
  app/admin/                 Admin-only pages (warehouses/suppliers/products/
                              locations/users/bulk-upload/settings/audit-log)
  app/storage/LocationDetailModal.tsx  click a heatmap cell / location row -
                              popup showing that slot's real placed products
                              (Session 8)
  lib/auth.tsx               auth context (login/logout, current user)
  lib/format.ts              "vs previous period" KPI-delta formatting
  components/GlobalSearch.tsx  app-wide search bar (top of every page)
  components/DataTable.tsx   sortable, paginated, CSV-exportable table
```

## One-time setup

You need network access to your Neon Postgres instance for this step, so run
it from a normal terminal on this machine (not through Claude) - see
**Known limitations** below for why.

```powershell
cd D:\Projects\SHUPPA\shuppa-ops-platform\shuppa-ops-platform\backend
venv\Scripts\activate
pip install -r requirements.txt   # installs passlib + bcrypt==4.0.1 (pinned - bcrypt >=4.1 breaks
                                   # passlib's backend detection), python-jose, python-multipart
python scripts\seed_database.py
```

This is **idempotent** - re-run it any time you want to refresh/reset the
data (it replaces every table it writes, so it's safe to run repeatedly).
**Re-running it also wipes out anything you added later through the Admin UI**
(new products/suppliers/warehouses/locations/users, and any changed dashboard
settings) since those live in the same tables - treat the seed script as a
"reset to demo state" tool, not an incremental migration.

You do **not** need to re-run this seed script every time the app gains a new
table or column going forward - `app/migrations.py` runs automatically on
every backend startup (`uvicorn` restart) and creates anything missing
(`CREATE TABLE IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`) without touching
existing data. The seed script stays the "full reset" tool; migrations are
the "upgrade in place" path.

It prints progress as it goes and finishes by writing
`backend/app/ml_model.json` (the trained delivery-risk model), printing the
login accounts it created, and seeding these Postgres tables:

| Table | Source |
|---|---|
| `dim_products` | your `shuppa_products_cleaned.csv`, plus a `product_id`, a `category` derived from the product name/description, and a `pending_placement` flag (see Stock Optimizer below). Prices/costs converted GBP→EUR. |
| `dim_product_dimensions` | **synthetic** - height/width/length/weight/fragility/storage type per product (your source data has no physical dimensions at all) |
| `dim_suppliers` | the **real ~84-name supplier list** you gave us (see Suppliers below), plus 9 synthetic warehouse-exclusive suppliers |
| `dim_warehouses` | the **3 real Dublin warehouses**: Lombard, Kimmage, Finglas |
| `dim_users` | 4 seeded login accounts (see Login accounts below), plus an `is_active` flag so Admin can deactivate a login without deleting it |
| `dim_storage_locations` | your `store_locations.csv`, replicated once per warehouse with a **synthetic maximum capacity** (`max_weight_kg`/`max_volume_cm3` only - see Multi-warehouse layout below); its own `current_weight_kg`/`current_volume_cm3`/`utilization_pct` columns are stale seed-time values that nothing reads anymore, superseded by `v_storage_location_occupancy` |
| `fact_sales_daily`, `fact_inventory_daily`, `fact_purchase_orders`, `fact_deliveries` | loaded from your CSVs (a `po_id` is added to purchase orders), with `warehouse_id` remapped from the source 1-5 range onto the 3 real warehouses and monetary columns converted GBP→EUR |
| `dim_settings` | key/value dashboard thresholds (stockout %, overstock value, supplier late-rate cutoffs, etc.) - editable from **Admin → Settings**, defaults set here and by `app/migrations.py` |
| `dim_audit_log` | empty on a fresh seed - fills up as Admin actions happen (see **Admin → Audit Log**) |
| `dim_product_placements` | **mostly backfilled** - one row per product+warehouse recording which `dim_storage_locations` slot it's in; `is_backfilled=true` rows are a reconstruction scored the same way the live Placement Advisor scores a suggestion (see **Real product-to-slot placement tracking** below), `is_backfilled=false` rows are a real choice someone made via the Placement Advisor |
| `v_storage_location_occupancy` | a **view**, not a table - every `dim_storage_locations` column plus `current_weight_kg`/`current_volume_cm3`/`utilization_pct` recomputed live by summing the real products in `dim_product_placements`, instead of reading the base table's stale synthetic values. Every location-facing query (heatmap, Overstocked/Underutilized, the location-detail popup, the live Placement Advisor, and the backfill itself) reads this view, not `dim_storage_locations`, for those three fields |

Every synthetic table/column is flagged (`is_synthetic` / `is_synthetic_capacity`
/ `is_layout_synthetic`) so it's always clear what's real transactional data
versus generated filler.

## Login accounts

Seeded by `seed_database.py` - **change these before this goes anywhere near
production** (and you'll be forced to anyway, see below):

| Username | Password | Role | Scope |
|---|---|---|---|
| `admin` | `Admin@12345` | ADMIN | every warehouse, plus the Admin pages |
| `lombard` | `Lombard@123` | WAREHOUSE | Lombard only |
| `kimmage` | `Kimmage@123` | WAREHOUSE | Kimmage only |
| `finglas` | `Finglas@123` | WAREHOUSE | Finglas only |

All four seeded accounts have `must_change_password` set, so the **first**
login with any of them redirects straight to **Change Password** and nothing
else in the app is reachable until that's done - this is a real server-side
gate (`app/auth.py`'s `get_current_user`, not just a frontend redirect), so it
can't be bypassed by calling the API directly either.

A WAREHOUSE-role login is locked to its own warehouse on every page and every
API call - even if you edit the request to ask for a different `warehouse_id`,
the backend overrides it server-side. Only ADMIN can see "All Warehouses" or
reach `/admin/*`.

**Account lockout:** after `MAX_FAILED_LOGIN_ATTEMPTS` (default 5) consecutive
failed logins, an account locks for `LOCKOUT_MINUTES` (default 15) - both
configurable via environment variables in `backend/app/auth.py`. A successful
login, or an Admin password reset, clears the failed-attempt counter and any
active lockout. **Manage Users** shows each account's lockout state and
`last_login_at`.

**Rate limiting:** every API request is capped per client IP -
`RATE_LIMIT_REQUESTS` requests (default 300) per `RATE_LIMIT_WINDOW_SECONDS`
(default 60), configurable in `backend/app/config.py`. This is an in-memory,
single-process fixed-window limiter (`app/rate_limit.py`) meant to blunt
accidental request storms and basic abuse on a single-instance deployment -
it resets on restart and does not coordinate across multiple backend
processes, so don't rely on it as a hard security boundary if this is ever
scaled horizontally. `/auth/login`, `/auth/register`, and
`/auth/forgot-password` sit behind a **second, much stricter** per-IP limit on
top of that general one - `LOGIN_RATE_LIMIT_REQUESTS` (default 10) per
`LOGIN_RATE_LIMIT_WINDOW_SECONDS` (default 300) - since those are the paths a
credential-stuffing or account-enumeration script would actually hit.

Add, deactivate, or reset a password for another account from **Admin →
Manage Users** - no manual SQL needed. That page also shows each account's
lockout status, `must_change_password` status, and last-login time (see
Account lockout below).

## Login security (Session 7)

**What changed and why**, since the previous version of this app stored the
JWT in `localStorage` and had no way for anyone but an Admin to create an
account or recover a forgotten password:

- **Password minimum raised from 6 to 10 characters**, with no forced mix of
  upper/lower/digit/symbol. This follows NIST SP 800-63B's actual guidance -
  length matters far more than composition rules, and composition rules push
  people toward predictable patterns (`Password1!`) instead of stronger ones.
- **Tokens moved off `localStorage` into an httpOnly, `SameSite=Lax` cookie**
  (`shuppa_access_token`), so a successful XSS injection can no longer just
  read the token out of browser storage. `Secure` is added automatically
  when `ENVIRONMENT=production` (it's dropped over local `http://`
  otherwise). `/docs` and API scripts still work unchanged via the
  `Authorization: Bearer` header - `get_current_user` accepts either.
- **The JWT secret can no longer default silently in production.** If
  `ENVIRONMENT=production` and `JWT_SECRET_KEY` is still unset (or still the
  dev fallback), the backend now refuses to start (`RuntimeError` at import
  time in `app/auth.py`) instead of quietly signing tokens with a
  publicly-known key.
- **Self-service registration** at `/register` - anyone can request an
  account (username, email, password, one warehouse), but it's created with
  `is_active=false, pending_approval=true` and can't log in until an Admin
  clicks **Approve** on it from **Manage Users**. Only an existing Admin can
  grant the ADMIN role; self-service always creates a WAREHOUSE account.
- **Forgot password** at `/forgot-password` → emails a single-use,
  30-minute reset link (`/reset-password?token=...`). The token itself is
  never stored - only its SHA-256 hash goes in `dim_password_reset_tokens` -
  so a database leak alone can't be used to reset anyone's password. Like the
  login form, this always returns the same generic "check your email"
  message whether or not the address matched an account, so it can't be used
  to enumerate who has a Shuppa login.
- **Forced password change** for the four seeded demo accounts (see Login
  accounts above), and for any account an Admin resets from Manage Users -
  the next login for that account is blocked at every other route until a
  new password is set.

**Sending real reset emails needs SMTP credentials**, which aren't seeded
with anything by default. Without them, `email_service.py` just logs the
reset link to the backend's console instead of emailing it - fine for local
testing, not fine for real users. To turn on real delivery, add these to
`backend/.env` (never commit real credentials to a shared repo):

```
SMTP_HOST=smtp.yourprovider.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_FROM_EMAIL=no-reply@yourdomain.com
SMTP_USE_TLS=true
FRONTEND_BASE_URL=http://localhost:3000   # used to build the reset link - set to the real domain in production
```

## Multi-warehouse layout - what's real vs. assumed

You gave us one combined Ambient/Chilled/Frozen/Vape Drawer location list.
Since the project only had one warehouse in mind at the time, **that real
layout is applied to Lombard** (warehouse_id 1). Kimmage and Finglas don't
have real layouts yet, so each gets its own **distinct, independently
generated** layout (same location codes and the same number of Ambient/
Chilled/Frozen slots overall, just shuffled onto different codes with a
different random seed per warehouse) so the three warehouses aren't identical
copies of each other. Every row in `dim_storage_locations` carries
`is_layout_synthetic` (`false` only for Lombard) so this is never silently
mixed up with real data. **Send us Kimmage's and Finglas's real shelving
plans and we'll swap them in** - it's a small, contained change to
`backend/scripts/seed_database.py`'s `_build_warehouse_type_maps()`.

The historical sales/inventory/purchase-order CSVs were captured against 5
warehouses (ids 1-5, from before this was scoped to Ireland). Rather than
throw away ~40% of the real historical rows, `warehouse_id` is folded down
onto the 3 real ones with `((old_id - 1) % 3) + 1`. This keeps all the real
transaction history, but it means "warehouse 4" and "warehouse 1" in the
original data now share a bucket - it is **not** a claim that they were
literally the same place.

## Real product-to-slot placement tracking (Session 8)

Clicking a Store Layout Heatmap cell (or an Overstocked/Underutilized
location row) opens a popup with that slot's capacity plus the products
genuinely on record as stored there. This wasn't possible before Session 8:
the Smart Placement Advisor could suggest a location, but confirming a
placement only ever flipped a `pending_placement` flag - it never actually
recorded *which* location a product ended up in. A new
`dim_product_placements` table (one row per product+warehouse - a product is
modeled as living in exactly one slot per warehouse, not spread across
several) now stores that assignment for real.

Two ways a row gets into that table, and the popup tells you which is which:

- **A real placement** - someone ran the Placement Advisor and clicked
  **"Place here"** on one of its suggestions (either from the New Products
  Awaiting Placement panel or, going forward, anywhere else that flow is
  wired up). `is_backfilled = false`.
- **A backfilled placement** - `app/migrations.py` found a product that's
  genuinely carrying stock in a warehouse (`fact_inventory_daily` has real
  rows for it) but had no placement on record, because this feature didn't
  exist when it was first stocked. Rather than leave the heatmap's popup
  empty for almost every product, `storage_optimizer.backfill_scored_placements()`
  assigns it to a location using **the exact same fit-score logic the live
  Smart Placement Advisor uses** - capacity headroom, right-sized-fit space
  efficiency, a fragility-appropriate shelf tier (fragile items steer away
  from high/overstock tiers), active-vs-overstock tier, and, for a fast
  mover (trailing 30-day sales velocity in the catalog's top quartile), a
  dispatch-proximity factor too. This replaced the very first version of
  this backfill (a plain `product_id mod` round robin, live for one prior
  session) once, via a guarded one-time upgrade in `migrations.py` - see its
  comments if you're digging into that history. **It's still a
  reconstruction, not real history** - nobody ever recorded where these
  products actually went, so it's still flagged `is_backfilled = true` and
  the popup still shows an amber "Backfilled" badge on it, rather than
  presenting a well-matched guess as confirmed fact. Backfilling only ever
  looks at pairs with no placement row yet (a real, person-confirmed
  placement is never touched or re-scored), and it re-runs on every backend
  startup, so a product that starts carrying stock later without ever going
  through a manual placement still gets placed automatically instead of
  showing up as an unexplained gap.
  - Because it scores every eligible product/warehouse pair against the
    same candidate pool of locations (rather than one product at a time
    through the UI), it simulates capacity filling up as it assigns -
    each choice reduces that location's remaining headroom for the next
    product scored against the same pool, so products don't all pile onto
    a single "best" slot.

### A location's capacity/utilization numbers are now computed live from real placements

Every location's `current_weight_kg`/`current_volume_cm3`/`utilization_pct` -
what colors a Store Layout Heatmap cell and what a location's popup shows -
comes from `v_storage_location_occupancy`, a database view
(`app/migrations.py`), **not** from `dim_storage_locations` directly. The
view sums each placed product's own weight/volume (from
`dim_product_placements` joined to `dim_product_dimensions`) per location, so
a slot's shown occupancy is always exactly "the products actually on record
here" - it can never disagree with what the click-to-inspect popup lists,
because it's computed from that same list. It's a plain view (not
materialized), so it's always current - nothing needs to remember to refresh
it after `mark_placed()` or a backfill run.

This replaced an earlier design where `current_weight_kg`/`current_volume_cm3`/
`utilization_pct` were static columns, set once at seed time to a random
percentage of a random capacity range with **no link at all** to which
products were tracked as being there. That mismatch was invisible under the
original round-robin backfill (which assigned a product to every location
regardless of how "full" its synthetic number claimed to be), but became
visible the moment real scoring shipped: a location seeded as, say, 92% full
gets correctly avoided by every scoring pass (nothing should recommend an
already-full-looking shelf), so it would honestly show zero tracked products
- which, next to a stale "92% full" figure, read as a flat contradiction if
you clicked around the heatmap. Every amber/red cell showing 0 products while
every blue cell showed several was that bug, not noise.

Only the **maximum capacity** (`max_weight_kg`/`max_volume_cm3` - the ceiling
a location's fill percentage is measured against) is still a synthetic
estimate; there's still no real per-slot maximum-capacity data to replace it
with, and `is_synthetic_capacity` now describes only that ceiling, not the
current/utilization figures next to it (the popup's wording says so). The
occupancy figure itself is computed from each product's own single-unit
weight/volume, not multiplied by its real on-hand stock quantity - consistent
with how `suggest_locations()`/`_score_location()` have always checked "does
one more of this fit," rather than introducing a second, incompatible notion
of shelf fullness.

`current_stock_on_hand` in the popup's product list, when present, is real -
pulled from that product's most recent `fact_inventory_daily` row for that
warehouse, not synthetic.

## Currency

All amounts are EUR (€). The source CSVs were GBP, so monetary columns
(`selling_price`, `unit_cost`, `gross_profit`, `revenue`, `cost`, `profit`,
`stock_value`, `order_cost`) are converted at a fixed, illustrative rate
(`FX_RATE_GBP_TO_EUR = 1.16` in `seed_database.py`) - **not** a live FX feed.
Change that constant and re-run the seed if you want a different rate.

## Suppliers

`dim_suppliers` now holds the real list you gave us. The first 50 names (in
the order you listed them) are mapped 1:1 onto the original synthetic
`supplier_id` 1-50 that the ~20k historical `fact_purchase_orders` rows
already reference, so all the real on-time-rate/order-value history stays
attached to the right supplier - only the display name changed. The
remaining names have no order history yet (new relationships going forward).
9 of those (3 per warehouse) are marked warehouse-exclusive rather than
common, to demonstrate "there could be more suppliers for different
warehouses" - add real warehouse-specific suppliers via **Admin → Suppliers**.

## Visual design

The app's look was given a deliberate pass beyond the initial build: a small
original set of line icons (`frontend/components/Icon.tsx`, ~35 icons drawn
from scratch - no icon library dependency) replaced every emoji across the
sidebar, KPI cards, alerts, status pills and buttons; the sidebar's active
nav item now slides between entries with a `framer-motion` animation
(already a dependency, not newly added) instead of just swapping a
background color; cards, buttons and table rows got hover/press feedback
and a shared elevation/radius/motion token scale
(`--shadow-sm/md/lg`, `--radius-sm/md/lg`, `--transition-fast/base` in
`app/globals.css`); and every chart's gridlines, axis text and tooltip
(`lib/theme.ts`'s `chartTooltipStyle`/`chrome`) now read the same
light/dark CSS variables as the rest of the UI, so a chart's chrome no
longer looks like a mismatched box dropped onto a themed card. The actual
data-encoding colors (category colors, stock-health/risk-level colors) were
left untouched - those came from a validated, colorblind-conscious palette
and were never the "generic" part.

**Session 6 follow-up: form controls and a leftover admin card.** A second
pass targeted three things that still looked out of place against the rest
of the redesigned UI. Every text input, `<select>` and textarea inside a
`.form-field` (every Admin "Add ___" page, the Delivery Risk Predictor form,
the Smart Placement Advisor form), plus the header filter pills
(`.select-pill`, `.date-filter`), gained a hover border, a focus ring
matching the rest of the app's purple accent, and a custom dropdown arrow
that matches the app's own `chevronDown` icon instead of the browser's
default triangle (a native `<select>`'s arrow can't read `currentColor`, so
it's swapped between two data-URI SVGs per theme via a `--select-arrow-image`
token). The ~15 form-feedback messages and status badges that hardcoded
`#d03b3b`/`#0ca30c`/`#fab219` directly were moved onto the new
`--status-*` tokens (see Known Limitations above for what didn't move, and
why). And **Admin → Settings**'s "Preview Impact" comparison cards, which
had been left as bare, unstyled `.kpi-card` divs since before the Session 6
redesign, were rebuilt with the actual `KpiCard` component - same
icon-badge/accent-bar treatment as every other KPI card in the app, and
using the same icon/color choices as the Alerts Center's own
critical/serious/warning breakdown for consistency. `KpiCard`'s `value` prop
was widened from `string` to `ReactNode` to allow this (fully backward
compatible - every other call site still just passes a plain string).

**Session 6 follow-up #2: fixes from an actual screenshot.** The two passes
above were both done by reading code, since this session has no way to open
the running app itself - the user then sent a real screenshot of Sales
Analytics, which surfaced issues code-reading alone couldn't have caught.

- **The global search bar floated in its own strip above the page header,**
  disconnected from the title/filters row below it - two stacked header
  bars instead of one. It's now rendered inside `TopBar` itself, alongside
  each page's own filters, so it's part of the same sticky, bordered header
  bar as everything else. (`AppLayout` no longer renders it separately;
  `components/GlobalSearch.tsx`'s own doc comment was updated to match.)
- **Chart X axes were printing raw ISO date strings** ("2025-12-05T00:00:00")
  as tick labels and tooltip headers, because none of `TrendLine`,
  `ForecastTrend`, or `StackedAreaTrend` had a tick/label formatter for the
  X axis (only the Y axis had one). New `formatAxisDate()` in `lib/theme.ts`
  turns a recognizable ISO date into a short "5 Dec" label and returns
  anything else unchanged, so it's safe as the default on any date-bucketed
  axis; applied to all three chart components' `tickFormatter`/
  `labelFormatter`.
- **A KPI card's "vs last period" delta showed a fractional value
  ("+292,572,587.7") next to a whole-number headline figure**
  ("€319,033,419") - `formatDelta()` in `lib/format.ts` always allowed up to
  1 decimal digit, which is fine for a plain count but looks like a bug next
  to a euro amount that's otherwise rounded to whole units. Added an
  `isCurrency` option that rounds to 0 decimals, and set it on the four
  money-valued deltas (Total Revenue, Total Profit, Total Order Value,
  Inventory at Risk). Note: the underlying `+1105.7%` swing itself is a
  separate, real data artifact (the period-over-period comparison window
  landing on a very low prior period in the seeded data), not a display bug
  - not something this pass fixed.
- **Verification:** 13 changed files pushed via the device bridge in one
  batch, all MD5-verified identical local vs. device; `npx tsc --noEmit`
  passed with zero errors afterward.

**Session 6 follow-up #3: KPI delta placement.** The green/red "vs last
period" delta badge used to sit beside the big number on the same line
(`.kpi-value-row` as a flex row). It now stacks underneath the number
instead (`.kpi-value-row` switched to `flex-direction: column`) - value on
top, delta directly below it, left-aligned under the title. `KpiCard` is a
single shared component used by every KPI row across all 5 dashboard pages
plus the Executive Overview and the Admin Settings "Preview Impact" cards,
so this one CSS change applies everywhere with no per-page edits needed.
Verified: MD5-identical `app/globals.css` local vs. device; `npx tsc
--noEmit` zero errors.

## Running it

Two terminals:

```powershell
# Terminal 1 - API on http://127.0.0.1:8000
cd D:\Projects\SHUPPA\shuppa-ops-platform\shuppa-ops-platform\backend
venv\Scripts\activate
python run.py

# Terminal 2 - UI on http://localhost:3000
cd D:\Projects\SHUPPA\shuppa-ops-platform\shuppa-ops-platform\frontend
npm run dev
```

Open http://localhost:3000 - it redirects to a login page. The API's
interactive docs are at http://127.0.0.1:8000/docs.

## What each page does

- **Executive Overview** (`/overview`) - the post-login landing page. Pulls
  the headline KPIs from all 5 dashboard pages plus the top items from the
  Alerts Center into one screen, each section linking through to its full
  page. Filter by warehouse.
- **Stock Summary** (`/stock`) - total products, stockout %, healthy/low/critical/
  overstock counts, inventory-at-risk value, a stock-health trend, low-stock
  table, and an alerts panel (thresholds: stockout >5%, overstock value >€200k,
  both editable in **Admin → Settings**). Filter by warehouse and by date
  (Before/After/Between). KPI cards show a "vs previous period" delta.
- **Supplier Summary** (`/suppliers`) - on-time/late %, per-supplier performance
  and reliability rating, monthly on-time trend, risk distribution, top suppliers
  by order value, and recent late deliveries. Filter by warehouse and by date.
  KPI cards show period-over-period deltas. Click a supplier row in the
  performance table to filter the late-deliveries table to just that
  supplier (drill-down); both tables support sorting, pagination and CSV
  export.
- **Stock Optimizer** (`/storage`) - a **New Products Awaiting Placement** panel
  (any product added via Admin shows up here until someone runs the advisor and
  confirms a slot), the storage tree, a product size analyzer, a utilization
  heatmap, overstocked/underutilized location lists, and the **Smart Placement
  Advisor**: give it a product's L/W/H/weight/fragility (or pick an existing
  product) and it scores every compatible storage location in that warehouse
  with a transparent, explainable fit score (capacity headroom, space
  efficiency, fragility-appropriate shelf tier, active vs. overstock tier) -
  see `backend/app/services/storage_optimizer.py`. **Click any heatmap cell
  (or a row in the Overstocked/Underutilized tables) to open a popup showing
  that exact slot's capacity plus every product actually on record as stored
  there** - see **Real product-to-slot placement tracking** below for what
  "on record" means. A **Reorder Suggestions** panel below it auto-computes a suggested
  reorder quantity for every LOW/CRITICAL product line (based on recent sales
  velocity, replenishing to a configurable target days-of-stock - falls back
  to a rough 2x-reorder-point estimate, flagged as such, when a product has no
  recent sales) plus its best historical supplier by on-time rate - see
  `stock_service.get_reorder_suggestions`.
- **Sales Analytics** (`/sales`) - revenue/units/profit KPIs (with
  period-over-period deltas), a revenue trend, a naive **revenue forecast**
  (linear-trend extrapolation, 7 days out - see `sales_service.get_forecast`;
  directional signal, not a seasonal demand model), optionally scoped to a
  single product category via a dropdown next to the forecast (still the same
  straight-line fit, just run against that category's own history - no
  weekly-seasonality modeling was added), top products, revenue by category,
  and sales by warehouse. Filter by warehouse and by date.
  "Avg. Transaction Value" is the average revenue per sales line, used as an
  honest stand-in for order-level AOV since the source data has no
  order-level table.
- **Delivery Risk Predictor** (`/delivery`) - pick a supplier/product/warehouse/
  quantity/lead time and get a risk score with an explanation panel, plus a
  table of the historically riskiest purchase orders. Filter by warehouse and
  by date. KPI cards show period-over-period deltas.
- **Alerts Center** (`/alerts`) - every active alert across all 4 data pages
  and the Stock Optimizer, in one place, sorted by severity and linking back
  to its source page (see `backend/app/services/alerts_service.py`). The
  sidebar's "Alerts Center" link shows a live count of critical alerts.
- **Admin** (`/admin/*`, ADMIN role only) - add a warehouse, add a supplier
  (common or warehouse-exclusive), add a product with its real physical
  dimensions (this immediately flags it for placement - see Stock Optimizer
  above), or a storage location + a range of sub-location slots. **Bulk
  Upload** now covers all three of Products, Suppliers, and Storage Locations
  (CSV paste or file, per-type templates and validation). **Manage Users**
  (add a login, deactivate one, reset a password, see lockout state and last
  login). **Settings** (edit the alert thresholds every other page reads) has
  a **Preview Impact** button that shows how many alerts would fire before vs.
  after a proposed change, without saving it. **Audit Log** (every admin
  mutation, who did it, when) can now be filtered by username, action, and
  date range.
- **Global search** (top of every page) - quick "jump to" lookup by product
  or supplier name; picking a result navigates to the Stock Optimizer (for a
  product) or Supplier Summary pre-filtered to that supplier.

### Session 5 / Phase 8 additions

These were added on top of the 5-page plan above, based on a round of
"what else could be added" brainstorming - each is clearly labeled where it
leans on a proxy signal rather than data the schema doesn't actually have:

- **Top Movers** (`/storage`, and on the new Floor View) - the fastest-selling
  products (top quartile of sales velocity), and the Smart Placement Advisor
  now nudges a top mover toward locations with a lower `location_code`
  within its candidate pool as a **synthetic "closer to dispatch" proxy** -
  there's no real aisle/travel-distance data, so this only reasons about
  relative position within the existing candidate set, not actual distance.
- **Correlated Products** (`/sales`) - for a given product, other products
  whose daily sales history moves together (Pearson correlation ≥ 0.4 over
  the last 90 days). This is **not real market-basket analysis** - the
  source data has no order-level "bought together" table, only daily
  per-product totals, so this is a same-day-trend proxy, not "customers who
  bought X also bought Y".
- **Rebalancing Suggestions** (`/stock`) - flags a product that's LOW/CRITICAL
  in one warehouse while a healthier surplus sits in another, as a candidate
  for an inter-warehouse transfer instead of a fresh supplier order.
- **Dead Stock report** (`/stock`) - products with no sales in the last N
  days (default 60, configurable in **Admin → Settings** as
  `dead_stock_days_threshold`) still sitting in stock, with the cash value
  tied up.
- **Margin Density** (`/storage`) - ranks products by profit per unit volume
  (profit ÷ L×W×H), surfacing bulky, low-margin items that may be worth
  less prime shelf space. This is a **product-level proxy, not a true
  per-shelf-slot margin figure** - the schema has no product-to-slot
  assignment table, so it can't say what's actually earning per square foot
  of a specific location today.
- **Draft PO** (`/storage`, Reorder Suggestions panel) - turns a reorder
  suggestion into a saved draft request (product, quantity, supplier,
  warehouse) an admin can review later via `GET /stock/draft-pos`. This
  **creates a draft record, not a live purchase order** - nothing is sent to
  a supplier and no real ordering/approval workflow exists yet.
- **Alert hints** (`/alerts`) - each alert now carries a short, rule-based
  "likely cause" hint (e.g. "sales velocity outpacing reorder point") -
  plain if/else thresholds, not an LLM-generated explanation.
- **Floor View** (`/floor`) - today's Reorder Suggestions and Top Movers in a
  compact, scannable card format, for a picker or warehouse worker who won't
  be at a desk. Originally built as a standalone, no-sidebar page for a
  phone-width screen, but that left it a dead end with no way back to the
  rest of the dashboard - it now uses the same `AppLayout`/Sidebar/`TopBar`
  shell as every other page (reachable from the sidebar, escapable like
  anywhere else), while keeping the compact card styling for the lists
  themselves.

Three other brainstormed ideas were deliberately **not** built this round,
by the user's own choice: a natural-language search bar and auto-generated
weekly summaries (both need a paid LLM API key), and a scheduled email
digest (needs an email-sending service) - all three need external
credentials only the user can provide.

Every dashboard page's date filter resolves "Before"/"After"/"Between" down to
a plain `date_from`/`date_to` pair that the API accepts on the relevant
endpoints (see `date_range_clause` in `backend/app/services/db_utils.py`).
KPI "vs previous period" deltas mirror the active date range's length when
one is set, or compare trailing 30 days vs. the prior 30 when it isn't (see
`previous_period_window`/`resolve_comparison_window` in the same file).

## Known limitations (read before you ask "why is X only okay, not great")

**The delivery-risk model is honest about being weak.** Train AUC ≈ 0.53,
barely above a coin flip - this looks like procedurally-generated demo data
rather than a real operational pattern. LOW/MEDIUM/HIGH is bucketed by
percentile rank within the training population, not a fixed probability
cutoff, so the UI still shows a meaningful relative spread.

**Auth is deliberately scoped, not enterprise SSO.** Bcrypt password hashing,
httpOnly-cookie JWTs, self-service registration with Admin approval, and a
real forgot-password email flow (all added in Session 7 - see **Login
security** above) cover what an internal ops tool with a modest user base
actually needs. There are still no refresh tokens and no server-side session
table, so a stolen (not just guessed) valid JWT stays usable until it expires
- there's no way to revoke one early short of rotating `JWT_SECRET_KEY` and
invalidating every session at once. The JWT secret (`JWT_SECRET_KEY`) still
defaults to a dev value for local convenience, but the backend now refuses to
start with that default if `ENVIRONMENT=production` - set a real one via
environment variable before this is exposed beyond localhost.

**Backfilled product placements are a reconstruction, not real history.**
Most products showing up in a heatmap-cell popup today got a placement the
migration made up (since Session 9, scored with the same fit-score logic a
live Smart Placement Advisor suggestion uses - capacity headroom, space
efficiency, fragility-appropriate tier, overstock tier, and fast-mover
proximity - not the original launch-day round robin) because nobody tracked
real placements before this feature existed - not because anyone confirmed a
product actually sits in that exact slot. The popup flags every such row
with a "Backfilled" badge specifically so a well-scored guess is never
mistaken for a real inventory audit. Only a product placed through the
Advisor's "Place here" action from here on is a genuine, chosen placement.
See **Real product-to-slot placement tracking** above for the full
mechanics.

**A location's maximum capacity is still a synthetic estimate.** As of the
`v_storage_location_occupancy` view, everything ELSE about a location's shown
capacity - `current_weight_kg`, `current_volume_cm3`, `utilization_pct` - is
computed live from real `dim_product_placements` rows, not a fabricated
number, so it can't disagree with the popup's own product list anymore. But
`max_weight_kg`/`max_volume_cm3` (the ceiling that percentage is measured
against) is still a randomized value from a plausible range chosen at seed
time - there's no real per-slot maximum-capacity data in the source CSVs to
replace it with. So a location's utilization_pct is a real numerator over a
guessed denominator: trust the relative signal (this shelf has more/less on
it than that one) more than the absolute percentage. Also worth knowing: the
occupancy figure sums each placed product's own single-unit weight/volume,
not that quantity's real on-hand stock count - a shelf tracking one unit each
of 20 different products shows the same occupancy as one tracking 20 units of
a single product, since the whole placement/scoring system has always
reasoned in single-unit terms (see `_score_location`'s docstring).

**The Sales Analytics forecast is a naive linear-trend extrapolation**, not a
seasonal or ML demand model - it fits a straight line to the trailing 30 days
and projects it 7 days forward (`sales_service.get_forecast`). The
per-category filter added in Session 4 only scopes *which* history the same
straight-line fit runs against - it does not add weekly/monthly seasonality,
holiday effects, or any per-product granularity. Treat it as "which way is
this heading", not a demand plan to order stock against. The **Reorder
Suggestions** panel on Stock Optimizer is deliberately a separate, simpler
velocity calculation (not tied to this forecast) - there's no per-product
forecast yet to correlate reorder timing against.

**Dark mode covers the app's shared components and CSS-variable-driven
styles.** The handful of older inline `style={{ color: "#..." }}` values that
were left over from the original dark-mode pass (form success/error text,
locked-account and failed-login badges, dead-stock/draft-PO messages) were
swept up in Session 6 onto four new semantic tokens -
`--status-good`/`--status-warning`/`--status-serious`/`--status-critical` in
`app/globals.css`, matching `lib/theme.ts`'s own `status` object
value-for-value - so there's now one place to change them instead of ~15
copy-pasted hex literals. The handful of places that tint an icon badge's
background from the same color (`KpiCard`'s `accent` prop, the Alerts
Center's per-level icons) still use literal hex rather than the new tokens,
because that badge-tinting trick concatenates a transparency suffix onto the
color string (`${accent}1f`) and can't do that to a `var(...)` reference -
not an oversight, just a real constraint of that technique.

**A KPI card's "vs last period" percentage can look extreme** (e.g. a
Total Revenue delta of "+1105.7%") when the comparison window happens to
land on a very low-activity stretch of the seeded data - the math itself is
correct (see `previous_period_window()`/`compute_deltas()` in
`db_utils.py`), it's just that a near-zero denominator makes any real
increase look huge as a percentage. Session 6 fixed the *decimal
formatting* of these deltas (they no longer show a fractional value next to
a whole-number headline figure) but did not investigate or change the
underlying period-window math - that's a separate question of whether the
seeded data's early history is realistic enough for period comparisons to
be meaningful there.

**Rate limiting is in-memory and per-process** (see Account lockout /
rate limiting above) - fine for the current single-instance deployment, not
a substitute for a shared limiter (e.g. Redis-backed) if this ever runs
behind a load balancer with multiple backend processes.

**Kimmage's and Finglas's shelving layouts are synthetic**, generated to be
different from each other and from Lombard, but not based on anything real -
see Multi-warehouse layout above.

**The GBP→EUR rate is a fixed illustrative constant**, not a live FX feed -
see Currency above.

**Why I couldn't run `npm run dev` / `pytest` myself to prove it all works
end-to-end:** I did as much verification as the sandbox allows - every backend
module passes `py_compile` (both in my cloud sandbox and directly on your
machine's Linux shell), the storage-optimizer scoring and delivery-risk math
have isolated unit tests with mocked data (`backend/test_logic.py`), the seed
script's ETL logic was run end-to-end against your real CSVs in a sandboxed
test harness (minus the actual DB write), and the whole frontend passes
`npx tsc --noEmit` with zero errors - run directly on your machine, against
your real `node_modules`. I also tried `npm run build` on your machine's
Linux shell as a further check; it failed on a missing native SWC binary for
that specific Linux sandbox (`@next/swc-linux-x64-gnu`/`-musl` not
installed) - that's an artifact of the sandboxed shell Claude runs commands
in, not a real problem with the code (your actual `next dev`/`next build` on
Windows uses a different, already-installed SWC binary and is unaffected).
My cloud environment has no network path to your Neon database at all, and I
can't launch `uvicorn` or click through the app myself. So the seed script,
the live API, and `next dev`/`next build` on your normal Windows terminal
still need to be run by you, per the steps above, before you rely on this -
especially the new Session 3 features (Alerts Center, Settings, Manage
Users, Bulk Upload, Audit Log, forecast, KPI deltas, drill-down, global
search), none of which have been clicked through yet.

**Session 4 verification (rate limiting, reorder suggestions, category
forecast, lockout, bulk upload for suppliers/locations, shared filters,
skeletons, dark mode, polling):** all 53 changed files were pushed to this
machine and their MD5 checksums were verified identical on both sides after
transfer (not just a "write succeeded" response). Every changed backend
module re-passed `py_compile` directly on your machine's Linux shell, and the
full logic-test suite (`test_logic.py`, `test_logic_phase7.py` - the latter
new this session, covering KPI-delta math, settings-preview isolation under
concurrent requests, the reorder-quantity/fallback-estimate logic, the
category-scoped forecast SQL, the audit-log filter query, and the rate
limiter's counting/reset behavior) passed against real `pydantic`/`pandas`/
`numpy` in my cloud sandbox, which mirrors this code exactly (verified by the
same checksums). `npx tsc --noEmit` again passed with zero errors, run
directly on your machine against your real `node_modules`, covering every
new/changed component and page. What I could **not** do this round: install
`fastapi`/`sqlalchemy` in your machine's Linux automation shell to exercise
the real FastAPI app object (that shell has no network access, unlike your
actual Windows Python venv, which already has those packages) - so router
wiring, the rate-limiting middleware's actual HTTP behavior, and the new
`/stock/reorder-suggestions`, `/sales/categories`, `/admin/suppliers/bulk`,
`/admin/locations/bulk`, and `/admin/audit-log/filters` endpoints have not
been hit with a real request yet. Start the API and UI per **Running it**
above and click through Stock Optimizer, Sales Analytics, Admin → Bulk
Upload/Audit Log/Settings/Manage Users, and the dark-mode toggle before
relying on this.

**The Top Movers "closer to dispatch" placement nudge is a synthetic
proxy** (see Session 5 additions above) - it ranks candidate locations by
`location_code` within the same warehouse+storage-type pool, not by any real
aisle or travel-distance measurement.

**Correlated Products (Sales Analytics) is a same-day sales-trend proxy, not
real market-basket / "bought together" analysis** - the source data has no
order-level transaction table to compute true co-purchase rates from.

**Margin Density is a product-level profit-per-volume proxy, not a true
per-shelf-slot margin figure** - there's no product-to-slot assignment table
to compute what a specific location is actually earning today.

**Draft PO creates a saved draft request, not a live purchase order** -
nothing is transmitted to a supplier and there's no approval/ordering
workflow around it yet; it's a starting point for an admin to act on
manually.

**Session 5 verification (Top Movers, Correlated Products, Rebalancing,
Dead Stock, Margin Density, Draft PO, alert hints, Floor View):** all 25
changed/new files were pushed to this machine and their MD5 checksums were
verified identical on both sides after transfer. Every changed/new backend
module re-passed `python3 -m py_compile` directly on your machine's Linux
shell, and the full logic-test suite - `test_logic.py`, `test_logic_phase7.py`,
and the new `test_logic_phase8.py` (covering the velocity/proximity scoring,
the sales-correlation math, rebalancing/dead-stock/margin-density queries,
draft-PO request validation, and the alert-hint rules against monkeypatched
fake data) - passed against real `pydantic`/`pandas`/`numpy` in my cloud
sandbox, which mirrors this code exactly (verified by the same checksums).
`npx tsc --noEmit` again passed with zero errors, run directly on your
machine against your real `node_modules`. One new finding this round: your
machine's Linux automation shell (the one Claude runs commands in here) has
never had `pydantic`/`sqlalchemy`/`fastapi` installed and has no PyPI network
access - confirmed by `test_logic.py` itself failing with the same
`ModuleNotFoundError` there, unrelated to anything changed this session.
That's a pre-existing gap in that shell, not your real Windows Python venv
(which already has those packages and is what actually runs the app) - it
just means the logic-test suite can only be run for real in my cloud sandbox,
not on this shell, going forward. As with every prior phase, none of these 8
new features have been clicked through in the live running app yet - start
the API and UI per **Running it** above and try the Stock Optimizer's Top
Movers/Margin Density/Draft PO, Sales Analytics' Correlated Products, Stock
Summary's Dead Stock/Rebalancing panels, the Alerts Center hints, and
`/floor` on a phone-width window before relying on this.

**The visual design pass hasn't been looked at in a real browser yet.**
Every changed file passed `npx tsc --noEmit` with zero errors (run directly
on your machine) and all 26 changed/new files were checksum-verified
identical, local vs. your machine, same as every other phase - but nobody
has opened the app and actually looked at the new icons, hover states, the
sidebar's sliding active-item animation, or how the charts render in dark
mode. Start the API and UI per **Running it** above and click through a few
pages (toggle dark mode too) before assuming it looks right.

**Security note:** your Neon Postgres password is stored in plain text in
several files in this project. That's fine for a local dev project, but if
this repo is ever pushed somewhere public or shared, rotate that password
(and the JWT secret) first.

## Extending it

- Send us Kimmage's and Finglas's real shelving layouts to replace the
  synthetic ones (see Multi-warehouse layout above).
- Add real product dimensions/weights whenever you have them for existing
  catalogued products - swap them into `dim_product_dimensions` (same
  columns) and stop treating that table as synthetic. New products go through
  **Admin → Add Product** (or **Bulk Upload** for many at once), which always
  captures real dimensions.
- Add a new dashboard-configurable threshold: add its default to
  `DEFAULT_SETTINGS` in `app/migrations.py` (and `SETTINGS_DEFAULTS` in
  `scripts/seed_database.py` for fresh installs), read it with
  `settings_service.get_setting_float(...)`, and it'll automatically show up
  on the **Admin → Settings** page (any key not in `SETTING_META` on that
  page still renders, just without a friendly label).
- Wire a new page's alerts into the unified feed by adding a signal to
  `alerts_service.get_all_alerts` (wrap it in try/except so it degrades
  gracefully like the existing ones).
- The old `backend/app/services/analytics_service.py` / `ml_service.py` and
  the executive/inventory/products pages from the original scaffold have been
  removed - they didn't match the final 5-page plan and referenced SQL views
  that were never created (not to be confused with the new `/overview`
  Executive Overview page added in Session 3, which is unrelated).
