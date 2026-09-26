import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    # python-dotenv is optional - DATABASE_URL can also be set directly in
    # the environment. See backend/.env.example.
    pass

# No real default on purpose - copy backend/.env.example to backend/.env and
# set your own DATABASE_URL there (never commit real credentials).
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/shuppa_dev",
)

# Comma-separated list of origins allowed to call this API (the Next.js dev
# server runs on :3000 by default).
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")

# Simple per-IP API rate limiting (see app/rate_limit.py). This is an
# in-memory, single-process limiter meant to blunt accidental hammering
# (a runaway frontend polling loop, a bad script) - it is NOT a substitute
# for a real rate limiter (e.g. Redis-backed) in a multi-process/multi-
# instance deployment, since each process keeps its own counters.
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "300"))
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# A tighter, separate limit applied only to the credential-guessing-prone
# auth endpoints (/auth/login, /auth/register, /auth/forgot-password) - see
# app/rate_limit.py. Deliberately much stricter than the general API limit
# above: a real user rarely needs more than a couple of login attempts a
# minute, but a script trying to guess passwords wants hundreds.
LOGIN_RATE_LIMIT_REQUESTS = int(os.getenv("LOGIN_RATE_LIMIT_REQUESTS", "10"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "300"))

# "production" enables a few checks that would be too strict for local dev:
# app/auth.py refuses to start with the default JWT secret, and the auth
# cookie is only marked Secure (HTTPS-only) when this is "production" (a
# Secure cookie is silently dropped by the browser over plain http://
# localhost, which is how local dev runs).
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Used to build the link inside password-reset emails (e.g.
# "https://shuppa.example.com/reset-password?token=..."). Defaults to the
# Next.js dev server's own origin.
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

# SMTP settings for password-reset emails (app/services/email_service.py).
# All optional: if SMTP_HOST is empty, email_service logs the message to the
# console instead of sending it, so forgot-password still works end-to-end
# in local dev without a real mail account - see that module's docstring.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "no-reply@shuppa.example.com")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() not in ("false", "0", "no")
