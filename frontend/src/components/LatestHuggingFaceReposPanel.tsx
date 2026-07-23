"use client";

import { useMemo } from "react";
import { shortHash, shortRepo, type HuggingFaceLatestRepo } from "@/lib/api";
import { ModelFamilyBadge } from "@/components/ModelFamilyBadge";
import {
  HF_DEFAULT_TAG_OPTIONS,
  HF_SORT_OPTIONS,
  hfSortLabel,
  hfSortMetricLabel,
  toggleTagSelection,
  type HfSortKey,
} from "@/lib/hfSearchOptions";

function hfRepoTimeMs(iso: string | null | undefined): number {
  if (!iso) return 0;
  const ms = new Date(iso).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

function sortHfRepos(repos: HuggingFaceLatestRepo[], sort: HfSortKey): HuggingFaceLatestRepo[] {
  return [...repos].sort((a, b) => {
    if (sort === "downloads" || sort === "likes") {
      const am = sort === "downloads" ? a.downloads ?? 0 : a.likes ?? 0;
      const bm = sort === "downloads" ? b.downloads ?? 0 : b.likes ?? 0;
      if (bm !== am) return bm - am;
      return a.repo.localeCompare(b.repo);
    }
    const am = hfRepoTimeMs(a.indexed_at);
    const bm = hfRepoTimeMs(b.indexed_at);
    const aHas = am > 0 ? 0 : 1;
    const bHas = bm > 0 ? 0 : 1;
    if (aHas !== bHas) return aHas - bHas;
    if (bm !== am) return bm - am;
    return a.repo.localeCompare(b.repo);
  });
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const diffMin = Math.round((Date.now() - d.getTime()) / 60_000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 24 * 60) return `${Math.floor(diffMin / 60)}h ago`;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function trackBadge(repo: HuggingFaceLatestRepo): { label: string; className: string } | null {
  if (!repo.is_tracked) {
    return { label: "not tracked", className: "text-zinc-500 border-zinc-700 bg-zinc-900/40" };
  }
  if (repo.pending_hub_poll) {
    return { label: "tracked · pending poll", className: "text-amber-300 border-amber-500/30 bg-amber-500/10" };
  }
  if (repo.digest_in_sync === true) {
    return { label: "tracked · synced", className: "text-lime-300 border-lime-500/30 bg-lime-500/10" };
  }
  if (repo.digest_in_sync === false) {
    return { label: "tracked · mismatch", className: "text-rose-300 border-rose-500/30 bg-rose-500/10" };
  }
  return { label: "tracked", className: "text-violet-300 border-violet-500/30 bg-violet-500/10" };
}

export default function LatestHuggingFaceReposPanel({
  repos,
  loading,
  totalHint,
  error,
  sort,
  selectedTags,
  hubSearchUrl,
  onSortChange,
  onTagsChange,
  onSyncDiscoveries,
  syncing,
}: {
  repos: HuggingFaceLatestRepo[];
  loading?: boolean;
  totalHint?: number | null;
  error?: string | null;
  sort: HfSortKey;
  selectedTags: string[];
  hubSearchUrl?: string | null;
  onSortChange: (sort: HfSortKey) => void;
  onTagsChange: (tags: string[]) => void;
  onSyncDiscoveries?: () => void;
  syncing?: boolean;
}) {
  const sortedRepos = useMemo(() => sortHfRepos(repos, sort), [repos, sort]);
  const trackedCount = sortedRepos.filter((repo) => repo.is_tracked).length;
  const untrackedCount = sortedRepos.length - trackedCount;

  return (
    <section className="panel px-3 py-2.5 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-[12px] font-semibold text-zinc-100">Latest on Hugging Face</h3>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Live from{" "}
            <a
              href={hubSearchUrl ?? "https://huggingface.co/models?search=albedo-qwen3.6-35b&sort=createdAt&direction=-1"}
              target="_blank"
              rel="noreferrer"
              className="text-orange-400/90 hover:underline"
            >
              huggingface.co (Albedo search)
            </a>
            {totalHint != null && totalHint > 0 ? ` · ${totalHint}+ matching repos` : ""}
            {sortedRepos.length > 0 ? ` · ${trackedCount} tracked · ${untrackedCount} new` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <select
            value={sort}
            onChange={(e) => onSortChange(e.target.value as HfSortKey)}
            aria-label="Sort Hugging Face repos"
            className="px-2 py-1 rounded text-[10px] border border-zinc-800 bg-zinc-950/80 text-zinc-300 focus:outline-none focus:border-orange-500/40"
          >
            {HF_SORT_OPTIONS.map((opt) => (
              <option key={opt.key} value={opt.key}>
                {opt.label}
              </option>
            ))}
          </select>
          {onSyncDiscoveries && (
            <button
              type="button"
              onClick={onSyncDiscoveries}
              disabled={syncing}
              className="px-2 py-1 rounded text-[10px] border border-zinc-700 text-zinc-300 hover:border-orange-500/40 hover:text-orange-200 disabled:opacity-50"
            >
              {syncing ? "syncing…" : "sync discoveries"}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[9px] text-zinc-600">tags (all required):</span>
        {HF_DEFAULT_TAG_OPTIONS.map((tag) => {
          const active = selectedTags.some((t) => t.toLowerCase() === tag.toLowerCase());
          return (
            <button
              key={tag}
              type="button"
              onClick={() => onTagsChange(toggleTagSelection(selectedTags, tag))}
              className={`px-1.5 py-0.5 rounded text-[9px] border transition-colors ${
                active
                  ? "border-orange-500/40 bg-orange-500/10 text-orange-200"
                  : "border-zinc-800 text-zinc-500 hover:border-zinc-700"
              }`}
            >
              {tag}
            </button>
          );
        })}
        {selectedTags.length > 0 && (
          <button
            type="button"
            onClick={() => onTagsChange([])}
            className="px-1.5 py-0.5 rounded text-[9px] border border-zinc-800 text-zinc-500 hover:border-zinc-700"
          >
            clear tags
          </button>
        )}
        <span className="text-[9px] text-zinc-600 ml-auto">
          top 10 by {hfSortMetricLabel(sort)}
        </span>
      </div>

      {error ? (
        <p className="text-[10px] text-amber-300/90 py-2">
          Hugging Face Hub search unavailable ({error}). Tracked repos and feed still load from DB.
        </p>
      ) : loading && repos.length === 0 ? (
        <p className="text-[10px] text-zinc-500 py-2">Searching Hugging Face Hub…</p>
      ) : repos.length === 0 ? (
        <p className="text-[10px] text-zinc-500 py-2">
          No Albedo repos match {hfSortLabel(sort)}
          {selectedTags.length > 0 ? ` with tags ${selectedTags.join(", ")}` : ""} — try fewer tags or sync
          registries.
        </p>
      ) : (
        <div className="grid gap-1.5 sm:grid-cols-2">
          {sortedRepos.map((repo, i) => {
            const badge = trackBadge(repo);
            return (
              <a
                key={repo.repo}
                href={repo.hub_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-start gap-2 rounded-md border border-zinc-800/90 bg-zinc-900/40 px-2.5 py-2 hover:border-orange-500/30 hover:bg-zinc-900/70 transition-colors"
              >
                <span className="text-[9px] mono text-zinc-600 w-4 shrink-0 pt-0.5">#{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-medium text-zinc-100 truncate">{shortRepo(repo.repo, 40)}</p>
                  <div className="flex flex-wrap items-center gap-2 mt-1">
                    <ModelFamilyBadge repo={repo.repo} family={repo.model_family} />
                    {badge && (
                      <span className={`inline-flex px-1 py-px rounded border text-[8px] ${badge.className}`}>
                        {badge.label}
                      </span>
                    )}
                    <span className="text-[9px] text-zinc-500">{fmtTime(repo.indexed_at)}</span>
                    {sort === "downloads" && repo.downloads != null && (
                      <span className="text-[9px] mono text-zinc-600">{repo.downloads} dl</span>
                    )}
                    {sort === "likes" && repo.likes != null && (
                      <span className="text-[9px] mono text-zinc-600">{repo.likes} likes</span>
                    )}
                    {repo.file_count != null && (
                      <span className="text-[9px] mono text-zinc-600">{repo.file_count} files</span>
                    )}
                  </div>
                  <p className="text-[9px] mono text-zinc-600 mt-0.5 truncate">
                  {repo.digest ? shortHash(repo.digest) : "search result · open hub for files"}
                </p>
                </div>
              </a>
            );
          })}
        </div>
      )}
    </section>
  );
}
