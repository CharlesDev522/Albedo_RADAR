"use client";

import { useMemo, useState } from "react";
import {
  shortHash,
  shortRepo,
  type PriorityMinerRepoStatus,
  type PriorityMinerStatus,
} from "@/lib/api";

type Filter = "all" | "pinned" | "top";

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(0)}%`;
}

function HostPill({
  label,
  ok,
  pending,
  url,
  digest,
  message,
  updatedAt,
}: {
  label: string;
  ok: boolean;
  pending: boolean;
  url: string;
  digest?: string | null;
  message?: string | null;
  updatedAt?: string | null;
}) {
  const tone = ok
    ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-200"
    : pending
      ? "border-zinc-700 bg-zinc-900/60 text-zinc-500"
      : "border-amber-500/30 bg-amber-500/10 text-amber-200/90";

  return (
    <div className={`rounded-md border px-2 py-1.5 min-w-0 ${tone}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[9px] font-medium uppercase tracking-wide opacity-80">{label}</span>
        <span className="text-[8px]">{ok ? "live" : pending ? "pending" : "missing"}</span>
      </div>
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="block text-[9px] text-sky-300 hover:underline truncate mt-1"
        title={url}
      >
        {url.replace(/^https?:\/\//, "")}
      </a>
      {ok && digest && (
        <p className="text-[8px] mono text-zinc-500 mt-0.5 truncate" title={digest}>
          {shortHash(digest)}
        </p>
      )}
      <p className="text-[8px] text-zinc-600 mt-0.5 truncate" title={message ?? undefined}>
        {message ? message.slice(0, 48) : fmtTime(updatedAt)}
      </p>
    </div>
  );
}

function RepoCard({ repo }: { repo: PriorityMinerRepoStatus }) {
  return (
    <div className="rounded-lg border border-zinc-800/80 bg-zinc-950/40 p-2 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <a
              href={repo.hippius_url ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-medium text-zinc-100 hover:text-sky-300 truncate max-w-[240px]"
              title={repo.repo}
            >
              {shortRepo(repo.repo, 36)}
            </a>
            {repo.is_top_repo && (
              <span className="text-[8px] px-1 rounded border border-violet-500/40 text-violet-300 bg-violet-500/10">
                top repo
              </span>
            )}
          </div>
          {repo.duel_count > 0 && (
            <p className="text-[9px] text-zinc-500 mt-0.5">
              {repo.duel_count} duels · {repo.challenger_wins} wins ({fmtPct(repo.challenger_win_pct)})
              {repo.coronations > 0 && <span className="text-amber-400"> · {repo.coronations} crowns</span>}
            </p>
          )}
          {repo.last_event_type && (
            <p className="text-[8px] text-fuchsia-300/90 mt-0.5">
              {repo.last_event_type.replace(/_/g, " ")} · {fmtTime(repo.last_event_at)}
            </p>
          )}
        </div>
      </div>
      <div className="grid sm:grid-cols-2 gap-2">
        <HostPill
          label="Hippius"
          ok={repo.hippius_tracked && !repo.hippius_pending}
          pending={repo.hippius_pending}
          url={repo.hippius_url ?? "#"}
          digest={repo.hippius_digest}
          message={repo.hippius_commit_message}
          updatedAt={repo.hippius_updated_at}
        />
        <HostPill
          label="Hugging Face"
          ok={repo.huggingface_exists}
          pending={repo.huggingface_pending}
          url={repo.huggingface_url ?? "#"}
          digest={repo.huggingface_digest}
          message={repo.huggingface_commit_message}
          updatedAt={repo.huggingface_updated_at}
        />
      </div>
    </div>
  );
}

function MinerCard({ miner }: { miner: PriorityMinerStatus }) {
  const [open, setOpen] = useState(true);
  const showRepos = open ? miner.repos.slice(0, 8) : [];

  return (
    <article className="rounded-lg border border-zinc-800 bg-zinc-950/30 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-left hover:bg-zinc-900/40"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-zinc-500 text-[10px]">{open ? "▼" : "▶"}</span>
          <span className="text-[12px] font-semibold text-zinc-100">{miner.namespace}</span>
          <span
            className={`text-[8px] px-1.5 py-0.5 rounded border ${
              miner.watch_source === "pinned"
                ? "border-fuchsia-500/40 text-fuchsia-200 bg-fuchsia-500/10"
                : "border-cyan-500/40 text-cyan-200 bg-cyan-500/10"
            }`}
          >
            {miner.watch_source === "pinned" ? "pinned" : `top #${miner.challenger_rank}`}
          </span>
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[9px] text-zinc-500">
          {miner.duel_count > 0 && (
            <span>
              <span className="text-zinc-300 mono">{miner.duel_count}</span> duels ·{" "}
              <span className="text-emerald-300 mono">{fmtPct(miner.challenger_win_pct)}</span> win
            </span>
          )}
          <span className="text-sky-300">{miner.hippius_tracked_count} hippius</span>
          <span className="text-orange-300">{miner.huggingface_tracked_count} HF</span>
          <span className="text-violet-300">{miner.updates_24h} upd/24h</span>
        </div>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-2 border-t border-zinc-800/60 pt-2">
          {showRepos.length === 0 ? (
            <p className="text-[10px] text-zinc-600">No repos discovered yet — run sync registries.</p>
          ) : (
            showRepos.map((repo) => <RepoCard key={repo.repo} repo={repo} />)
          )}
          {miner.repos.length > 8 && (
            <p className="text-[9px] text-zinc-600 text-center">
              +{miner.repos.length - 8} more repos — search tracked table below
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
  if (!miners.length) {
    return null;
  }

  return (
    <section className="panel px-3 py-2.5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-[12px] font-semibold text-zinc-100">Challenger watchlist</h3>
          <p className="text-[10px] text-zinc-500 mt-0.5 max-w-2xl">
            Pinned miners + top duel challengers from live analysis. Each repo polled on Hippius and
            Hugging Face with direct hub URLs.
          </p>
        </div>
        <div className="flex gap-1 text-[9px]">
          {(
            [
              ["all", `All (${miners.length})`],
              ["pinned", `Pinned (${pinnedCount})`],
              ["top", `Top (${topCount})`],
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

      <div className="grid gap-2 lg:grid-cols-2">
        {filtered.map((miner) => (
          <MinerCard key={`${miner.namespace}:${miner.watch_source}`} miner={miner} />
        ))}
      </div>
    </section>
  );
}
