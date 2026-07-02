"use client";

import { hippiusModelUrl, shortAddr, shortRepo, type AlbedoEvalQueueOverview } from "@/lib/api";

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function modelLink(modelUri: string | null | undefined): string | null {
  if (!modelUri) return null;
  return hippiusModelUrl(modelUri.split("@")[0]);
}

function repoLabel(
  p: { repo?: string | null; namespace?: string | null; model_name?: string | null }
): string {
  return shortRepo(p.repo ?? `${p.namespace ?? ""}/${p.model_name ?? ""}`.replace(/^\//, ""), 28);
}

function ParticipantRow({
  p,
  showPosition,
}: {
  p: AlbedoEvalQueueOverview["queue"][number];
  showPosition?: boolean;
}) {
  const url = modelLink(p.model_uri);
  return (
    <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
      {showPosition && (
        <td className="py-1 pr-2 mono text-zinc-500 w-8">{p.position ?? "—"}</td>
      )}
      <td className="py-1 pr-2">
        {url ? (
          <a href={url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline truncate block max-w-[160px]">
            {repoLabel(p)}
          </a>
        ) : (
          <span className="text-zinc-300 truncate block max-w-[160px]">{repoLabel(p)}</span>
        )}
        <span className="text-[9px] text-zinc-600">uid {p.uid ?? "—"}</span>
      </td>
      <td className="py-1 pr-2 mono text-zinc-500">{shortAddr(p.hotkey ?? "", 4)}</td>
      <td className="py-1 pr-2 text-zinc-500">{p.state ?? "—"}</td>
      {p.commit_block != null && (
        <td className="py-1 mono text-zinc-600 text-right">{p.commit_block.toLocaleString()}</td>
      )}
    </tr>
  );
}

function PipelineColumn({
  bucket,
}: {
  bucket: AlbedoEvalQueueOverview["pipeline"][number];
}) {
  const hasWork = bucket.running_count > 0 || bucket.queued_count > 0;
  return (
    <div className={`rounded-lg border p-2.5 min-w-0 ${hasWork ? "border-sky-500/30 bg-sky-500/5" : "border-zinc-800 bg-zinc-900/40"}`}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <h4 className="text-[11px] font-semibold text-zinc-200">{bucket.label}</h4>
        <span className="text-[9px] mono text-zinc-500">
          {bucket.running_count} run · {bucket.queued_count} q
        </span>
      </div>

      {bucket.running.length > 0 && (
        <div className="mb-2">
          <p className="text-[9px] uppercase tracking-wide text-emerald-400/90 mb-1">Running</p>
          <ul className="space-y-1">
            {bucket.running.map((p, i) => {
              const url = modelLink(p.model_uri);
              return (
                <li key={`${p.submission_id ?? p.uid ?? i}-run`} className="text-[10px] rounded border border-emerald-500/20 bg-emerald-500/5 px-2 py-1">
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline truncate block">
                      {repoLabel(p)}
                    </a>
                  ) : (
                    <span className="text-zinc-300 truncate block">{repoLabel(p)}</span>
                  )}
                  <span className="text-[9px] text-zinc-600">
                    uid {p.uid ?? "—"}
                    {p.state ? ` · ${p.state}` : ""}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {bucket.queued.length > 0 && (
        <div>
          <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-1">Queued</p>
          <ul className="space-y-1 max-h-28 overflow-y-auto">
            {bucket.queued.map((p, i) => {
              const url = modelLink(p.model_uri);
              return (
                <li key={`${p.submission_id ?? p.uid ?? i}-q`} className="text-[10px] text-zinc-400 truncate">
                  <span className="mono text-zinc-600 mr-1">#{p.position ?? i + 1}</span>
                  {url ? (
                    <a href={url} target="_blank" rel="noreferrer" className="text-zinc-300 hover:text-sky-300">
                      {repoLabel(p)}
                    </a>
                  ) : (
                    repoLabel(p)
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {!bucket.running.length && !bucket.queued.length && (
        <p className="text-[10px] text-zinc-600">Idle</p>
      )}
    </div>
  );
}

export default function AlbedoEvalQueueOverviewPanel({
  data,
  compact = false,
}: {
  data: AlbedoEvalQueueOverview;
  compact?: boolean;
}) {
  const evalProgress =
    data.current_eval?.sample_count != null &&
    data.current_eval.sample_count > 0 &&
    data.current_eval.generated_sample_count != null
      ? Math.round(
          (data.current_eval.generated_sample_count / data.current_eval.sample_count) * 100
        )
      : null;

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2.5">
        <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
          <div>
            <h3 className="text-[11px] font-semibold text-zinc-200">On-chain eval pipeline</h3>
            <p className="text-[9px] text-zinc-600 mt-0.5">
              Hippius validate → pre-eval → eval · updated {fmtTime(data.updated_at)}
            </p>
          </div>
          <div className="flex gap-2 text-[10px]">
            <span className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-400">
              wait list <span className="mono text-zinc-200">{data.queue_length}</span>
            </span>
            {data.fail_count > 0 && (
              <span className="rounded border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-rose-300">
                DQ <span className="mono">{data.fail_count}</span>
              </span>
            )}
          </div>
        </div>

        {data.current_eval && (
          <div className="mb-3 rounded border border-sky-500/25 bg-sky-500/5 px-2.5 py-2 text-[10px]">
            <p className="text-sky-200 font-medium">
              Active eval · {data.current_eval.state}
              {evalProgress != null && <span className="text-zinc-400 font-normal"> · {evalProgress}% samples</span>}
            </p>
            <p className="text-zinc-500 mt-0.5 truncate">
              {repoLabel(data.current_eval)} · uid {data.current_eval.uid}
            </p>
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-2">
          {data.pipeline.map((bucket) => (
            <PipelineColumn key={bucket.stage} bucket={bucket} />
          ))}
        </div>
      </section>

      {!compact && (
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-1">Eval wait queue</h3>
          <p className="text-[9px] text-zinc-600 mb-2">
            Miners waiting for an Albedo eval slot (dashboard queue)
          </p>
          {data.queue.length === 0 ? (
            <p className="text-[10px] text-zinc-500">No miners in the wait queue.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] min-w-[480px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-1 pr-2 w-8">#</th>
                    <th className="text-left py-1 pr-2">Model</th>
                    <th className="text-left py-1 pr-2">Hotkey</th>
                    <th className="text-left py-1 pr-2">State</th>
                    <th className="text-right py-1">Commit block</th>
                  </tr>
                </thead>
                <tbody>
                  {data.queue.map((p) => (
                    <ParticipantRow key={`${p.uid}-${p.position}`} p={p} showPosition />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
