"use client";

import { ReactNode, useMemo, useState } from "react";
import Icon from "./Icon";

export type Column<T> = {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  align?: "left" | "right" | "center";
  sortable?: boolean;
};

type SortState = { key: string; direction: "asc" | "desc" } | null;

function compareValues(a: any, b: any): number {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  const an = typeof a === "number" ? a : Number(a);
  const bn = typeof b === "number" ? b : Number(b);
  if (!Number.isNaN(an) && !Number.isNaN(bn) && a !== "" && b !== "") {
    return an - bn;
  }
  return String(a).localeCompare(String(b));
}

function toCsvValue(v: any): string {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv<T extends Record<string, any>>(filename: string, columns: Column<T>[], rows: T[]) {
  const header = columns.map((c) => toCsvValue(c.header)).join(",");
  const lines = rows.map((row) => columns.map((c) => toCsvValue(row[c.key])).join(","));
  const csv = [header, ...lines].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function DataTable<T extends Record<string, any>>({
  columns,
  rows,
  emptyMessage = "No data yet.",
  keyField,
  pageSize,
  csvFilename,
  onRowClick,
  activeRowKey,
}: {
  columns: Column<T>[];
  rows: T[];
  emptyMessage?: string;
  keyField: string;
  /** When set, paginates client-side at this many rows per page. Omit to show every row (existing behavior). */
  pageSize?: number;
  /** When set, shows an "Export CSV" button that downloads the (sorted, unpaginated) rows under this filename. */
  csvFilename?: string;
  /** Optional row click handler - used for drill-down interactions (e.g. click a supplier to filter another table). */
  onRowClick?: (row: T) => void;
  /** Row keyField value to visually highlight as "selected" (pairs with onRowClick drill-down). */
  activeRowKey?: string | number;
}) {
  const [sort, setSort] = useState<SortState>(null);
  const [page, setPage] = useState(0);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const cmp = compareValues(a[sort.key], b[sort.key]);
      return sort.direction === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort]);

  const pageCount = pageSize ? Math.max(1, Math.ceil(sortedRows.length / pageSize)) : 1;
  const currentPage = Math.min(page, pageCount - 1);
  const visibleRows = pageSize
    ? sortedRows.slice(currentPage * pageSize, currentPage * pageSize + pageSize)
    : sortedRows;

  const toggleSort = (col: Column<T>) => {
    if (col.sortable === false) return;
    setPage(0);
    setSort((s) => {
      if (!s || s.key !== col.key) return { key: col.key, direction: "asc" };
      if (s.direction === "asc") return { key: col.key, direction: "desc" };
      return null;
    });
  };

  if (!rows || rows.length === 0) {
    return <p className="empty-state">{emptyMessage}</p>;
  }

  return (
    <div>
      {csvFilename && (
        <div className="table-toolbar">
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={() => downloadCsv(csvFilename, columns, sortedRows)}
          >
            <Icon name="download" size={13} /> Export CSV
          </button>
        </div>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((c) => {
                const sortable = c.sortable !== false;
                const isSorted = sort?.key === c.key;
                const ariaSort: "ascending" | "descending" | "none" = !sortable
                  ? "none"
                  : isSorted
                  ? sort!.direction === "asc"
                    ? "ascending"
                    : "descending"
                  : "none";
                return (
                  <th
                    key={c.key}
                    style={{ textAlign: c.align || "left", cursor: sortable ? "pointer" : undefined }}
                    onClick={() => toggleSort(c)}
                    onKeyDown={
                      sortable
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              toggleSort(c);
                            }
                          }
                        : undefined
                    }
                    tabIndex={sortable ? 0 : undefined}
                    aria-sort={sortable ? ariaSort : undefined}
                    title={sortable ? "Click to sort" : undefined}
                  >
                    {c.header}
                    {sortable && isSorted && (
                      <span className="sort-indicator" aria-hidden>
                        <Icon name={sort!.direction === "asc" ? "chevronUp" : "chevronDown"} size={12} strokeWidth={2.4} />
                      </span>
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr
                key={row[keyField]}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? "row-clickable" : undefined}
                style={
                  activeRowKey !== undefined && row[keyField] === activeRowKey
                    ? { background: "rgba(139, 92, 246, 0.1)" }
                    : undefined
                }
              >
                {columns.map((c) => (
                  <td key={c.key} style={{ textAlign: c.align || "left" }}>
                    {c.render ? c.render(row) : row[c.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageSize && pageCount > 1 && (
        <div className="table-pagination">
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={currentPage === 0}
          >
            <Icon name="chevronLeft" size={13} /> Prev
          </button>
          <span className="table-pagination-label">
            Page {currentPage + 1} of {pageCount}
          </span>
          <button
            type="button"
            className="btn-secondary btn-small"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={currentPage >= pageCount - 1}
          >
            Next <Icon name="chevronRight" size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
