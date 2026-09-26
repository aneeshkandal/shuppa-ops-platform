"""Supplier Returns - tracking wrong/extra items a supplier delivered that
need resolving. Unlike most of this app's demo data, this feature starts
completely empty (see dim_supplier_returns/dim_supplier_return_items in
app/migrations.py) and is only ever populated by real admin/warehouse usage,
the same "starts empty on purpose" precedent as dim_draft_purchase_orders.

Resolution model (per product line, not per whole return - each item in a
return can go a different way):
  - RETURNED: the item was physically shipped back to the supplier. Always
    available regardless of whether product_id is known.
  - PO_GENERATED: the wrongly-delivered/extra item is actually a recognized
    catalog product the warehouse wants to keep and pay for properly - reuses
    stock_service.create_draft_po() so it shows up alongside every other
    draft PO. Only valid when the item has a product_id.
  - LISTED_AS_NEW_PRODUCT: the item isn't in the catalog at all - the
    frontend sends the admin to the Add Product form (pre-filled with
    product_name_reported) and, once that form succeeds, calls back here with
    the new product_id. Only valid when the item has NO product_id (a known
    product should never be "listed as new").
"""

from typing import Optional

from sqlalchemy import text

from app.auth import CurrentUser
from app.database import engine
from app.models.schemas import CreateSupplierReturnRequest, DraftPurchaseOrderRequest, ResolveReturnItemRequest
from app.services import audit_service, stock_service
from app.services.db_utils import query_one, query_records, warehouse_filter_clause


def list_suppliers_for_warehouse(warehouse_id: Optional[int] = None) -> list[dict]:
    """Supplier dropdown for the "File a Return" form. Not admin-gated (unlike
    GET /admin/suppliers), since filing a return is a regular warehouse
    action - mirrors admin_service.list_suppliers()'s query exactly."""
    if warehouse_id is None:
        return query_records("SELECT supplier_id, supplier_name FROM dim_suppliers ORDER BY supplier_name")
    return query_records(
        """
        SELECT supplier_id, supplier_name FROM dim_suppliers
        WHERE warehouse_id IS NULL OR warehouse_id = :w
        ORDER BY supplier_name
        """,
        {"w": warehouse_id},
    )


def create_return(req: CreateSupplierReturnRequest, actor: CurrentUser) -> dict:
    """Files a new return with one or more product line items, all starting
    life as PENDING. Just records intent, same as create_draft_po - nothing
    here notifies the supplier automatically."""
    supplier = query_one("SELECT supplier_name FROM dim_suppliers WHERE supplier_id = :sid", {"sid": req.supplier_id})
    if not supplier:
        raise ValueError(f"supplier_id {req.supplier_id} not found")

    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO dim_supplier_returns (supplier_id, warehouse_id, filed_by, scheduled_return_date, note)
                VALUES (:sid, :wh, :by, :sched, :note)
                RETURNING return_id
                """
            ),
            {
                "sid": req.supplier_id,
                "wh": req.warehouse_id,
                "by": actor.username,
                "sched": req.scheduled_return_date,
                "note": req.note,
            },
        )
        return_id = result.scalar()

        for item in req.items:
            conn.execute(
                text(
                    """
                    INSERT INTO dim_supplier_return_items
                        (return_id, product_id, product_name_reported, quantity, reason)
                    VALUES (:rid, :pid, :name, :qty, :reason)
                    """
                ),
                {
                    "rid": return_id,
                    "pid": item.product_id,
                    "name": item.product_name_reported,
                    "qty": item.quantity,
                    "reason": item.reason,
                },
            )

    audit_service.log_action(
        actor, "file_supplier_return", "supplier_return", return_id,
        f"{len(req.items)} item(s) from {supplier['supplier_name']}",
    )
    return get_return_detail(return_id)


def list_returns(warehouse_id: Optional[int] = None) -> list[dict]:
    """Powers the Supplier Summary page's Returns card. One row per return,
    with an item_count and pending_count so the table can show at a glance
    which returns still need admin attention."""
    return query_records(
        f"""
        SELECT
            r.return_id, r.supplier_id, s.supplier_name, r.warehouse_id,
            r.filed_at, r.filed_by, r.scheduled_return_date, r.note,
            COUNT(i.return_item_id) AS item_count,
            COUNT(i.return_item_id) FILTER (WHERE i.resolution = 'PENDING') AS pending_count
        FROM dim_supplier_returns r
        JOIN dim_suppliers s ON s.supplier_id = r.supplier_id
        LEFT JOIN dim_supplier_return_items i ON i.return_id = r.return_id
        WHERE 1=1 {warehouse_filter_clause(warehouse_id, "r.warehouse_id")}
        GROUP BY r.return_id, r.supplier_id, s.supplier_name, r.warehouse_id,
                 r.filed_at, r.filed_by, r.scheduled_return_date, r.note
        ORDER BY r.filed_at DESC
        """,
        {"warehouse_id": warehouse_id},
    )


def get_return_detail(return_id: int) -> dict:
    """Full return header + all of its line items, for the detail modal
    opened by clicking a supplier's name in the Returns card."""
    header = query_one(
        """
        SELECT r.return_id, r.supplier_id, s.supplier_name, r.warehouse_id,
               r.filed_at, r.filed_by, r.scheduled_return_date, r.note
        FROM dim_supplier_returns r
        JOIN dim_suppliers s ON s.supplier_id = r.supplier_id
        WHERE r.return_id = :rid
        """,
        {"rid": return_id},
    )
    if not header:
        raise ValueError(f"return_id {return_id} not found")

    items = query_records(
        """
        SELECT return_item_id, return_id, product_id, product_name_reported, quantity, reason,
               resolution, resolved_at, resolved_by, linked_draft_po_id, created_product_id
        FROM dim_supplier_return_items
        WHERE return_id = :rid
        ORDER BY return_item_id
        """,
        {"rid": return_id},
    )
    header["items"] = items
    return header


def resolve_return_item(return_item_id: int, req: ResolveReturnItemRequest, actor: CurrentUser) -> dict:
    """Admin's decision on one pending line item. Enforces the same
    product_id-driven guard the frontend uses to decide which buttons to
    show, so a stale UI or a direct API call can't produce a nonsensical
    result (a "known" product listed as new, or a PO drafted for a product
    that doesn't exist)."""
    item = query_one(
        "SELECT * FROM dim_supplier_return_items WHERE return_item_id = :id", {"id": return_item_id}
    )
    if not item:
        raise ValueError(f"return_item_id {return_item_id} not found")
    if item["resolution"] != "PENDING":
        raise ValueError(f"return item {return_item_id} was already resolved as {item['resolution']}")

    if req.resolution == "PO_GENERATED":
        if not item["product_id"]:
            raise ValueError("Cannot generate a PO for an item with no recognized product_id")
        po = stock_service.create_draft_po(
            DraftPurchaseOrderRequest(
                product_id=item["product_id"],
                warehouse_id=query_one(
                    "SELECT warehouse_id FROM dim_supplier_returns WHERE return_id = :rid",
                    {"rid": item["return_id"]},
                )["warehouse_id"],
                quantity=req.quantity or item["quantity"],
                note=req.note or f"Re-inbound from supplier return #{item['return_id']}",
            ),
            actor,
        )
        linked_draft_po_id = po["draft_po_id"]
        created_product_id = None
    elif req.resolution == "LISTED_AS_NEW_PRODUCT":
        if item["product_id"]:
            raise ValueError("Item already matches a known product_id - it can't be listed as a new product")
        if not req.created_product_id:
            raise ValueError("created_product_id is required for LISTED_AS_NEW_PRODUCT")
        linked_draft_po_id = None
        created_product_id = req.created_product_id
    else:  # RETURNED
        linked_draft_po_id = None
        created_product_id = None

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE dim_supplier_return_items
                SET resolution = :res, resolved_at = NOW(), resolved_by = :by,
                    linked_draft_po_id = :draft_po, created_product_id = :product
                WHERE return_item_id = :id
                """
            ),
            {
                "res": req.resolution,
                "by": actor.username,
                "draft_po": linked_draft_po_id,
                "product": created_product_id,
                "id": return_item_id,
            },
        )

    audit_service.log_action(
        actor, "resolve_return_item", "supplier_return_item", return_item_id, req.resolution
    )
    return query_one(
        """
        SELECT return_item_id, return_id, product_id, product_name_reported, quantity, reason,
               resolution, resolved_at, resolved_by, linked_draft_po_id, created_product_id
        FROM dim_supplier_return_items
        WHERE return_item_id = :id
        """,
        {"id": return_item_id},
    )
