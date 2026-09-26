import { ReactNode } from "react";

export default function ChartCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="card chart-card">
      <div className="chart-card-header">
        <h3>{title}</h3>
        {action}
      </div>
      <div className="chart-card-body">{children}</div>
    </div>
  );
}
