"use client";

import { useState } from "react";
import AppLayout from "../../../components/AppLayout";
import AdminGuard from "../../../components/AdminGuard";
import TopBar from "../../../components/TopBar";
import DataTable from "../../../components/DataTable";
import Icon from "../../../components/Icon";
import { ErrorState, LoadingState } from "../../../components/LoadingState";
import { WAREHOUSES, adminApi } from "../../../lib/api";
import { useApi } from "../../../lib/useApi";
import CustomDropdown from "../../../components/CustomDropdown";

export default function AdminUsersPage() {
  const users = useApi(() => adminApi.listUsers(), []);

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"ADMIN" | "WAREHOUSE">("WAREHOUSE");
  const [warehouseId, setWarehouseId] = useState<number | "">("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const [resetTarget, setResetTarget] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const [rowBusy, setRowBusy] = useState<number | null>(null);

  const submit = async () => {
    setSaving(true);
    setError(null);
    setOk(false);
    try {
      await adminApi.addUser({
        username,
        password,
        role,
        warehouse_id: role === "WAREHOUSE" && warehouseId !== "" ? Number(warehouseId) : undefined,
        email: email || undefined,
      });
      setUsername("");
      setEmail("");
      setPassword("");
      setWarehouseId("");
      setOk(true);
      users.reload();
    } catch (e: any) {
      setError(e?.message || "Could not add user.");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (userId: number, isActive: boolean) => {
    setRowBusy(userId);
    try {
      await adminApi.updateUser(userId, { is_active: !isActive });
      users.reload();
    } catch (e: any) {
      setError(e?.message || "Could not update user.");
    } finally {
      setRowBusy(null);
    }
  };

  const approveUser = async (userId: number) => {
    setRowBusy(userId);
    try {
      await adminApi.updateUser(userId, { is_active: true });
      users.reload();
    } catch (e: any) {
      setError(e?.message || "Could not approve user.");
    } finally {
      setRowBusy(null);
    }
  };

  const submitReset = async (userId: number) => {
    if (!resetPassword) return;
    setRowBusy(userId);
    try {
      await adminApi.updateUser(userId, { password: resetPassword });
      setResetTarget(null);
      setResetPassword("");
      users.reload();
    } catch (e: any) {
      setError(e?.message || "Could not reset password.");
    } finally {
      setRowBusy(null);
    }
  };

  const warehouseName = (id: number | null) => WAREHOUSES.find((w) => w.id === id)?.name || (id ? `#${id}` : "All warehouses");

  return (
    <AppLayout>
      <AdminGuard>
        <TopBar title="Admin – Manage Users" />
        <div className="content-area">
          <div className="card admin-form-card">
            <div className="chart-card-header">
              <h3>Add User</h3>
            </div>
            <div className="form-grid">
              <div className="form-field">
                <label>Username</label>
                <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. swords" />
              </div>
              <div className="form-field">
                <label>Email (optional)</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="needed for password-reset emails"
                />
              </div>
              <div className="form-field">
                <label>Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="min. 10 characters" />
              </div>
              <div className="form-field">
                <label>Role</label>
                <CustomDropdown
                  value={role}
                  onChange={(v) => setRole(v as "ADMIN" | "WAREHOUSE")}
                  options={[
                    { value: "WAREHOUSE", label: "Warehouse" },
                    { value: "ADMIN", label: "Admin" },
                  ]}
                />
              </div>
              {role === "WAREHOUSE" && (
                <div className="form-field">
                  <label>Warehouse</label>
                  <CustomDropdown
                    placeholder="Select a warehouse..."
                    value={warehouseId}
                    onChange={(v) => setWarehouseId(v ? Number(v) : "")}
                    options={WAREHOUSES.filter((w) => w.id).map((w) => ({ value: w.id!, label: w.name }))}
                  />
                </div>
              )}
              <button
                className="btn-primary"
                onClick={submit}
                disabled={saving || !username || password.length < 10 || (role === "WAREHOUSE" && !warehouseId)}
              >
                {saving ? "Adding..." : "Add User"}
              </button>
            </div>
            {error && <p className="empty-state" style={{ color: "var(--status-critical)" }}>{error}</p>}
            {ok && <p className="empty-state" style={{ color: "var(--status-good)" }}>User added.</p>}
          </div>

          <div className="card admin-table-wrap">
            <div className="chart-card-header">
              <h3>Existing Users</h3>
            </div>
            {users.loading && <LoadingState />}
            {users.error && <ErrorState message={users.error} onRetry={users.reload} />}
            {users.data && (
              <DataTable
                keyField="user_id"
                rows={users.data}
                columns={[
                  { key: "user_id", header: "ID" },
                  { key: "username", header: "Username" },
                  {
                    key: "email",
                    header: "Email",
                    render: (r) => r.email || <span style={{ color: "var(--text-muted)" }}>—</span>,
                  },
                  { key: "role", header: "Role" },
                  { key: "warehouse_id", header: "Warehouse", render: (r) => warehouseName(r.warehouse_id) },
                  {
                    key: "is_active",
                    header: "Status",
                    render: (r) =>
                      r.pending_approval ? (
                        <span style={{ color: "var(--status-warning)", fontWeight: 700 }}>Pending Approval</span>
                      ) : (
                        <span style={{ color: r.is_active ? "var(--status-good)" : "var(--status-critical)", fontWeight: 700 }}>
                          {r.is_active ? "Active" : "Deactivated"}
                        </span>
                      ),
                  },
                  {
                    key: "must_change_password",
                    header: "Password",
                    render: (r) =>
                      r.must_change_password ? (
                        <span style={{ color: "var(--status-warning)" }}>Must change on next login</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      ),
                  },
                  {
                    key: "is_locked",
                    header: "Lockout",
                    render: (r) =>
                      r.is_locked ? (
                        <span style={{ color: "var(--status-critical)", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 4 }}>
                          <Icon name="lock" size={13} /> Locked{r.failed_login_count ? ` (${r.failed_login_count} failed)` : ""}
                        </span>
                      ) : r.failed_login_count ? (
                        <span style={{ color: "var(--status-warning)" }}>{r.failed_login_count} recent failed attempt(s)</span>
                      ) : (
                        <span style={{ color: "var(--text-muted)" }}>—</span>
                      ),
                  },
                  {
                    key: "last_login_at",
                    header: "Last Login",
                    render: (r) => (r.last_login_at ? new Date(r.last_login_at).toLocaleString() : "Never"),
                  },
                  {
                    key: "actions",
                    header: "Actions",
                    sortable: false,
                    render: (r) => (
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {r.pending_approval ? (
                          <button
                            className="btn-primary btn-small"
                            disabled={rowBusy === r.user_id}
                            onClick={() => approveUser(r.user_id)}
                            type="button"
                          >
                            Approve
                          </button>
                        ) : (
                          <button
                            className="btn-secondary btn-small"
                            disabled={rowBusy === r.user_id}
                            onClick={() => toggleActive(r.user_id, r.is_active)}
                            type="button"
                          >
                            {r.is_active ? "Deactivate" : "Reactivate"}
                          </button>
                        )}
                        {resetTarget === r.user_id ? (
                          <>
                            <input
                              type="password"
                              placeholder="min. 10 characters"
                              value={resetPassword}
                              onChange={(e) => setResetPassword(e.target.value)}
                              style={{ width: 140 }}
                            />
                            <button
                              className="btn-secondary btn-small"
                              disabled={rowBusy === r.user_id || resetPassword.length < 10}
                              onClick={() => submitReset(r.user_id)}
                              type="button"
                            >
                              Save
                            </button>
                            <button
                              className="btn-secondary btn-small"
                              onClick={() => {
                                setResetTarget(null);
                                setResetPassword("");
                              }}
                              type="button"
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button className="btn-secondary btn-small" onClick={() => setResetTarget(r.user_id)} type="button">
                            Reset Password
                          </button>
                        )}
                      </div>
                    ),
                  },
                ]}
              />
            )}
          </div>
        </div>
      </AdminGuard>
    </AppLayout>
  );
}
