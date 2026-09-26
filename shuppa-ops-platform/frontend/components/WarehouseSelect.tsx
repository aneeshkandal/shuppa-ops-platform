"use client";

import { useEffect } from "react";
import { WAREHOUSES } from "../lib/api";
import { useAuth } from "../lib/auth";
import CustomDropdown from "./CustomDropdown";

export default function WarehouseSelect({
  value,
  onChange,
}: {
  value: number | undefined;
  onChange: (warehouseId: number | undefined) => void;
}) {
  const { user } = useAuth();

  // WAREHOUSE-role users are locked to their own warehouse - the backend
  // enforces this regardless of what's requested, but the UI shouldn't even
  // offer the choice. Lock the value in as soon as we know who's logged in.
  useEffect(() => {
    if (user?.role === "WAREHOUSE" && value !== user.warehouse_id) {
      onChange(user.warehouse_id ?? undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (user?.role === "WAREHOUSE") {
    return <span className="select-pill">{user.warehouse_name}</span>;
  }

  return (
    <CustomDropdown
      variant="pill"
      ariaLabel="Warehouse"
      value={value ?? ""}
      onChange={(v) => onChange(v ? Number(v) : undefined)}
      options={WAREHOUSES.map((w) => ({ value: w.id ?? "", label: w.name }))}
    />
  );
}
