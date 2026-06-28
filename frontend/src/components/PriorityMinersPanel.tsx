"use client";

import {
  hfModelUrl,
  hippiusModelUrl,
  shortHash,
  shortRepo,
  type PriorityMinerRepoStatus,
  type PriorityMinerStatus,
} from "@/lib/api";

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function hostCell(
  label: string,
  tracked: boolean,
  pending: boolean,
  exists: boolean,
  digest: string | null | undefined,
  updatedAt: string | null | undefined,
  message: string | null | undefined,
  url: string
) {
  if (!tracked) {
    return (
      <td className="py-1.5 px-1 text-[9px] text-zinc-600">
        <span className="text-zinc-700">not polled</span>
      </td>
    );
  }
  if (pending || !exists) {
    return (
      <td className="py-1.5 px-1 text-[9px] text-zinc-500">
        <span className="text-amber-400/90">{label}</span> · no public repo
      </td>
    );
  }
  return (
    <td className="py-1.5 px-1 text-[9px]">
      <a href={url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline block truncate max-w-[140px]">
        {shortHash(digest ?? "")}
      </a>
      <p className="text-zinc-600 mt-0.5 truncate max-w-[160px]" title={message ?? undefined}>
        {message ? message.slice(0, 42) : fmtTime(updatedAt)}
      </p>
    </td>
  );
}

function RepoRow({ repo }: { repo: PriorityMinerRepoStatus }) {
  return (
    <tr className="border-b border-zinc-800/50 align-top">
      <td className="py-1.5 pr-2">
        <p className="text-zinc-200 truncate max-w-[180px]" title={repo.repo}>
          {shortRepo(repo.repo, 32)}
        </p>
        {repo.last_event_type && (
          <p className="text-[8px] text-violet-300 mt-0.5">
            {repo.last_event_type.replace(/_/g, " ")} · {fmtTime(repo.last_event_at)}
          </p>
        )}
      </td>
      {hostCell(
        "hippius",
        repo.hippius_tracked,
        repo.hippius_pending,
        !repo.hippius_pending,
        repo.hippius_digest,
        repo.hippius_updated_at,
        repo.hippius_commit_message,
        hippiusModelUrl(repo.repo)
      )}
      {hostCell(
        "HF",
        repo.huggingface_tracked,
        repo.huggingface_pending,
        repo.huggingface_exists,
        repo.huggingface_digest,
        repo.huggingface_updated_at,
        repo.huggingface_commit_message,
        hfModelUrl(repo.repo)
      )}
    </tr>
  );
}

export default function PriorityMinersPanel({
  miners,
  loading,
}: {
  miners: PriorityMinerStatus[];
  loading?: boolean;
}) {
  if (loading && !miners.length) {
    return (
      <section className="panel px-3 py-2 text-[10px] text-zinc-500">
        Loading priority miner tracking…
      </section>
    );
  }
  if (!miners.length) {
    return null;
  }

  return (
    <section className="panel px-3 py-2 space-y-3">
      <div>
        <h3 className="text-[11px] font-semibold text-zinc-200">Priority miners — dual hub watch</h3>
        <p className="text-[9px] text-zinc-600 mt-0.5">
          cyantest · booksome · divinequest — every Albedo repo from duels polled on Hippius and Hugging Face
          (HF probed even when not public yet). Updates every 60s.
        </p>
      </div>

      {miners.map((miner) => (
        <div key={miner.namespace} className="rounded border border-zinc-800/80 bg-zinc-950/30">
          <div className="flex flex-wrap items-center justify-between gap-2 px-2 py-1.5 border-b border-zinc-800/60">
            <p className="text-[11px] font-medium text-zinc-100">{miner.namespace}</p>
            <div className="flex flex-wrap gap-2 text-[9px] text-zinc-500">
              <span>{miner.discovered_repos} repos</span>
              <span className="text-sky-300">{miner.hippius_tracked_count} hippius live</span>
              <span className="text-orange-300">{miner.huggingface_tracked_count} HF live</span>
              <span className="text-violet-300">{miner.updates_24h} updates 24h</span>
              {miner.last_activity_at && <span>last {fmtTime(miner.last_activity_at)}</span>}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800/50">
                  <th className="text-left py-1 px-2">Repo</th>
                  <th className="text-left py-1 px-1">Hippius</th>
                  <th className="text-left py-1 px-1">Hugging Face</th>
                </tr>
              </thead>
              <tbody>
                {miner.repos.slice(0, 12).map((repo) => (
                  <RepoRow key={repo.repo} repo={repo} />
                ))}
              </tbody>
            </table>
          </div>
          {miner.repos.length > 12 && (
            <p className="text-[9px] text-zinc-600 px-2 py-1">
              +{miner.repos.length - 12} more repos — search tracked repos table below
            </p>
          )}
        </div>
      ))}
    </section>
  );
}
