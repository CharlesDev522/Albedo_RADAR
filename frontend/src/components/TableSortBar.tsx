"use client";

import { dashboardColumnDir, sortLabel, toggleDashboardSort, type DashboardSortKey, type SortColumn } from "@/lib/dashboardSort";

const SORT_COLUMNS: { column: SortColumn; label: string }[] = [
  { column: "uid", label: "uid" },
  { column: "commit", label: "commit" },
  { column: "reg", label: "reg" },
  { column: "coldkey", label: "coldkey" },
];

export default function TableSortBar({
  sort,
  onSort,
  showStatus = false,
}: {
  sort: DashboardSortKey;
  onSort: (next: DashboardSortKey) => void;
  showStatus?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3 py-2 border-t border-zinc-800/80 text-[10px]">
      <span className="text-zinc-600 mr-0.5">sort</span>
      {SORT_COLUMNS.map(({ column, label }) => {
        const dir = dashboardColumnDir(sort, column);
        return (
          <button
            key={column}
            type="button"
            onClick={() => onSort(toggleDashboardSort(sort, column))}
            className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full border transition-colors ${
              dir
                ? "border-zinc-500 text-zinc-200 bg-zinc-800/60"
                : "border-zinc-800 text-zinc-600 hover:border-zinc-700 hover:text-zinc-400"
            }`}
          >
            {label}
            <span className="mono text-[9px] opacity-80">{dir === "asc" ? "↑" : dir === "desc" ? "↓" : "↕"}</span>
          </button>
        );
      })}
      {showStatus && (
        <button
          type="button"
          onClick={() => onSort(toggleDashboardSort(sort, "status"))}
          className={`inline-flex items-center gap-0.5 px-2 py-0.5 rounded-full border transition-colors ${
            dashboardColumnDir(sort, "status")
              ? "border-zinc-500 text-zinc-200 bg-zinc-800/60"
              : "border-zinc-800 text-zinc-600 hover:border-zinc-700 hover:text-zinc-400"
          }`}
        >
          committed
          <span className="mono text-[9px] opacity-80">
            {sort === "committed_first" ? "✓" : sort === "uncommitted_first" ? "✗" : "↕"}
          </span>
        </button>
      )}
      <span className="text-zinc-600 ml-auto mono">{sortLabel(sort)}</span>
    </div>
  );
}
