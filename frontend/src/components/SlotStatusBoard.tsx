"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import {
  hippiusModelUrl,
  shortAddr,
  shortRepo,
  type SlotStatusEntry,
  type SlotStatusSummary,
} from "@/lib/api";
import { DASHBOARD_POLL_MS, useDashboardSync } from "@/lib/DashboardSyncContext";
import { useSubnet } from "@/lib/useSubnet";

type FilterKey =
  | "all"
  | "committed"
  | "v6"
  | "timelock_encrypted"
  | "json"
  | "other"
  | "none";

const FILTERS: { key: FilterKey; label: string; color: string; hint?: string }[] = [
  { key: "all", label: "all 256", color: "text-zinc-300 border-zinc-600" },
  { key: "committed", label: "has commit", color: "text-zinc-200 border-zinc-500 bg-zinc-800/40", hint: "any on-chain commit" },
  { key: "v6", label: "v6", color: "text-lime-400 border-lime-500/40 bg-lime-500/10" },
  { key: "timelock_encrypted", label: "encrypted", color: "text-violet-300 border-violet-500/40 bg-violet-500/10", hint: "TimelockEncrypted" },
  { key: "json", label: "json", color: "text-amber-300 border-amber-500/40 bg-amber-500/10" },
  { key: "other", label: "other", color: "text-orange-300 border-orange-500/40 bg-orange-500/10" },
  { key: "none", label: "no commit", color: "text-zinc-500 border-zinc-700 bg-zinc-800/30" },
];

function byUid(a: SlotStatusEntry, b: SlotStatusEntry) {
  return a.uid - b.uid;
}

const TYPE_STYLES: Record<string, string> = {
  v6: "text-lime-400 border-lime-500/30 bg-lime-500/10",
  timelock_encrypted: "text-violet-300 border-violet-500/30 bg-violet-500/10",
  binary: "text-violet-300 border-violet-500/30 bg-violet-500/10",
  json: "text-amber-300 border-amber-500/30 bg-amber-500/10",
  other: "text-orange-300 border-orange-500/30 bg-orange-500/10",
  unknown: "text-rose-300 border-rose-500/30 bg-rose-500/10",
  none: "text-zinc-500 border-zinc-700 bg-zinc-800/20",
};

const GRID_COLORS: Record<string, string> = {
  v6: "bg-lime-500",
  timelock_encrypted: "bg-violet-500",
  binary: "bg-violet-600",
  json: "bg-amber-500",
  other: "bg-orange-500",
  unknown: "bg-rose-500",
  none: "bg-zinc-700",
};

function filterSlots(slots: SlotStatusEntry[], filter: FilterKey): SlotStatusEntry[] {
  if (filter === "all") return slots;
  if (filter === "committed") return slots.filter((s) => s.commitment_type !== "none");
  if (filter === "timelock_encrypted")
    return slots.filter((s) => s.commitment_type === "timelock_encrypted" || s.commitment_type === "binary");
  if (filter === "other")
    return slots.filter((s) => s.commitment_type === "other" || s.commitment_type === "unknown");
  return slots.filter((s) => s.commitment_type === filter);
}

function summaryFromSlots(subnet: number, slots: SlotStatusEntry[]): SlotStatusSummary {
  const counts: Record<string, number> = {};
  for (const s of slots) counts[s.commitment_type] = (counts[s.commitment_type] ?? 0) + 1;
  return {
    subnet,
    total_slots: slots.length,
    v6: counts.v6 ?? 0,
    json: counts.json ?? 0,
    timelock_encrypted: counts.timelock_encrypted ?? 0,
    binary: counts.binary ?? 0,
    other: (counts.other ?? 0) + (counts.unknown ?? 0),
    unknown: counts.unknown ?? 0,
    none: counts.none ?? 0,
    committed: slots.length - (counts.none ?? 0),
    last_scan_at: new Date().toISOString(),
  };
}

export default function SlotStatusBoard() {
  const { subnet } = useSubnet();
  const { slotData, lastRefresh, loading, apiError } = useDashboardSync();
  const [filter, setFilter] = useState<FilterKey>("committed");
  const [highlightUid, setHighlightUid] = useState<number | null>(null);
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  const allSlots = useMemo(() => {
    const rows = slotData?.slots ?? [];
    return [...rows].sort(byUid);
  }, [slotData?.slots]);

  const summary = useMemo(() => {
    if (allSlots.length > 0) return summaryFromSlots(subnet, allSlots);
    return slotData?.summary;
  }, [allSlots, slotData?.summary, subnet]);

  const displaySlots = useMemo(
    () => filterSlots(allSlots, filter).sort(byUid),
    [allSlots, filter]
  );

  const jumpToUid = useCallback((uid: number) => {
    setHighlightUid(uid);
    requestAnimationFrame(() => {
      rowRefs.current.get(uid)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }, []);

  const countFor = (key: FilterKey, s: SlotStatusSummary | undefined) => {
    if (!s) return loading ? "…" : "—";
    const map: Record<FilterKey, number | undefined> = {
      all: s.total_slots,
      committed: s.committed,
      v6: s.v6 ?? 0,
      timelock_encrypted: s.timelock_encrypted + (s.binary ?? 0),
      json: s.json,
      other: s.other,
      none: s.none,
    };
    return String(map[key] ?? 0);
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">miner slots · SN{subnet}</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            {loading && !slotData ? "loading…" : `256 UIDs · ${lastRefresh ? `updated ${Math.round((Date.now() - lastRefresh.getTime()) / 1000)}s ago` : "—"} · sync ${DASHBOARD_POLL_MS / 1000}s`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <span className="text-[9px] text-zinc-600 mono">
            {slotData?.source === "chain" ? "● live chain" : slotData ? "db · synced" : "…"}
          </span>
        </div>
      </div>

      {apiError && (
        <div className="px-3 py-2 border-b border-rose-500/20 bg-rose-500/5 text-[10px] text-rose-300">{apiError}</div>
      )}

      {filter === "timelock_encrypted" && summary && summary.timelock_encrypted + (summary.binary ?? 0) === 0 && !loading && (
        <div className="px-3 py-2 border-b border-violet-500/20 bg-violet-500/5 text-[10px] text-violet-200/90 leading-relaxed">
          No <code className="mono text-violet-100">TimelockEncrypted</code> on <strong>SN{subnet}</strong> (finney) right now.
        </div>
      )}

      {summary && (
        <div className="px-3 py-2 border-b border-zinc-800/80 text-[10px] text-zinc-500">
          <strong className="text-zinc-300">{summary.committed}</strong> slots have a commit (
          <span className="text-lime-400">{summary.v6 ?? 0} v6</span>,{" "}
          <span className="text-violet-400">{summary.timelock_encrypted + (summary.binary ?? 0)} enc</span>,{" "}
          <span className="text-amber-400">{summary.json} json</span>) ·{" "}
          <strong className="text-zinc-400">{summary.none}</strong> empty · showing{" "}
          <strong className="text-zinc-300">{displaySlots.length}</strong>
          {filter !== "all" ? ` (${filter})` : ""}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 px-3 py-2 border-b border-zinc-800/80">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            title={f.hint}
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

      {allSlots.length > 0 && (
        <div className="px-3 py-2.5 border-b border-zinc-800/80 w-full">
          <div
            className="w-full flex flex-wrap gap-[2px] p-1.5 bg-zinc-950/60 border border-zinc-800/70 rounded-md shadow-inner content-start"
            title="UID 0→255 left-to-right — click to jump to table row"
          >
            {allSlots.map((s) => (
              <button
                key={s.uid}
                type="button"
                title={`uid ${s.uid} · ${s.commitment_type}${s.registered_at_block ? ` · reg ${s.registered_at_block}` : ""}`}
                onClick={() => jumpToUid(s.uid)}
                className={`w-[10px] h-[10px] shrink-0 rounded-[2px] p-0 border-0 ${GRID_COLORS[s.commitment_type] ?? "bg-zinc-700"} ${
                  filter !== "all" && !filterSlots([s], filter).length ? "opacity-30 saturate-50" : "opacity-100"
                } ${highlightUid === s.uid ? "ring-2 ring-white/90 ring-offset-1 ring-offset-zinc-950 scale-110 z-10" : ""} hover:ring-1 hover:ring-white/70 hover:brightness-110 cursor-pointer transition-all duration-100`}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-x-2.5 gap-y-1 mt-2 text-[9px] text-zinc-500">
            {Object.entries(GRID_COLORS).map(([k, c]) => (
              <span key={k} className="inline-flex items-center gap-1">
                <span className={`w-2 h-2 rounded-[2px] ${c}`} />
                {k === "timelock_encrypted" ? "encrypted" : k === "none" ? "empty" : k}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
        <table className="tbl">
          <thead className="sticky top-0 z-10 bg-zinc-950">
            <tr>
              <th>uid</th>
              <th>type</th>
              <th>registered</th>
              <th>commit blk</th>
              <th>reveal rnd</th>
              <th>hotkey</th>
              <th>coldkey</th>
              <th>detail</th>
            </tr>
          </thead>
          <tbody>
            {displaySlots.length === 0 ? (
              <tr>
                <td colSpan={8} className="text-center text-zinc-500 py-8 text-[10px]">
                  {loading ? "loading…" : slotData ? "no slots match filter" : "waiting for data…"}
                </td>
              </tr>
            ) : (
              displaySlots.map((s) => (
                <tr
                  key={s.uid}
                  ref={(el) => {
                    if (el) rowRefs.current.set(s.uid, el);
                    else rowRefs.current.delete(s.uid);
                  }}
                  className={`${s.commitment_type === "none" ? "opacity-50" : ""} ${
                    highlightUid === s.uid ? "bg-zinc-800/60" : ""
                  }`}
                >
                  <td className="mono font-medium text-zinc-200 tabular-nums">{s.uid}</td>
                  <td>
                    <TypeBadge type={s.commitment_type} />
                  </td>
                  <td className="mono text-zinc-400 tabular-nums">
                    {s.registered_at_block?.toLocaleString() ?? "—"}
                  </td>
                  <td className="mono text-zinc-500 tabular-nums">
                    {s.commit_block?.toLocaleString() ?? "—"}
                  </td>
                  <td className="mono text-zinc-500 tabular-nums">
                    {s.reveal_round?.toLocaleString() ?? "—"}
                  </td>
                  <td className="mono text-zinc-500" title={s.hotkey}>
                    {shortAddr(s.hotkey, 5)}
                  </td>
                  <td className="mono text-zinc-500" title={s.coldkey ?? undefined}>
                    {s.coldkey ? shortAddr(s.coldkey, 5) : "—"}
                  </td>
                  <td className="text-[10px] text-zinc-500 max-w-[180px] truncate">
                    {s.commitment_type === "v6" && s.detail ? (
                      <a
                        href={hippiusModelUrl(s.detail)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-lime-400/80 hover:underline"
                      >
                        {shortRepo(s.detail, 28)}
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
    type === "timelock_encrypted" || type === "binary"
      ? "encrypted"
      : type === "none"
        ? "—"
        : type;
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
