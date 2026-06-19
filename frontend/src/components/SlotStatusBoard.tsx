"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  modelCommitUrl,
  shortAddr,
  shortRepo,
  type SlotStatusEntry,
  type SlotStatusSummary,
} from "@/lib/api";
import { DASHBOARD_POLL_MS, useDashboardSync } from "@/lib/DashboardSyncContext";
import { getSubnetProfile } from "@/lib/subnets";
import {
  getSlotFilters,
  getSubnetTheme,
  isAlbedoPipeType,
  isPublishedPipeType,
  slotGridColor,
  slotTypeLabel,
  slotTypeStyle,
  type SlotFilterKey,
} from "@/lib/subnetTheme";
import { useSubnet } from "@/lib/useSubnet";
import SearchBar from "@/components/SearchBar";
import { ModelFamilyBadge } from "@/components/ModelFamilyBadge";
import { isSearchActive, matchesMinerFields } from "@/lib/searchFilter";
import { inferAlbedoModelFamily } from "@/lib/modelFamily";

function slotModelFamily(slot: SlotStatusEntry): string | null {
  return slot.model_family ?? inferAlbedoModelFamily(slot.detail);
}

function byUid(a: SlotStatusEntry, b: SlotStatusEntry) {
  return a.uid - b.uid;
}

function filterSlots(slots: SlotStatusEntry[], filter: SlotFilterKey, subnet: number): SlotStatusEntry[] {
  if (filter === "all") return slots;
  if (filter === "unpublished")
    return slots.filter(
      (s) =>
        s.is_published === false ||
        (s.is_published == null && !isPublishedPipeType(s.commitment_type, subnet))
    );
  if (filter === "committed") return slots.filter((s) => s.commitment_type !== "none");
  if (filter === "v6" && subnet === 97)
    return slots.filter((s) => isAlbedoPipeType(s.commitment_type));
  if (filter === "qwen36_35b" && subnet === 97)
    return slots.filter((s) => slotModelFamily(s) === "qwen3.6-35b");
  if (filter === "qwen3_4b" && subnet === 97)
    return slots.filter((s) => slotModelFamily(s) === "qwen3-4b");
  if (filter === "timelock_encrypted")
    return slots.filter((s) => s.commitment_type === "timelock_encrypted" || s.commitment_type === "binary");
  if (filter === "other")
    return slots.filter((s) => s.commitment_type === "other" || s.commitment_type === "unknown");
  return slots.filter((s) => s.commitment_type === filter);
}

export default function SlotStatusBoard() {
  const { subnet } = useSubnet();
  const profile = getSubnetProfile(subnet);
  const theme = getSubnetTheme(subnet);
  const filters = useMemo(() => getSlotFilters(subnet), [subnet]);
  const { slotData, lastRefresh, loading, apiError } = useDashboardSync();
  const [filter, setFilter] = useState<SlotFilterKey>(theme.slotDefaultFilter);
  const [search, setSearch] = useState("");
  const [highlightUid, setHighlightUid] = useState<number | null>(null);
  const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

  useEffect(() => {
    setFilter(theme.slotDefaultFilter);
    setSearch("");
    setHighlightUid(null);
  }, [subnet, theme.slotDefaultFilter]);

  const allSlots = useMemo(() => {
    const rows = slotData?.slots ?? [];
    return [...rows].sort(byUid);
  }, [slotData?.slots]);

  const summary = useMemo(() => slotData?.summary, [slotData?.summary]);

  const filteredSlots = useMemo(
    () => filterSlots(allSlots, filter, subnet).sort(byUid),
    [allSlots, filter, subnet]
  );

  const displaySlots = useMemo(() => {
    if (!isSearchActive(search)) return filteredSlots;
    return filteredSlots.filter((s) =>
      matchesMinerFields(search, {
        uid: s.uid,
        hotkey: s.hotkey,
        coldkey: s.coldkey,
        repo: s.detail,
        commitmentType: s.commitment_type,
        detail: s.detail,
      })
    );
  }, [filteredSlots, search]);

  const jumpToUid = useCallback((uid: number) => {
    setHighlightUid(uid);
    requestAnimationFrame(() => {
      rowRefs.current.get(uid)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }, []);

  const countFor = (key: SlotFilterKey, s: SlotStatusSummary | undefined) => {
    if (!s) return loading ? "…" : "—";
    const map: Record<SlotFilterKey, number | undefined> = {
      all: s.total_slots,
      committed: s.committed,
      v6: (s.v6 ?? 0) + (s.v7 ?? 0),
      qwen36_35b: s.qwen36_35b ?? 0,
      qwen3_4b: s.qwen3_4b ?? 0,
      unpublished: s.unpublished ?? 0,
      timelock_encrypted: s.timelock_encrypted + (s.binary ?? 0),
      json: s.json,
      other: s.other,
      none: s.none,
    };
    return String(map[key] ?? 0);
  };

  const primaryCount =
    theme.slotPrimaryType === "json"
      ? summary?.json ?? 0
      : (summary?.v6 ?? 0) + (summary?.v7 ?? 0);

  const gridLegend = useMemo(() => {
    if (subnet === 24) {
      return ["json", "v6", "timelock_encrypted", "other", "none"].map((k) => ({
        key: k,
        color: slotGridColor(subnet, k),
        label: slotTypeLabel(subnet, k === "timelock_encrypted" ? "timelock_encrypted" : k),
      }));
    }
    return ["v6", "v7", "timelock_encrypted", "unpublished", "none"].map((k) => ({
      key: k,
      color: slotGridColor(subnet, k === "unpublished" ? "json" : k),
      label: k === "unpublished" ? "unpublished" : slotTypeLabel(subnet, k),
    }));
  }, [subnet]);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">
            {profile.name} miner slots · SN{subnet}
          </h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            {profile.tagline} ·{" "}
            {loading && !slotData ? "loading…" : `256 UIDs · ${lastRefresh ? `updated ${Math.round((Date.now() - lastRefresh.getTime()) / 1000)}s ago` : "—"} · sync ${DASHBOARD_POLL_MS / 1000}s`}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <SearchBar
            value={search}
            onChange={setSearch}
            placeholder="uid, hotkey, coldkey, repo…"
            resultCount={displaySlots.length}
            totalCount={filteredSlots.length}
          />
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
          No <code className="mono text-violet-100">TimelockEncrypted</code> on <strong>SN{subnet}</strong> right now.
        </div>
      )}

      {summary && (
        <div className="px-3 py-2 border-b border-zinc-800/80 text-[10px] text-zinc-500">
          <strong className="text-zinc-300">{summary.committed}</strong> slots have a commit (
          <span className={theme.textAccent}>
            {primaryCount} {theme.slotSummaryPrimaryLabel}
          </span>
          {subnet === 97 && (
            <>
              , <span className="text-lime-400">{summary.v6} v6</span>
              {(summary.v7 ?? 0) > 0 && (
                <>
                  , <span className="text-emerald-400">{summary.v7} v7</span>
                </>
              )}
              {(summary.qwen36_35b ?? 0) > 0 && (
                <>
                  , <span className="text-sky-400">{summary.qwen36_35b} Qwen3.6-35B</span>
                </>
              )}
              {(summary.qwen3_4b ?? 0) > 0 && (
                <>
                  , <span className="text-amber-400">{summary.qwen3_4b} Qwen3-4B</span>
                </>
              )}
              , <span className="text-violet-400">{summary.timelock_encrypted + (summary.binary ?? 0)} enc</span>
              , <span className="text-rose-400">{summary.unpublished ?? 0} unpublished</span>
            </>
          )}
          {subnet === 24 && (summary.v6 ?? 0) > 0 && (
            <>
              , <span className="text-lime-400">{summary.v6} v5/v6</span>
            </>
          )}
          ) · <strong className="text-zinc-400">{summary.none}</strong> empty · showing{" "}
          <strong className="text-zinc-300">{displaySlots.length}</strong>
          {filter !== "all" ? ` (${filters.find((f) => f.key === filter)?.label ?? filter})` : ""}
          {isSearchActive(search) ? " · search" : ""}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 px-3 py-2 border-b border-zinc-800/80">
        {filters.map((f) => (
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
                title={`uid ${s.uid} · ${slotTypeLabel(subnet, s.commitment_type)}${s.registered_at_block ? ` · reg ${s.registered_at_block}` : ""}`}
                onClick={() => jumpToUid(s.uid)}
                className={`w-[10px] h-[10px] shrink-0 rounded-[2px] p-0 border-0 ${slotGridColor(subnet, s.commitment_type)} ${
                  filter !== "all" && !filterSlots([s], filter, subnet).length ? "opacity-30 saturate-50" : "opacity-100"
                } ${highlightUid === s.uid ? "ring-2 ring-white/90 ring-offset-1 ring-offset-zinc-950 scale-110 z-10" : ""} hover:ring-1 hover:ring-white/70 hover:brightness-110 cursor-pointer transition-all duration-100`}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-x-2.5 gap-y-1 mt-2 text-[9px] text-zinc-500">
            {gridLegend.map(({ key, color, label }) => (
              <span key={key} className="inline-flex items-center gap-1">
                <span className={`w-2 h-2 rounded-[2px] ${color}`} />
                {label}
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
                  {loading
                    ? "loading…"
                    : slotData
                      ? isSearchActive(search)
                        ? "no slots match search"
                        : "no slots match filter"
                      : "waiting for data…"}
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
                    <TypeBadge subnet={subnet} type={s.commitment_type} />
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
                    <SlotDetail subnet={subnet} slot={s} />
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

function SlotDetail({ subnet, slot }: { subnet: number; slot: SlotStatusEntry }) {
  const theme = getSubnetTheme(subnet);
  if (!slot.detail) return <>—</>;

  const isModelSlot =
    subnet === 97
      ? isAlbedoPipeType(slot.commitment_type)
      : slot.commitment_type === "v6" ||
        slot.commitment_type === "v5" ||
        slot.commitment_type === "v7" ||
        slot.commitment_type === "json";

  if (isModelSlot) {
    const family = slot.model_family ?? inferAlbedoModelFamily(slot.detail);
    return (
      <span className="inline-flex items-center gap-1.5 max-w-full">
        <a
          href={modelCommitUrl(slot.detail, "", theme.modelHost)}
          target="_blank"
          rel="noopener noreferrer"
          className={`${theme.textAccent} opacity-90 hover:underline truncate`}
        >
          {shortRepo(slot.detail, 28)}
        </a>
        <ModelFamilyBadge repo={slot.detail} family={family} />
      </span>
    );
  }

  return <>{slot.detail}</>;
}

function TypeBadge({ subnet, type }: { subnet: number; type: string }) {
  const label = slotTypeLabel(subnet, type);
  return (
    <span
      className={`inline-flex px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wide ${slotTypeStyle(subnet, type)}`}
    >
      {label}
    </span>
  );
}
