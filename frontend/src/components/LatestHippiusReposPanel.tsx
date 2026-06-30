"use client";

import { shortHash, shortRepo, type HippiusLatestRepo } from "@/lib/api";
import { ModelFamilyBadge } from "@/components/ModelFamilyBadge";

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

export default function LatestHippiusReposPanel({
  repos,
  loading,
  totalHint,
}: {
  repos: HippiusLatestRepo[];
  loading?: boolean;
  totalHint?: number | null;
}) {
  return (
    <section className="panel px-3 py-2.5 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[12px] font-semibold text-zinc-100">Latest on Hippius Hub</h3>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Live from{" "}
            <a
              href="https://hub.hippius.com/models?q=albedo"
              target="_blank"
              rel="noreferrer"
              className="text-sky-400/90 hover:underline"
            >
              hub.hippius.com?q=albedo
            </a>
            {totalHint != null && totalHint > 0 ? ` · ${totalHint}+ indexed Albedo repos` : ""}
          </p>
        </div>
        <span className="text-[9px] text-zinc-600">newest 10 by index time</span>
      </div>

      {loading && repos.length === 0 ? (
        <p className="text-[10px] text-zinc-500 py-2">Loading Hippius Hub index…</p>
      ) : repos.length === 0 ? (
        <p className="text-[10px] text-zinc-500 py-2">
          No Albedo repos returned from Hippius Hub API — check network or try sync registries.
        </p>
      ) : (
        <div className="grid gap-1.5 sm:grid-cols-2">
          {repos.map((repo, i) => (
            <a
              key={repo.repo}
              href={repo.hub_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-start gap-2 rounded-md border border-zinc-800/90 bg-zinc-900/40 px-2.5 py-2 hover:border-sky-500/30 hover:bg-zinc-900/70 transition-colors"
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
