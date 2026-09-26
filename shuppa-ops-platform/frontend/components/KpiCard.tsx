import type { CSSProperties, ReactNode } from "react";
import Icon, { IconName } from "./Icon";

type Props = {
  icon?: IconName;
  label: string;
  /** Usually a plain string, but any node is fine (e.g. a "before -> after" comparison with an inline icon). */
  value: ReactNode;
  delta?: string;
  deltaGood?: boolean;
  /** A CSS color (hex/rgb/CSS variable) used to tint the icon badge and the card's top accent bar. */
  accent?: string;
};

export default function KpiCard({ icon, label, value, delta, deltaGood, accent }: Props) {
  const style = accent ? ({ "--kpi-accent": accent } as CSSProperties) : undefined;
  return (
    <div className="kpi-card" style={style}>
      <div className="kpi-label">
        {icon && (
          <span
            className="icon-badge icon-badge-sm"
            style={accent ? { color: accent, background: `${accent}1f` } : undefined}
          >
            <Icon name={icon} size={14} strokeWidth={2} />
          </span>
        )}
        {label}
      </div>
      <div className="kpi-value-row">
        <span className="kpi-value">{value}</span>
        {delta && (
          <span className={`kpi-delta ${deltaGood ? "kpi-delta-good" : "kpi-delta-bad"}`}>{delta}</span>
        )}
      </div>
    </div>
  );
}
