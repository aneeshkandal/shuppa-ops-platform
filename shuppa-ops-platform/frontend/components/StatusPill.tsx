import { resolutionColor, riskLevelColor, stockStatusColor } from "../lib/theme";
import Icon, { IconName } from "./Icon";

const ICONS: Record<string, IconName> = {
  HEALTHY: "checkCircle",
  LOW: "alertTriangle",
  CRITICAL: "alertOctagon",
  OVERSTOCK: "alertTriangle",
  HIGH: "alertOctagon",
  MEDIUM: "alertTriangle",
  PENDING: "clock",
  RETURNED: "checkCircle",
  RESOLVED: "checkCircle",
  PO_GENERATED: "clipboardList",
  LISTED_AS_NEW_PRODUCT: "alertTriangle",
};

export default function StatusPill({ status }: { status: string }) {
  const key = (status || "").toUpperCase();
  const color = stockStatusColor[key] || riskLevelColor[key] || resolutionColor[key] || "#898781";
  const icon = ICONS[key];
  return (
    <span
      className="status-pill"
      style={{ color, borderColor: color, background: `${color}1a` }}
    >
      {icon && <Icon name={icon} size={12} strokeWidth={2.4} />}
      {status}
    </span>
  );
}
