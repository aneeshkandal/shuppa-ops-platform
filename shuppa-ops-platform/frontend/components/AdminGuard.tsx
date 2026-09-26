"use client";

import { ReactNode } from "react";
import { useAuth } from "../lib/auth";

export default function AdminGuard({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && user.role !== "ADMIN") {
    return (
      <div className="content-area">
        <div className="card">
          <p className="empty-state">This page is for Admin accounts only.</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
