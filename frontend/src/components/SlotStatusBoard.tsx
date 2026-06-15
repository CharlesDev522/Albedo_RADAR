"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  hippiusModelUrl,
  shortAddr,
  shortRepo,
  type SlotStatusData,
  type SlotStatusEntry,
  type SlotStatusSummary,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const POLL_MS = 5000;

type FilterKey =
  | "all"
  | "committed"
  | "v5"
  | "non_v5"
  | "timelock_encrypted"
  | "v4"
  | "json"
  | "none";

type SortKey = "uid_asc" | "uid_desc" | "reg_asc" | "reg_desc" | "commit_asc" | "commit_desc" | "type";

const FILTERS: { key: FilterKey; label: string; color: string; hint?: string }[] = [
  { key: "all", label: "all 256", color: "text-zinc-300 border-zinc-600" },
  { key: "committed", label: "has commit", color: "text-zinc-200 border-zinc-500 bg-zinc-800/40", hint: "any on-chain commit" },
  { key: "v5", label: "v5", color: "text-emerald-400 border-emerald-500/40 bg-emerald-500/10" },
  { key: "non_v5", label: "non-v5", color: "text-sky-300 border-sky-500/40 bg-sky-500/10", hint: "v4 / json / encrypted" },
  { key: "timelock_encrypted", label: "encrypted", color: "text-violet-300 border-violet-500/40 bg-violet-500/10", hint: "TimelockEncrypted" },
  { key: "v4", label: "v4 legacy", color: "text-sky-300 border-sky-500/40 bg-sky-500/10" },
  { key: "json", label: "json", color: "text-amber-300 border-amber-500/40 bg-amber-500/10" },
  { key: "none", label: "no commit", color: "text-zinc-500 border-zinc-700 bg-zinc-800/30" },
];

const SORTS: { key: SortKey; label: string }[] = [
  { key: "uid_asc", label: "uid ↑" },
  { key: "uid_desc", label: "uid ↓" },
  { key: "reg_desc", label: "registered ↓" },
  { key: "reg_asc", label: "registered ↑" },
  { key: "commit_desc", label: "commit blk ↓" },
  { key: "commit_asc", label: "commit blk ↑" },
  { key: "type", label: "type" },
];

const TYPE_STYLES: Record<string, string> = {
  v5: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  timelock_encrypted: "text-violet-300 border-violet-500/30 bg-violet-500/10",
  binary: "text-violet-300 border-violet-500/30 bg-violet-500/10",
  v4: "text-sky-300 border-sky-500/30 bg-sky-500/10",
  json: "text-amber-300 border-amber-500/30 bg-amber-500/10",
  other: "text-orange-300 border-orange-500/30 bg-orange-500/10",
  unknown: "text-rose-300 border-rose-500/30 bg-rose-500/10",
  none: "text-zinc-500 border-zinc-700 bg-zinc-800/20",
};

const GRID_COLORS: Record<string, string> = {
  v5: "bg-emerald-500",
  timelock_encrypted: "bg-violet-500",
  binary: "bg-violet-600",
  v4: "bg-sky-500",
  json: "bg-amber-500",
  other: "bg-orange-500",
  unknown: "bg-rose-500",
  none: "bg-zinc-700",
};

function filterSlots(slots: SlotStatusEntry[], filter: FilterKey): SlotStatusEntry[] {
  if (filter === "all") return slots;
  if (filter === "committed") return slots.filter((s) => s.commitment_type !== "none");
  if (filter === "non_v5") return slots.filter((s) => s.commitment_type !== "none" && s.commitment_type !== "v5");
  if (filter === "timelock_encrypted")
    return slots.filter((s) => s.commitment_type === "timelock_encrypted" || s.commitment_type === "binary");
  return slots.filter((s) => s.commitment_type === filter);
}

function sortSlots(slots: SlotStatusEntry[], sort: SortKey): SlotStatusEntry[] {
  const copy = [...slots];
  const reg = (s: SlotStatusEntry) => s.registered_at_block ?? -1;
  const commit = (s: SlotStatusEntry) => s.commit_block ?? -1;
  switch (sort) {
    case "uid_desc":
      return copy.sort((a, b) => b.uid - a.uid);
    case "reg_asc":
      return copy.sort((a, b) => reg(a) - reg(b) || a.uid - b.uid);
    case "reg_desc":
      return copy.sort((a, b) => reg(b) - reg(a) || a.uid - b.uid);
    case "commit_asc":
      return copy.sort((a, b) => commit(a) - commit(b) || a.uid - b.uid);
    case "commit_desc":
      return copy.sort((a, b) => commit(b) - commit(a) || a.uid - b.uid);
    case "type":
      return copy.sort((a, b) => a.commitment_type.localeCompare(b.commitment_type) || a.uid - b.uid);
    default:
      return copy.sort((a, b) => a.uid - b.uid);
  }
}

export default function SlotStatusBoard() {
  const { subnet, setSubnet, presets } = useSubnet();
  const [filter, setFilter] = useState<FilterKey>("committed");
  const [sort, setSort] = useState<SortKey>("uid_asc");
  const [data, setData] = useState<SlotStatusData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlightUid, setHighlightUid] = useState<number | null>(null);
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  const refresh = useCallback(async () => {
    try {
      const res = await api.getSlotStatus(subnet, "all", sort, true);
      setData(res);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to load slots");
    }
  }, [subnet, sort]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const summary = data?.summary;
  const allSlots = data?.slots ?? [];
  const displaySlots = useMemo(
    () => sortSlots(filterSlots(allSlots, filter), sort),
    [allSlots, filter, sort]
  );

  const jumpToUid = useCallback((uid: number) => {
    setHighlightUid(uid);
    requestAnimationFrame(() => {
      rowRefs.current.get(uid)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }, []);

  const countFor = (key: FilterKey, s: SlotStatusSummary | undefined) => {
    if (!s) return "—";
    const map: Record<FilterKey, number | undefined> = {
      all: s.total_slots,
      committed: s.committed,
      v5: s.v5,
      non_v5: s.non_v5,
      timelock_encrypted: s.timelock_encrypted + (s.binary ?? 0),
      v4: s.v4,
      json: s.json,
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
            all 256 UIDs · registered block · commit type (live chain scan)
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <label className="inline-flex items-center gap-1 text-[10px] text-zinc-500">
            subnet
            <select
              value={presets.includes(subnet as (typeof presets)[number]) ? subnet : "custom"}
              onChange={(e) => {
                const v = e.target.value;
                if (v !== "custom") setSubnet(Number(v));
              }}
              className="text-[10px] bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 text-zinc-300 mono"
            >
              {presets.map((n) => (
                <option key={n} value={n}>
                  SN{n}
                </option>
              ))}
              <option value="custom">custom</option>
            </select>
            {!presets.includes(subnet as (typeof presets)[number]) && (
              <input
                type="number"
                min={0}
                max={65535}
                value={subnet}
                onChange={(e) => setSubnet(Number(e.target.value) || 0)}
                className="w-12 text-[10px] bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 text-zinc-300 mono"
              />
            )}
          </label>
          <span className="text-[9px] text-zinc-600 mono">
            {data?.source === "chain" ? "● live chain" : "db"}
          </span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="text-[10px] bg-zinc-900 border border-zinc-700 rounded px-1.5 py-0.5 text-zinc-300"
          >
            {SORTS.map((s) => (
              <option key={s.key} value={s.key}>
                sort: {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error && (
        <div className="px-3 py-2 border-b border-rose-500/20 bg-rose-500/5 text-[10px] text-rose-300">{error}</div>
      )}

      {filter === "timelock_encrypted" && summary && summary.timelock_encrypted + (summary.binary ?? 0) === 0 && (
        <div className="px-3 py-2 border-b border-violet-500/20 bg-violet-500/5 text-[10px] text-violet-200/90 leading-relaxed">
          No <code className="mono text-violet-100">TimelockEncrypted</code> on <strong>SN{subnet}</strong> (finney) right
          now. Check the subnet selector — explorer JSON often shows a different <code className="mono">netuid</code> than
          SN97. On SN97, uid 5 is <strong>v4 legacy</strong> (sky blue), not encrypted. Violet slots appear after{" "}
          <code className="mono">set_reveal_commitment</code> is on chain.
        </div>
      )}

      {summary && (
        <div className="px-3 py-2 border-b border-zinc-800/80 text-[10px] text-zinc-500">
          <strong className="text-zinc-300">{summary.committed}</strong> slots have a commit on chain (
          <span className="text-emerald-400">{summary.v5} v5</span>,{" "}
          <span className="text-sky-400">{summary.v4} v4</span>,{" "}
          <span className="text-violet-400">{summary.timelock_encrypted + (summary.binary ?? 0)} encrypted</span>,{" "}
          <span className="text-amber-400">{summary.json} json</span>) ·{" "}
          <strong className="text-zinc-400">{summary.none}</strong> with no commit
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
        <div className="px-3 py-2 border-b border-zinc-800/80">
          <div
            className="inline-grid gap-px p-px bg-zinc-800/60 rounded"
            style={{ gridTemplateColumns: "repeat(32, 4px)" }}
            title="256 UID slots — click to jump to row"
          >
            {sortSlots(allSlots, "uid_asc").map((s) => (
              <button
                key={s.uid}
                type="button"
                title={`uid ${s.uid} · ${s.commitment_type}${s.registered_at_block ? ` · reg ${s.registered_at_block}` : ""}`}
                onClick={() => jumpToUid(s.uid)}
                className={`w-[4px] h-[4px] rounded-[0.5px] p-0 border-0 ${GRID_COLORS[s.commitment_type] ?? "bg-zinc-700"} ${
                  filter !== "all" && !filterSlots([s], filter).length ? "opacity-25" : "opacity-100"
                } ${highlightUid === s.uid ? "ring-1 ring-white scale-150 z-10" : ""} hover:ring-1 hover:ring-white/60 hover:scale-125 cursor-pointer transition-transform`}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-x-2 gap-y-0.5 mt-1.5 text-[8px] text-zinc-600">
            {Object.entries(GRID_COLORS).map(([k, c]) => (
              <span key={k} className="inline-flex items-center gap-0.5">
                <span className={`w-1 h-1 rounded-[0.5px] ${c}`} />
                {k === "timelock_encrypted" ? "enc" : k === "none" ? "empty" : k}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
        <table className="tbl">
          <thead className="sticky top-0 z-10">
            <tr>
              <th>uid</th>
              <th>type</th>
              <th>registered</th>
              <th>commit blk</th>
              <th>reveal rnd</th>
              <th>hotkey</th>
              <th>detail</th>
            </tr>
          </thead>
          <tbody>
            {displaySlots.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center text-zinc-500 py-8 text-[10px]">
                  {data ? "no slots match filter" : "loading from chain…"}
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
                  <td className="mono font-medium text-zinc-200">{s.uid}</td>
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
                  <td className="text-[10px] text-zinc-500 max-w-[180px] truncate">
                    {s.commitment_type === "v5" && s.detail ? (
                      <a
                        href={hippiusModelUrl(s.detail)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-emerald-400/80 hover:underline"
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
