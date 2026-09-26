"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError } from "../../lib/api";
import { authApi } from "../../lib/api";
import { useAuth } from "../../lib/auth";

export default function ChangePasswordPage() {
  const { user, refreshUser } = useAuth();
  const router = useRouter();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      await refreshUser();
      router.push("/overview");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change your password.");
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
        <div className="login-subtitle">
          {user?.must_change_password
            ? "You need to set a new password before continuing."
            : "Change your password."}
        </div>

        {error && <div className="login-error">{error}</div>}
        <form className="form-grid" onSubmit={submit}>
          <div className="form-field">
            <label>Current password</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              required
              autoFocus
            />
          </div>
          <div className="form-field">
            <label>New password</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoComplete="new-password"
              minLength={10}
              required
            />
          </div>
          <button className="btn-primary" type="submit" disabled={loading || !currentPassword || newPassword.length < 10}>
            {loading ? "Changing..." : "Change password"}
          </button>
        </form>
        <div className="login-hint">
          {user?.must_change_password
            ? "This account was created with a password someone else chose - you need to pick your own before you can use the rest of the app."
            : "At least 10 characters."}
        </div>
      </div>
    </div>
  );
}
