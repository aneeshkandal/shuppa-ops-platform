/**
 * Shimmering placeholder blocks shown in place of a chart/table/KPI card
 * while its data is loading, instead of the bare "Loading..." text
 * (LoadingState) - reduces layout jump and gives a sense of shape before
 * the real content arrives. Purely presentational; sizes are passed in per
 * use-site rather than guessed from context.
 */
export function Skeleton({ height = 16, width = "100%" }: { height?: number | string; width?: number | string }) {
  return <div className="skeleton-block" style={{ height, width }} />;
}

/** A handful of stacked skeleton rows, sized like a KPI/chart card's body. */
export function SkeletonRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="skeleton-rows">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} height={14} width={i === rows - 1 ? "60%" : "100%"} />
      ))}
    </div>
  );
}

/** Sized to roughly match a chart card's plot area. */
export function SkeletonChart() {
  return <div className="skeleton-block skeleton-chart" />;
}

/** Sized to roughly match a KpiCard. */
export function SkeletonKpiRow({ count = 4 }: { count?: number }) {
  return (
    <div className="kpi-row">
      {Array.from({ length: count }).map((_, i) => (
        <div className="kpi-card" key={i}>
          <Skeleton height={11} width="55%" />
          <div style={{ marginTop: 14 }}>
            <Skeleton height={26} width="75%" />
          </div>
        </div>
      ))}
    </div>
  );
}
