"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { authApi } from "./api";

export type Role = "ADMIN" | "WAREHOUSE";

export interface AuthUser {
  user_id: number;
  username: string;
  role: Role;
  warehouse_id: number | null;
  warehouse_name: string | null;
  must_change_password: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  /** Re-fetches /auth/me - used by the change-password page after a
   * successful change, so must_change_password flips to false and the
   * mandatory-redirect effect above stops sending the user back there. */
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// Public pages that don't need (or, for /change-password, temporarily
// bypass) the normal "must be logged in" gate below.
const PUBLIC_PATHS = new Set(["/login", "/register", "/forgot-password", "/reset-password"]);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    // No token to check for anymore - the browser just sends whatever
    // httpOnly auth cookie it has (or doesn't) on this call, and a missing/
    // expired one comes back as a plain 401 (see lib/api.ts).
    authApi
      .me()
      .then((u) => setUser({ ...u, role: u.role as Role, must_change_password: !!u.must_change_password }))
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (loading) return;
    const isPublicPage = PUBLIC_PATHS.has(pathname);

    if (!user && !isPublicPage) {
      router.replace("/login");
      return;
    }
    if (user && isPublicPage && pathname !== "/reset-password") {
      router.replace("/overview");
      return;
    }
    // A forced password change blocks every other page until it's done -
    // mirrors the same rule the backend enforces in app/auth.py's
    // get_current_user, so this is a UX shortcut, not the real security
    // boundary.
    if (user?.must_change_password && pathname !== "/change-password") {
      router.replace("/change-password");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, loading, pathname]);

  const login = async (username: string, password: string) => {
    const res = await authApi.login(username, password);
    setUser({
      user_id: res.user.user_id,
      username: res.user.username,
      role: res.user.role as Role,
      warehouse_id: res.user.warehouse_id,
      warehouse_name: res.user.warehouse_name,
      must_change_password: !!res.user.must_change_password,
    });
    router.push(res.user.must_change_password ? "/change-password" : "/overview");
  };

  const logout = () => {
    authApi.logout().finally(() => {
      setUser(null);
      router.push("/login");
    });
  };

  const refreshUser = async () => {
    const u = await authApi.me();
    setUser({ ...u, role: u.role as Role, must_change_password: !!u.must_change_password });
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
