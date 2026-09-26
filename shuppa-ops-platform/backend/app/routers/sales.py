from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import CurrentUser, effective_warehouse_id, get_current_user
from app.services import sales_service

router = APIRouter(prefix="/sales", tags=["Sales Analytics"])


@router.get("/kpis")
def kpis(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return sales_service.get_kpis(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trend")
def trend(
    granularity: str = Query("day", pattern="^(day|month)$"),
    days: int = Query(31, ge=7, le=365),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return sales_service.get_trend(
            granularity, days, effective_warehouse_id(warehouse_id, current_user), date_from, date_to, category
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forecast")
def forecast(
    forecast_days: int = Query(7, ge=1, le=30),
    history_days: int = Query(30, ge=7, le=180),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """`category` optionally scopes the forecast to one product category
    instead of the warehouse-wide total - see sales_service.get_forecast."""
    try:
        return sales_service.get_forecast(
            forecast_days,
            history_days,
            effective_warehouse_id(warehouse_id, current_user),
            date_from,
            date_to,
            category,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def categories(current_user: CurrentUser = Depends(get_current_user)):
    """Powers the Sales Analytics forecast's category-filter dropdown."""
    try:
        return sales_service.get_categories()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-products")
def top_products(
    limit: int = Query(10, ge=1, le=100),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return sales_service.get_top_products(limit, effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-category")
def by_category(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return sales_service.get_by_category(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-warehouse")
def by_warehouse(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return sales_service.get_by_warehouse(date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/correlated-products")
def correlated_products(
    product_id: int = Query(..., description="Find products with a similar demand pattern to this one"),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    limit: int = Query(5, ge=1, le=20),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Products whose daily sales pattern correlates with the given
    product's - see sales_service.get_correlated_products for the important
    caveat that this is a demand-pattern proxy, NOT real market-basket /
    co-purchase data (this dataset has no order-level transactions)."""
    try:
        return sales_service.get_correlated_products(product_id, effective_warehouse_id(warehouse_id, current_user), limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/avg-order-value")
def avg_order_value(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        return sales_service.get_avg_order_value(effective_warehouse_id(warehouse_id, current_user), date_from, date_to)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order-trend")
def order_trend(
    granularity: str = Query("day", pattern="^(day|month)$"),
    days: int = Query(31, ge=7, le=365),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Order-count/order-revenue trend - see sales_service.get_order_trend
    and backfill_synthetic_orders for what's real vs. synthetic here."""
    try:
        return sales_service.get_order_trend(
            granularity, days, effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order-time-distribution")
def order_time_distribution(
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Order volume by hour of day - see sales_service.get_order_time_distribution
    for why the shape closely tracks a fixed synthetic demand curve."""
    try:
        return sales_service.get_order_time_distribution(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/customer-growth")
def customer_growth(
    days: int = Query(90, ge=7, le=365),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """New-vs-returning customer counts and a new-customer trend - see
    sales_service.get_customer_growth and backfill_synthetic_orders for what's
    real vs. synthetic here (customer identity itself has no real basis
    anywhere in Shuppa's source data)."""
    try:
        return sales_service.get_customer_growth(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to, days
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/delivery-performance")
def delivery_performance(
    days: int = Query(31, ge=7, le=365),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Last-mile (customer-facing) delivery performance - see
    sales_service.get_delivery_performance for why this is deliberately a
    separate concept from the Delivery Risk Predictor page (which models
    real supplier-to-warehouse deliveries, not this fabricated
    warehouse-to-customer leg)."""
    try:
        return sales_service.get_delivery_performance(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to, days
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/return-cancellation")
def return_cancellation(
    days: int = Query(31, ge=7, le=365),
    warehouse_id: Optional[int] = Query(None, ge=1, le=3),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return/cancellation rate and estimated lost revenue - see
    sales_service.get_return_cancellation_insights; there is no real
    returns/cancellations data anywhere in Shuppa's source data."""
    try:
        return sales_service.get_return_cancellation_insights(
            effective_warehouse_id(warehouse_id, current_user), date_from, date_to, days
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
