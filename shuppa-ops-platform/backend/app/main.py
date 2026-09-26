from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.migrations import run_migrations
from app.rate_limit import RateLimitMiddleware
from app.routers import (
    admin,
    alerts,
    auth,
    delivery,
    insights,
    returns,
    sales,
    search,
    settings,
    stock,
    storage,
    suppliers,
)

app = FastAPI(title="Shuppa Operations Intelligence Platform")

# Order matters: middleware runs in reverse of the order it's added (the
# last one added wraps the others), and CORS needs to run on every response,
# including a 429 from the rate limiter, so a throttled browser request still
# gets a readable error instead of a CORS failure masking it. Adding
# RateLimitMiddleware first and CORSMiddleware second achieves that.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _on_startup():
    # Idempotent schema migrations (new tables/columns added after the first
    # seed) - see app/migrations.py. Safe to run on every restart.
    run_migrations()


app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(stock.router)
app.include_router(suppliers.router)
app.include_router(storage.router)
app.include_router(sales.router)
app.include_router(delivery.router)
app.include_router(insights.router)
app.include_router(alerts.router)
app.include_router(search.router)
app.include_router(settings.router)
app.include_router(returns.router)


@app.get("/")
def root():
    return {
        "name": "Shuppa Operations Intelligence Platform API",
        "pages": ["/stock", "/suppliers", "/optimizer", "/sales", "/delivery"],
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
