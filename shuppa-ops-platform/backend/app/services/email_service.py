"""Outbound email for the forgot-password flow, via plain stdlib smtplib -
deliberately not a new pip dependency (this project has already been bitten
once by an unpinned auth-adjacent dependency silently breaking, see the
bcrypt/passlib note in README's Session 3 writeup), and smtplib works with
any standard SMTP provider: Gmail (with an app password), SendGrid,
Mailgun, Postmark, AWS SES's SMTP interface, or a real company mail server.

If SMTP_HOST isn't configured (the out-of-the-box default), send_email()
doesn't fail the request - it logs the message to the console instead, the
same "degrade honestly instead of crashing" pattern already used elsewhere
in this codebase (see alerts_service's per-signal try/except). That keeps
the forgot-password flow fully testable in local dev without a real mailbox:
the reset link just shows up in the backend's terminal output instead of an
inbox.
"""

import smtplib
from email.mime.text import MIMEText

from app.config import (
    FRONTEND_BASE_URL,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)


def send_email(to_email: str, subject: str, body_text: str) -> bool:
    """Returns True if it actually sent over SMTP, False if it fell back to
    console logging (not configured) or the SMTP call itself failed - either
    way this never raises, since a broken mail server shouldn't 500 the
    forgot-password endpoint (which must return its generic response either
    way - see routers/auth.py)."""
    if not SMTP_HOST:
        print(f"[email_service] SMTP not configured - logging email instead of sending it.\n"
              f"  To: {to_email}\n  Subject: {subject}\n  Body:\n{body_text}\n")
        return False

    message = MIMEText(body_text)
    message["Subject"] = subject
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = to_email

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM_EMAIL, [to_email], message.as_string())
        return True
    except Exception as exc:  # noqa: BLE001 - any SMTP failure degrades the same way
        print(f"[email_service] Failed to send email to {to_email}: {exc}")
        return False


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    reset_link = f"{FRONTEND_BASE_URL}/reset-password?token={reset_token}"
    body = (
        "A password reset was requested for your Shuppa Operations account.\n\n"
        f"Reset your password here (this link expires in 30 minutes):\n{reset_link}\n\n"
        "If you didn't request this, you can safely ignore this email - your "
        "password won't change unless you use the link above."
    )
    return send_email(to_email, "Reset your Shuppa Operations password", body)
