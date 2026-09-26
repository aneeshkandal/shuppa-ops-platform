"use client";

import { useEffect, useState } from "react";
import { formatRelativeTime } from "../lib/format";
import Icon from "./Icon";

/**
 * "Last updated Xs ago" + a manual refresh button, for pages backed by
 * useApi's polling refreshInterval (Alerts Center, sidebar badge, Executive
 * Overview). Re-renders itself every few seconds purely to keep the
 * relative-time text current - it doesn't refetch anything on its own.
 */
export default function LastUpdated({
  timestamp,
  onRefresh,
}: {
  timestamp: number | null;
  onRefresh?: () => void;
}) {
  const [, setNowTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setNowTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="last-updated">
      {timestamp && <span className="last-updated-text">Updated {formatRelativeTime(timestamp)}</span>}
      {onRefresh && (
        <button
          type="button"
          className="btn-secondary btn-small"
          onClick={onRefresh}
          aria-label="Refresh now"
          title="Refresh now"
        >
          <Icon name="refreshCw" size={12} strokeWidth={2.2} />
        </button>
      )}
    </span>
  );
}
