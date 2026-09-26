"use client";

import { useEffect, useState } from "react";
import Icon from "./Icon";
import { useApi } from "../lib/useApi";
import { ErrorState, LoadingState } from "./LoadingState";
import type { InsightsResponse } from "../lib/api";

/**
 * The "Key Business Insights" card: one of these per analytics page (Stock
 * Summary, Sales Analytics, Supplier Summary, Stock Optimizer, Delivery Risk
 * Predictor) rather than a single dashboard-wide card pooling every domain
 * together - the user explicitly compared both layouts against a mockup of
 * this page (see the project's build notes) and picked one card per page,
 * each scoped to that page's own relevant insight types.
 *
 * Renders a small tabs/pills row (the user's chosen filter style, matching
 * this app's existing pill-style filters elsewhere) and shows the selected
 * tab's insight text below it. Every insight this fetches is derived from
 * data that page's own KPIs/charts already show - see
 * backend/app/services/insights_service.py - so this card never introduces
 * a number that disagrees with the rest of the page.
 *
 * `fetcher` should be one of the `insightsApi.*` functions from lib/api.ts,
 * wrapped in a stable-ish closure the same way every other useApi() call on
 * these pages already does (e.g. `() => insightsApi.stock(warehouseId,
 * range)`); `deps` should list exactly the values that closure reads, so a
 * warehouse/date filter change refetches this card in lockstep with every
 * other panel on the page.
 */
export default function KeyInsightsCard({
  fetcher,
  deps,
}: {
  fetcher: () => Promise<InsightsResponse>;
  deps: any[];
}) {
  const result = useApi(fetcher, deps);
  const [activeKey, setActiveKey] = useState<string | null>(null);

  const insights = result.data?.insights || [];

  // A fresh fetch (a warehouse/date filter change, or "Suggest Again"-style
  // reload) can come back with a different set of keys entirely - reset to
  // the first tab whenever the currently-selected key isn't in the new list,
  // rather than silently showing nothing.
  useEffect(() => {
    if (insights.length > 0 && !insights.some((i) => i.key === activeKey)) {
      setActiveKey(insights[0].key);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result.data]);

  const active = insights.find((i) => i.key === activeKey) || insights[0];

  return (
    <div className="card">
      <div className="chart-card-header">
        <h3>Key Business Insights</h3>
      </div>
      {result.loading && <LoadingState />}
      {result.error && <ErrorState message={result.error} onRetry={result.reload} />}
      {!result.loading && !result.error && insights.length === 0 && (
        <p className="empty-state">No insights available right now.</p>
      )}
      {insights.length > 1 && (
        <div className="insight-tabs">
          {insights.map((i) => (
            <button
              key={i.key}
              type="button"
              className={`insight-tab${i.key === active?.key ? " active" : ""}`}
              onClick={() => setActiveKey(i.key)}
            >
              {i.label}
            </button>
          ))}
        </div>
      )}
      {active && (
        <div className="insight-body">
          <span className="icon-badge icon-badge-sm">
            <Icon name="lightbulb" size={15} />
          </span>
          <div className="insight-text">{active.text}</div>
        </div>
      )}
    </div>
  );
}
