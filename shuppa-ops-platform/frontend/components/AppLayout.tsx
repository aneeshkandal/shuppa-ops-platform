"use client";

import { ReactNode } from "react";
import Sidebar from "./Sidebar";
import { useAuth } from "../lib/auth";
import { LoadingState } from "./LoadingState";

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  // While the session is being resolved (or right before the auth redirect
  // to /login kicks in), don't flash protected content or fire API calls
  // that will just 401.
  if (loading || !user) {
    return (
      <div className="app-shell">
        <div className="main-column">
          <LoadingState label="Loading..." />
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-column">{children}</div>
    </div>
  );
}
