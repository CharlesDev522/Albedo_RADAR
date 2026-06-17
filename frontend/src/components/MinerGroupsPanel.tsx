"use client";

import { useMemo, useState } from "react";
import {
  hippiusModelUrl,
  shortAddr,
  shortRepo,
} from "@/lib/api";
import { useDashboardSync } from "@/lib/DashboardSyncContext";
import {
  buildMinerRows,
  clusterSummary,
  groupByColdkey,
  groupByOwner,
  ownerPalette,
  repoOwner,
  type GroupView,
  type MinerGroup,
} from "@/lib/minerGroups";
import { useSubnet } from "@/lib/useSubnet";

export default function MinerGroupsPanel() {
  const { subnet } = useSubnet();
  const { registry, commits } = useDashboardSync();
  const [view, setView] = useState<GroupView>("coldkey");
  const [multiOnly, setMultiOnly] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const rows = useMemo(() => buildMinerRows(registry, commits), [registry, commits]);
  const summary = useMemo(() => clusterSummary(rows), [rows]);

  const groups = useMemo(() => {
    return view === "coldkey" ? groupByColdkey(rows, multiOnly) : groupByOwner(rows, multiOnly);
  }, [rows, view, multiOnly]);

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">miner clusters · SN{subnet}</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            same coldkey operators · shared HuggingFace owners (happyconst, rsgold, …)
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <ViewToggle view={view} onView={setView} />
          <button
            type="button"
            onClick={() => setMultiOnly((v) => !v)}
            className={`px-2 py-0.5 rounded-full border text-[10px] transition-colors ${
              multiOnly
                ? "border-zinc-500 text-zinc-200 bg-zinc-800/60"
                : "border-zinc-800 text-zinc-600 hover:border-zinc-700"
            }`}
          >
            {multiOnly ? "multi only" : "all groups"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 p-3 border-b border-zinc-800/80">
        <MiniStat label="miners" value={String(summary.totalMiners)} />
        <MiniStat label="v6" value={String(summary.v6Miners)} accent />
        <MiniStat label="multi coldkeys" value={String(summary.multiColdkeys)} />
        <MiniStat label="multi HF owners" value={String(summary.multiOwners)} />
        <MiniStat label="largest coldkey" value={String(summary.largestColdkey)} />
        <MiniStat label="largest owner" value={String(summary.largestOwner)} />
      </div>

      {groups.length === 0 ? (
        <div className="px-3 py-10 text-center text-[11px] text-zinc-500">
          {multiOnly
            ? "no multi-miner groups yet — try “all groups” or wait for more registry data"
            : "no groups to show"}
        </div>
      ) : (
        <div className="p-3 grid grid-cols-1 lg:grid-cols-2 gap-3 max-h-[720px] overflow-y-auto">
          {groups.map((g) => (
            <GroupCard
              key={`${g.kind}-${g.key}`}
              group={g}
              view={view}
              open={expanded.has(g.key)}
              onToggle={() => toggleExpand(g.key)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ViewToggle({ view, onView }: { view: GroupView; onView: (v: GroupView) => void }) {
  return (
    <div className="inline-flex rounded-md border border-zinc-800 overflow-hidden text-[10px]">
      <button
        type="button"
        onClick={() => onView("coldkey")}
        className={`px-2.5 py-1 transition-colors ${
          view === "coldkey" ? "bg-zinc-800 text-zinc-100" : "text-zinc-600 hover:text-zinc-400"
        }`}
      >
        by coldkey
      </button>
      <button
        type="button"
        onClick={() => onView("owner")}
        className={`px-2.5 py-1 border-l border-zinc-800 transition-colors ${
          view === "owner" ? "bg-zinc-800 text-zinc-100" : "text-zinc-600 hover:text-zinc-400"
        }`}
      >
        by HF owner
      </button>
    </div>
  );
}

function GroupCard({
  group,
  view,
  open,
  onToggle,
}: {
  group: MinerGroup;
  view: GroupView;
  open: boolean;
  onToggle: () => void;
}) {
  const accent =
    view === "owner" ? ownerPalette(group.label) : ownerPalette(group.label.slice(-8));

  const topOwners = Object.entries(group.ownerCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);

  return (
    <article
      className={`rounded-md border ${accent.border} ${accent.bg} overflow-hidden shadow-sm`}
    >
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left px-3 py-2.5 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full shrink-0 ${accent.dot}`} />
              <p className={`text-[11px] font-semibold truncate ${accent.text}`}>
                {view === "coldkey" ? (
                  <span className="mono" title={group.label}>
                    {shortAddr(group.label, 6)}
                  </span>
                ) : (
                  group.label
                )}
              </p>
            </div>
            <p className="text-[10px] text-zinc-500 mt-1">
              {group.miners.length} miners · {group.v6Count} v6
              {view === "owner" && group.coldkeyCount > 1 && (
                <> · {group.coldkeyCount} coldkeys</>
              )}
            </p>
          </div>
          <span className="text-[10px] text-zinc-600 shrink-0">{open ? "▾" : "▸"}</span>
        </div>

        <div className="flex flex-wrap gap-1 mt-2">
          {group.miners.map((m) => (
            <UidChip key={m.uid} uid={m.uid} hasV6={m.hasV6} />
          ))}
        </div>

        {topOwners.length > 0 && view === "coldkey" && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {topOwners.map(([owner, count]) => {
              const pal = ownerPalette(owner);
              return (
                <span
                  key={owner}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] ${pal.border} ${pal.bg} ${pal.text}`}
                >
                  {owner}
                  <span className="mono opacity-70">×{count}</span>
                </span>
              );
            })}
          </div>
        )}
      </button>

      {open && (
        <div className="border-t border-zinc-800/60 bg-zinc-950/40">
          <table className="tbl">
            <thead>
              <tr>
                <th>uid</th>
                <th>hotkey</th>
                {view === "owner" && <th>coldkey</th>}
                <th>model</th>
              </tr>
            </thead>
            <tbody>
              {group.miners.map((m) => {
                const owner = repoOwner(m.repo);
                const pal = owner ? ownerPalette(owner) : null;
                return (
                  <tr key={m.uid}>
                    <td className="mono text-zinc-200">
                      {m.uid}
                      {m.hasV6 ? (
                        <span className="ml-1 text-[8px] text-lime-400">v6</span>
                      ) : (
                        <span className="ml-1 text-[8px] text-zinc-600">—</span>
                      )}
                    </td>
                    <td className="mono text-zinc-500" title={m.hotkey}>
                      {shortAddr(m.hotkey, 4)}
                    </td>
                    {view === "owner" && (
                      <td className="mono text-zinc-500" title={m.coldkey}>
                        {shortAddr(m.coldkey, 4)}
                      </td>
                    )}
                    <td className="text-[10px] max-w-[140px] truncate">
                      {m.repo ? (
                        <a
                          href={hippiusModelUrl(m.repo)}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`hover:underline ${pal?.text ?? "text-sky-400/80"}`}
                          title={hippiusModelUrl(m.repo)}
                        >
                          {shortRepo(m.repo, 22)}
                        </a>
                      ) : (
                        <span className="text-zinc-600">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}

function UidChip({ uid, hasV6 }: { uid: number; hasV6: boolean }) {
  return (
    <span
      className={`inline-flex items-center justify-center min-w-[26px] h-[18px] px-1 rounded text-[9px] mono tabular-nums border ${
        hasV6
          ? "border-lime-500/40 bg-lime-500/15 text-lime-300"
          : "border-zinc-700 bg-zinc-900/80 text-zinc-500"
      }`}
      title={hasV6 ? `uid ${uid} · v6` : `uid ${uid}`}
    >
      {uid}
    </span>
  );
}

function MiniStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800/80 bg-zinc-950/50 px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wide text-zinc-600">{label}</p>
      <p className={`text-[13px] font-semibold tabular-nums mt-0.5 ${accent ? "text-lime-400" : "text-zinc-200"}`}>
        {value}
      </p>
    </div>
  );
}
