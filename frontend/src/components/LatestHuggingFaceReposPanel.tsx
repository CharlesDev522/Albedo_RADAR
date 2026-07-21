"use client";

import { useMemo } from "react";
import { shortHash, shortRepo, type HuggingFaceLatestRepo } from "@/lib/api";
import { ModelFamilyBadge } from "@/components/ModelFamilyBadge";

function hfRepoTimeMs(iso: string | null | undefined): number {
  if (!iso) return 0;
  const ms = new Date(iso).getTime();
  return Number.isFinite(ms) ? ms : 0;
}

function sortHfReposByDate(repos: HuggingFaceLatestRepo[]): HuggingFaceLatestRepo[] {
  return [...repos].sort((a, b) => {
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

export default function LatestHuggingFaceReposPanel({
  repos,
  loading,
  totalHint,
  error,
}: {
  repos: HuggingFaceLatestRepo[];
  loading?: boolean;
  totalHint?: number | null;
  error?: string | null;
}) {
  const sortedRepos = useMemo(() => sortHfReposByDate(repos), [repos]);

  return (
    <section className="panel px-3 py-2.5 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[12px] font-semibold text-zinc-100">Latest on Hugging Face</h3>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Live from{" "}
            <a
              href="https://huggingface.co/models?search=albedo-qwen3.6-35b"
              target="_blank"
              rel="noreferrer"
              className="text-orange-400/90 hover:underline"
            >
              huggingface.co (Albedo search)
            </a>
            {totalHint != null && totalHint > 0 ? ` · ${totalHint}+ matching repos` : ""}
          </p>
        </div>
        <span className="text-[9px] text-zinc-600">newest 10 by last modified</span>
      </div>

      {error ? (
        <p className="text-[10px] text-amber-300/90 py-2">
          Hugging Face Hub search unavailable ({error}). Tracked repos and feed still load from DB.
        </p>
      ) : loading && repos.length === 0 ? (
        <p className="text-[10px] text-zinc-500 py-2">Searching Hugging Face Hub…</p>
      ) : repos.length === 0 ? (
        <p className="text-[10px] text-zinc-500 py-2">
          No Albedo repos returned from Hugging Face — check network or try sync registries.
        </p>
      ) : (
        <div className="grid gap-1.5 sm:grid-cols-2">
          {sortedRepos.map((repo, i) => (
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
                  <span className="text-[9px] text-zinc-500">{fmtTime(repo.indexed_at)}</span>
                  {repo.file_count != null && (
                    <span className="text-[9px] mono text-zinc-600">{repo.file_count} files</span>
                  )}
                </div>
                <p className="text-[9px] mono text-zinc-600 mt-0.5 truncate">{shortHash(repo.digest)}</p>
              </div>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}
