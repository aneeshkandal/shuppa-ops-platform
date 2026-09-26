"""Global search: quick lookup across products and suppliers by name, for
the search bar in the top bar. Kept intentionally simple (ILIKE, small
limits) - this is a "jump to" tool, not a full-text search engine.
"""

from app.services.db_utils import query_records


def search(q: str, limit: int = 8) -> dict:
    like = f"%{q}%"
    products = query_records(
        """
        SELECT product_id, product_name, category
        FROM dim_products
        WHERE product_name ILIKE :q
        ORDER BY product_name
        LIMIT :limit
        """,
        {"q": like, "limit": limit},
    )
    suppliers = query_records(
        """
        SELECT supplier_id, supplier_name
        FROM dim_suppliers
        WHERE supplier_name ILIKE :q
        ORDER BY supplier_name
        LIMIT :limit
        """,
        {"q": like, "limit": limit},
    )
    return {"products": products, "suppliers": suppliers}
