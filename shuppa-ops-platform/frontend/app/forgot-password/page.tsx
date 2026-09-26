"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { authApi, ApiError } from "../../lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await authApi.forgotPassword(email);
      // Always the same generic message whether or not the email matched an
      // account - see the backend's /auth/forgot-password docstring for why.
      setMessage(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-logo">
          <span className="sidebar-logo-badge">S</span>
          Shuppa
        </div>
        <div className="login-subtitle">Reset your password.</div>

        {message ? (
          <div className="login-success">{message}</div>
        ) : (
          <>
            {error && <div className="login-error">{error}</div>}
            <form className="form-grid" onSubmit={submit}>
              <div className="form-field">
                <label>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                  autoFocus
                />
              </div>
              <button className="btn-primary" type="submit" disabled={loading || !email}>
                {loading ? "Sending..." : "Send reset link"}
              </button>
            </form>
            <div className="login-hint">
              Only accounts with an email on file (set by you at registration, or added by an Admin in Manage
              Users) can be reset this way.
            </div>
          </>
        )}

        <div className="login-links">
          <Link href="/login">Back to sign in</Link>
          <span />
        </div>
      </div>
    </div>
  );
}
