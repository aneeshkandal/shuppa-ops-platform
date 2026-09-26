"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { authApi, ApiError } from "../../lib/api";
import { useApi } from "../../lib/useApi";
import CustomDropdown from "../../components/CustomDropdown";

export default function RegisterPage() {
  const warehouses = useApi(() => authApi.warehousesPublic(), []);
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [warehouseId, setWarehouseId] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await authApi.register({ username, email, password, warehouse_id: Number(warehouseId) });
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit registration.");
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
        <div className="login-subtitle">Request a warehouse account.</div>

        {submitted ? (
          <>
            <div className="login-success">
              Registration submitted. An Admin needs to approve your account from Manage Users before you can log
              in - you'll be able to sign in with the password you just chose once that happens.
            </div>
            <div className="login-links">
              <Link href="/login">Back to sign in</Link>
              <span />
            </div>
          </>
        ) : (
          <>
            {error && <div className="login-error">{error}</div>}
            <form className="form-grid" onSubmit={submit}>
              <div className="form-field">
                <label>Username</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  minLength={3}
                  maxLength={50}
                  required
                  autoFocus
                />
              </div>
              <div className="form-field">
                <label>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>
              <div className="form-field">
                <label>Password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={10}
                  required
                />
              </div>
              <div className="form-field">
                <label>Warehouse</label>
                <CustomDropdown
                  placeholder={warehouses.loading ? "Loading..." : "Select a warehouse"}
                  value={warehouseId}
                  onChange={setWarehouseId}
                  options={(warehouses.data || []).map((w) => ({ value: w.warehouse_id, label: w.warehouse_name }))}
                />
              </div>
              <button className="btn-primary" type="submit" disabled={loading || !username || !email || !password || !warehouseId}>
                {loading ? "Submitting..." : "Request account"}
              </button>
            </form>
            <div className="login-links">
              <Link href="/login">Back to sign in</Link>
              <span />
            </div>
            <div className="login-hint">
              New accounts are always created as a single-warehouse account pending Admin approval - only an
              existing Admin can grant Admin access.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
