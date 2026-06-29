"use client";

import { useMemo, useState } from "react";
import {
  shortHash,
  shortRepo,
  type PriorityMinerRepoStatus,
  type PriorityMinerStatus,
} from "@/lib/api";

type Filter = "all" | "pinned" | "top";

/** Latest repos shown per miner — sorted by most recent hub activity */
const LATEST_REPOS_LIMIT = 10;

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const now = Date.now();
  const diffMin = Math.round((now - d.getTime()) / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 24 * 60) return `${Math.floor(diffMin / 60)}h ago`;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(0)}%`;
}

function repoActivityTs(repo: PriorityMinerRepoStatus): number {
  const candidates = [repo.last_event_at, repo.hippius_updated_at, repo.huggingface_updated_at];
  let max = 0;
  for (const iso of candidates) {
    if (!iso) continue;
    const t = new Date(iso).getTime();
    if (t > max) max = t;
  }
  return max;
}

function pickLatestRepos(repos: PriorityMinerRepoStatus[], limit = LATEST_REPOS_LIMIT): PriorityMinerRepoStatus[] {
  return [...repos]
    .sort((a, b) => {
      const ta = repoActivityTs(a);
      const tb = repoActivityTs(b);
      if (tb !== ta) return tb - ta;
      return a.repo.localeCompare(b.repo);
    })
    .slice(0, limit);
}

function HostDot({ ok, pending, label }: { ok: boolean; pending: boolean; label: string }) {
  const color = ok ? "bg-emerald-400" : pending ? "bg-zinc-600" : "bg-amber-500/80";
  return (
    <span className="inline-flex items-center gap-1" title={`${label}: ${ok ? "live" : pending ? "pending" : "missing"}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${color}`} />
      <span className="text-[8px] text-zinc-500 uppercase">{label}</span>
    </span>
  );
}

function LatestRepoRow({ repo, rank }: { repo: PriorityMinerRepoStatus; rank: number }) {
  const activity = fmtTime(
    repo.last_event_at ?? repo.hippius_updated_at ?? repo.huggingface_updated_at
  );
  const hippiusOk = repo.hippius_tracked && !repo.hippius_pending;
  const hfOk = repo.huggingface_exists;

  return (
    <div className="flex flex-col gap-1.5 rounded-md border border-zinc-800/90 bg-zinc-900/50 px-2.5 py-2 hover:border-zinc-700/80 transition-colors">
      <div className="flex items-start justify-between gap-2 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[9px] mono text-zinc-600 w-4 shrink-0">#{rank}</span>
            <a
              href={repo.hippius_url ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-semibold text-zinc-100 hover:text-sky-300 truncate"
              title={repo.repo}
            >
              {shortRepo(repo.repo, 38)}
            </a>
          </div>
          {repo.last_event_type ? (
            <p className="text-[9px] text-fuchsia-300/80 mt-0.5 ml-6">
              {repo.last_event_type.replace(/_/g, " ")} · {activity}
            </p>
          ) : (
            <p className="text-[9px] text-zinc-600 mt-0.5 ml-6">last activity {activity}</p>
          )}
        </div>
        {repo.duel_count > 0 && (
          <span className="text-[9px] mono text-zinc-500 shrink-0">
            {repo.duel_count}d · {fmtPct(repo.challenger_win_pct)}
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 ml-6">
        <HostDot ok={hippiusOk} pending={repo.hippius_pending} label="hip" />
        <a
          href={repo.hippius_url ?? "#"}
          target="_blank"
          rel="noreferrer"
          className="text-[9px] text-sky-400/90 hover:underline truncate max-w-[160px]"
          title={repo.hippius_url ?? undefined}
        >
          {hippiusOk && repo.hippius_digest ? shortHash(repo.hippius_digest) : "hub.hippius.com"}
        </a>
        <span className="text-zinc-800">·</span>
        <HostDot ok={hfOk} pending={repo.huggingface_pending} label="hf" />
        <a
          href={repo.huggingface_url ?? "#"}
          target="_blank"
          rel="noreferrer"
          className="text-[9px] text-orange-400/90 hover:underline truncate max-w-[160px]"
          title={repo.huggingface_url ?? undefined}
        >
          {hfOk && repo.huggingface_digest ? shortHash(repo.huggingface_digest) : "huggingface.co"}
        </a>
      </div>
    </div>
  );
}

function MinerCard({ miner }: { miner: PriorityMinerStatus }) {
  const [expanded, setExpanded] = useState(miner.watch_source === "pinned");
  const latest = useMemo(() => pickLatestRepos(miner.repos), [miner.repos]);
  const hiddenCount = Math.max(0, miner.repos.length - latest.length);

  return (
    <article className="rounded-lg border border-zinc-800/90 bg-zinc-950/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-zinc-900/50"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-zinc-600 text-[10px] w-3">{expanded ? "−" : "+"}</span>
          <span className="text-[13px] font-semibold text-zinc-50">{miner.namespace}</span>
          <span
            className={`text-[8px] px-1.5 py-0.5 rounded font-medium ${
              miner.watch_source === "pinned"
                ? "bg-fuchsia-500/15 text-fuchsia-200 border border-fuchsia-500/30"
                : "bg-cyan-500/15 text-cyan-200 border border-cyan-500/30"
            }`}
          >
            {miner.watch_source === "pinned" ? "pinned" : `#${miner.challenger_rank}`}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[9px] text-zinc-500 shrink-0">
          {miner.duel_count > 0 && (
            <span>
              <span className="text-zinc-300">{miner.duel_count}</span> duels
            </span>
          )}
          <span className="text-violet-300">{miner.updates_24h} upd</span>
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-2 border-t border-zinc-800/50 pt-2">
          {latest.length === 0 ? (
            <p className="text-[10px] text-zinc-600 py-1">No repos yet — sync registries.</p>
          ) : (
            latest.map((repo, i) => <LatestRepoRow key={repo.repo} repo={repo} rank={i + 1} />)
          )}
          {hiddenCount > 0 && (
            <p className="text-[9px] text-zinc-600 text-center pt-1">
              {hiddenCount} older repos hidden · {miner.discovered_repos} total
            </p>
          )}
        </div>
      )}

      {!expanded && latest.length > 0 && (
        <div className="px-3 pb-2.5 border-t border-zinc-800/40 pt-2">
          <LatestRepoRow repo={latest[0]} rank={1} />
          {latest.length > 1 && (
            <p className="text-[9px] text-zinc-600 mt-1.5 ml-1">
              +{latest.length - 1} more recent · expand for latest {LATEST_REPOS_LIMIT}
            </p>
          )}
        </div>
      )}
    </article>
  );
}

export default function PriorityMinersPanel({
  miners,
  loading,
}: {
  miners: PriorityMinerStatus[];
  loading?: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    if (filter === "pinned") return miners.filter((m) => m.watch_source === "pinned");
    if (filter === "top") return miners.filter((m) => m.watch_source === "top_challenger");
    return miners;
  }, [miners, filter]);

  const pinnedCount = miners.filter((m) => m.watch_source === "pinned").length;
  const topCount = miners.filter((m) => m.watch_source === "top_challenger").length;

  if (loading && !miners.length) {
    return (
      <section className="panel px-3 py-2 text-[10px] text-zinc-500">
        Loading challenger watchlist…
      </section>
    );
  }
  if (!miners.length) return null;

  return (
    <section className="panel px-3 py-2.5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[12px] font-semibold text-zinc-100">Priority miner repos</h3>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Latest {LATEST_REPOS_LIMIT} repos per namespace · sorted by recent hub activity
          </p>
        </div>
        <div className="flex gap-1 text-[9px]">
          {(
            [
              ["all", `All (${miners.length})`],
              ["pinned", `Pinned (${pinnedCount})`],
              ["top", `Challengers (${topCount})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`px-2 py-1 rounded border ${
                filter === key
                  ? "border-sky-500/50 bg-sky-500/15 text-sky-100"
                  : "border-zinc-700 text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {filtered.map((miner) => (
          <MinerCard key={`${miner.namespace}:${miner.watch_source}`} miner={miner} />
        ))}
      </div>
    </section>
  );
}
