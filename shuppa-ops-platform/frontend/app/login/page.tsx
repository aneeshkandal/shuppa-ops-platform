"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useAuth } from "../../lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err: any) {
      setError(err?.message || "Could not log in.");
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
        <div className="login-subtitle">{"Warehouse operations dashboard – sign in to continue."}</div>

        {error && <div className="login-error">{error}</div>}

        <form className="form-grid" onSubmit={submit}>
          <div className="form-field">
            <label>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
            />
          </div>
          <div className="form-field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <button className="btn-primary" type="submit" disabled={loading || !username || !password}>
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="login-links">
          <Link href="/forgot-password">Forgot password?</Link>
          <Link href="/register">Request an account</Link>
        </div>

        <div className="login-hint">
          {
            "Admin sees every warehouse. A warehouse account (Lombard / Kimmage / Finglas) only sees and manages its own warehouse’s data."
          }
        </div>
      </div>
    </div>
  );
}
