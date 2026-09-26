"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { authApi, ApiError } from "../../lib/api";

export default function ResetPasswordPage() {
  // Read directly from window.location (rather than next/navigation's
  // useSearchParams) so this page doesn't need a Suspense boundary just for
  // a query param - same pattern already used by the Supplier Summary
  // page's "jump from search" deep link.
  const [token] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("token") || "";
  });
  const [newPassword, setNewPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await authApi.resetPassword(token, newPassword);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset your password.");
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
        <div className="login-subtitle">Choose a new password.</div>

        {!token ? (
          <div className="login-error">
            This link is missing its reset token. Request a new one from the forgot-password page.
          </div>
        ) : done ? (
          <div className="login-success">Your password has been reset. You can now sign in with it.</div>
        ) : (
          <>
            {error && <div className="login-error">{error}</div>}
            <form className="form-grid" onSubmit={submit}>
              <div className="form-field">
                <label>New password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                  autoFocus
                />
              </div>
              <button className="btn-primary" type="submit" disabled={loading || newPassword.length < 10}>
                {loading ? "Resetting..." : "Reset password"}
              </button>
            </form>
            <div className="login-hint">This link expires 30 minutes after it was requested and works once.</div>
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
