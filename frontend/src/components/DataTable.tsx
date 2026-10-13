// DataTable — analytical table for query results, previews and ML outputs.
// Values are formatted for display only; missing values show as "—".

import { useMemo, useState } from "react";
import { formatValue, humanize, isNumeric, kindOf, plural, type ValueKind } from "../lib/format";

interface Props {
  columns: string[];
  rows: unknown[][];
  /** Rows shown before "Show all". */
  initialRows?: number;
  /** Server reported it stopped at its row cap. */
  truncated?: boolean;
  emptyMessage?: string;
  /** Constrain height and scroll inside (sticky header). */
  maxHeightClass?: string;
}

export function DataTable({
  columns,
  rows,
  initialRows = 50,
  truncated = false,
  emptyMessage = "No matching records.",
  maxHeightClass = "max-h-[420px]",
}: Props) {
  const [expanded, setExpanded] = useState(false);

  const kinds = useMemo<ValueKind[]>(
    () => columns.map((c, i) => kindOf(c, rows.find((r) => r[i] !== null && r[i] !== undefined)?.[i])),
    [columns, rows],
  );

  if (rows.length === 0) {
    return <p className="px-4 py-6 text-center text-sm text-ink-muted">{emptyMessage}</p>;
  }

  const visible = expanded ? rows : rows.slice(0, initialRows);
  const alignRight = (i: number) => kinds[i] !== "text" && kinds[i] !== "date";

  return (
    <div>
      <div className={`overflow-auto ${maxHeightClass}`}>
        <table className="min-w-full border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              {columns.map((c, i) => (
                <th
                  key={c}
                  scope="col"
                  className={`sticky top-0 z-10 whitespace-nowrap border-b border-line bg-surface-sunken px-4 py-2.5 text-xs font-semibold text-ink-secondary ${
                    alignRight(i) ? "text-right" : "text-left"
                  }`}
                >
                  {humanize(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, r) => (
              <tr key={r} className="hover:bg-surface-sunken/60">
                {columns.map((c, i) => (
                  <td
                    key={c}
                    className={`whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-ink ${
                      alignRight(i) ? "text-right tabular-nums" : "text-left"
                    } ${isNumeric(row[i]) ? "tabular-nums" : ""}`}
                  >
                    {formatValue(row[i], kinds[i])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {(rows.length > initialRows || truncated) && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-xs text-ink-muted">
          <span>
            {rows.length > initialRows && !expanded
              ? `Showing ${plural(initialRows, "row")} of ${rows.length.toLocaleString("en-IN")}`
              : plural(rows.length, "row")}
            {truncated && " · the server limited this result; refine the question to narrow it"}
          </span>
          {rows.length > initialRows && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="focus-ring rounded font-medium text-primary hover:text-primary-hover"
            >
              {expanded ? "Show fewer" : "Show all rows"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/** Convert Recharts-style records into columns/rows for DataTable. */
export function recordsToTable(records: Record<string, unknown>[]): { columns: string[]; rows: unknown[][] } {
  const columns = records.length ? Object.keys(records[0]).filter((k) => !k.startsWith("__")) : [];
  return { columns, rows: records.map((r) => columns.map((c) => r[c])) };
}
