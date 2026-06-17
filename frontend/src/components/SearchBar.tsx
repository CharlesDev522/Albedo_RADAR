"use client";

import { isSearchActive } from "@/lib/searchFilter";

export default function SearchBar({
  value,
  onChange,
  placeholder = "Search uid, hotkey, coldkey, repo…",
  resultCount,
  totalCount,
  className = "",
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  resultCount?: number;
  totalCount?: number;
  className?: string;
}) {
  const active = isSearchActive(value);

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="relative flex-1 min-w-[140px] max-w-md">
        <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600 text-[11px]">
          ⌕
        </span>
        <input
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          aria-label="Search"
          className="w-full pl-6 pr-7 py-1 rounded-md border border-zinc-800 bg-zinc-950/80 text-[11px] text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-zinc-600 focus:ring-1 focus:ring-zinc-700"
        />
        {active && (
          <button
            type="button"
            onClick={() => onChange("")}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 px-1 text-[10px] text-zinc-500 hover:text-zinc-300"
            aria-label="Clear search"
          >
            ×
          </button>
        )}
      </div>
      {active && resultCount != null && totalCount != null && (
        <span className="text-[9px] text-zinc-600 mono shrink-0 tabular-nums">
          {resultCount}/{totalCount}
        </span>
      )}
    </div>
  );
}
