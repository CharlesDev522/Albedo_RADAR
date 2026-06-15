"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  DEFAULT_SUBNET,
  hippiusModelUrl,
  shortAddr,
  shortRepo,
  type SlotStatusData,
  type SlotStatusEntry,
  type SlotStatusSummary,
} from "@/lib/api";

const POLL_MS = 5000;

type FilterKey =
  | "all"
  | "v5"
  | "timelock_encrypted"
  | "v4"
  | "json"
  | "other"
  | "unknown"
  | "none"
  | "committed";

const FILTERS: { key: FilterKey; label: string; color: string }[] = [
  { key: "all", label: "all slots", color: "text-zinc-300 border-zinc-600" },
  { key: "v5", label: "v5", color: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10" },
  { key: "timelock_encrypted", label: "encrypted", color: "text-violet-300 border-violet-500/40 bg-violet-500/10" },
  { key: "v4", label: "v4", color: "text-sky-300 border-sky-500/40 bg-sky-500/10" },
  { key: "json", label: "json", color: "text-amber-300 border-amber-500/40 bg-amber-500/10" },
  { key: "other", label: "other", color: "text-orange-300 border-orange-500/40 bg-orange-500/10" },
  { key: "none", label: "no commit", color: "text-zinc-500 border-zinc-700 bg-zinc-800/30" },
  { key: "committed", label: "any commit", color: "text-zinc-300 border-zinc-600" },
];

const TYPE_STYLES: Record<string, string> = {
  v5: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  timelock_encrypted: "text-violet-300 border-violet-500/30 bg-violet-500/10",
  v4: "text-sky-300 border-sky-500/30 bg-sky-500/10",
  json: "text-amber-300 border-amber-500/30 bg-amber-500/10",
  other: "text-orange-300 border-orange-500/30 bg-orange-500/10",
  unknown: "text-rose-300 border-rose-500/30 bg-rose-500/10",
  none: "text-zinc-500 border-zinc-700 bg-zinc-800/20",
};

const GRID_COLORS: Record<string, string> = {
  v5: "bg-emerald-500",
  timelock_encrypted: "bg-violet-500",
  v4: "bg-sky-500",
  json: "bg-amber-500",
  other: "bg-orange-500",
  unknown: "bg-rose-500",
  none: "bg-zinc-700",
};

function filterSlots(slots: SlotStatusEntry[], filter: FilterKey): SlotStatusEntry[] {
  if (filter === "all") return slots;
  if (filter === "committed") return slots.filter((s) => s.commitment_type !== "none");
  return slots.filter((s) => s.commitment_type === filter);
}

export default function SlotStatusBoard() {
  const subnet = DEFAULT_SUBNET;
  const [filter, setFilter] = useState<FilterKey>("all");
  const [data, setData] = useState<SlotStatusData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"grid" | "table">("grid");

  const refresh = useCallback(async () => {
    try {
      const res = await api.getSlotStatus(subnet, "all");
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load slots");
    }
  }, [subnet]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const summary = data?.summary;
  const allSlots = data?.slots ?? [];
  const displaySlots = useMemo(() => filterSlots(allSlots, filter), [allSlots, filter]);

  const countFor = (key: FilterKey, s: SlotStatusSummary | undefined) => {
    if (!s) return "—";
    if (key === "all") return String(s.total_slots);
    if (key === "committed") return String(s.total_slots - s.none);
    if (key === "timelock_encrypted") return String(s.timelock_encrypted);
    return String(s[key as keyof SlotStatusSummary] ?? 0);
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">miner slots · SN{subnet}</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            every UID 0–255 — v5, encrypted, v4, json, other, or no commit
          </p>
        </div>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setView("grid")}
            className={`px-2 py-0.5 text-[10px] rounded border ${view === "grid" ? "border-zinc-500 text-zinc-200" : "border-zinc-800 text-zinc-600"}`}
          >
            grid
          </button>
          <button
            type="button"
            onClick={() => setView("table")}
            className={`px-2 py-0.5 text-[10px] rounded border ${view === "table" ? "border-zinc-500 text-zinc-200" : "border-zinc-800 text-zinc-600"}`}
          >
            table
          </button>
        </div>
      </div>

      {error && (
        <div className="px-3 py-2 border-b border-rose-500/20 bg-rose-500/5 text-[10px] text-rose-300">{error}</div>
      )}

      <div className="flex flex-wrap gap-1.5 px-3 py-2 border-b border-zinc-800/80">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] transition-colors ${
              filter === f.key ? f.color : "text-zinc-600 border-zinc-800 hover:border-zinc-700"
            }`}
          >
            {f.label}
            <span className="mono opacity-70">{countFor(f.key, summary)}</span>
          </button>
        ))}
      </div>

      {view === "grid" && allSlots.length > 0 && (
        <div className="px-3 py-3 border-b border-zinc-800/80">
          <div
            className="grid gap-0.5"
            style={{ gridTemplateColumns: "repeat(16, minmax(0, 1fr))" }}
            title="256 UID slots — color = commitment type"
          >
            {allSlots.map((s) => (
              <div
                key={s.uid}
                title={`uid ${s.uid} · ${s.commitment_type}${s.detail ? ` · ${s.detail}` : ""}`}
                className={`aspect-square rounded-sm ${GRID_COLORS[s.commitment_type] ?? "bg-zinc-700"} ${
                  filter !== "all" && !filterSlots([s], filter).length ? "opacity-20" : "opacity-90"
                } hover:opacity-100 hover:ring-1 hover:ring-white/30 cursor-default`}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-3 mt-2 text-[9px] text-zinc-500">
            {Object.entries(GRID_COLORS).map(([k, c]) => (
              <span key={k} className="inline-flex items-center gap-1">
                <span className={`w-2 h-2 rounded-sm ${c}`} />
                {k === "timelock_encrypted" ? "encrypted" : k}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
        <table className="tbl">
          <thead className="sticky top-0 z-10">
            <tr>
              <th>uid</th>
              <th>type</th>
              <th>hotkey</th>
              <th>commit blk</th>
              <th>reveal rnd</th>
              <th>detail</th>
            </tr>
          </thead>
          <tbody>
            {displaySlots.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center text-zinc-500 py-8 text-[10px]">
                  {data ? "no slots match filter" : "loading slots…"}
                </td>
              </tr>
            ) : (
              displaySlots.map((s) => (
                <tr key={s.uid} className={s.commitment_type === "none" ? "opacity-40" : ""}>
                  <td className="mono font-medium text-zinc-200">{s.uid}</td>
                  <td>
                    <TypeBadge type={s.commitment_type} />
                  </td>
                  <td className="mono text-zinc-400" title={s.hotkey}>
                    {shortAddr(s.hotkey, 5)}
                  </td>
                  <td className="mono text-zinc-500 tabular-nums">
                    {s.commit_block?.toLocaleString() ?? "—"}
                  </td>
                  <td className="mono text-zinc-500 tabular-nums">
                    {s.reveal_round?.toLocaleString() ?? "—"}
                  </td>
                  <td className="text-[10px] text-zinc-500 max-w-[200px] truncate">
                    {s.commitment_type === "v5" && s.detail ? (
                      <a
                        href={hippiusModelUrl(s.detail)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-400/80 hover:underline"
                      >
                        {shortRepo(s.detail, 32)}
                      </a>
                    ) : (
                      s.detail ?? "—"
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function TypeBadge({ type }: { type: string }) {
  const label =
    type === "timelock_encrypted" ? "encrypted" : type === "none" ? "—" : type;
  return (
    <span
      className={`inline-flex px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wide ${
        TYPE_STYLES[type] ?? TYPE_STYLES.unknown
      }`}
    >
      {label}
    </span>
  );
}
