import { ReactNode } from "react";
import GlobalSearch from "./GlobalSearch";

export default function TopBar({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="topbar">
      <h1 className="page-title">{title}</h1>
      <div className="topbar-filters">
        {children}
        <GlobalSearch />
      </div>
    </div>
  );
}
