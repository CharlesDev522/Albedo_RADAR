"use client";

import { useCallback, useEffect, useState } from "react";
import { api, hippiusModelUrl, shortAddr, shortRepo, type AlbedoLiveDuel } from "@/lib/api";
import { DEFAULT_SUBNET } from "@/lib/subnets";

const POLL_MS = 8_000;

function fmtElapsed(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}

function participantLabel(p: AlbedoLiveDuel["challenger"]): string {
  if (!p) return "—";
  return shortRepo(p.repo ?? p.model_name ?? p.namespace ?? "unknown", 32);
}

export default function LiveDuelBanner() {
  const [live, setLive] = useState<AlbedoLiveDuel | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getAlbedoLiveDuel(DEFAULT_SUBNET);
      setLive(data);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  if (!live?.is_active) return null;

  const challenger = live.challenger;
  const king = live.king;
  const progress = live.progress_pct;
  const hasProgress = progress != null && live.sample_count != null;

  return (
    <div className="border-b border-sky-500/30 bg-gradient-to-r from-sky-500/10 via-zinc-950 to-violet-500/10">
      <div className="max-w-[1400px] mx-auto px-3 py-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-sky-400/40 bg-sky-500/15 text-sky-200 text-[10px] font-semibold shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-sky-300 animate-pulse" />
              LIVE DUEL
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-zinc-100">{live.phase_label}</p>
              <p className="text-[9px] text-zinc-500">
                {live.pipeline_stage && `${live.pipeline_stage} · `}
                {live.elapsed_seconds != null && `${fmtElapsed(live.elapsed_seconds)} elapsed`}
                {live.eval_queue_depth > 0 && ` · ${live.eval_queue_depth} in queue`}
              </p>
            </div>
          </div>
          <a
            href={live.dashboard_url}
            target="_blank"
            rel="noreferrer"
            className="text-[9px] text-sky-400 hover:underline shrink-0"
          >
            Hippius dashboard ↗
          </a>
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-emerald-400 font-medium shrink-0">CH</span>
            {challenger?.model_uri ? (
              <a
                href={hippiusModelUrl(challenger.model_uri.split("@")[0])}
                target="_blank"
                rel="noreferrer"
                className="text-sky-300 hover:underline truncate max-w-[200px]"
              >
                {participantLabel(challenger)}
              </a>
            ) : (
              <span className="text-zinc-400">{participantLabel(challenger)}</span>
            )}
            {challenger?.uid != null && (
              <span className="text-zinc-600 mono">uid {challenger.uid}</span>
            )}
          </div>
          <span className="text-zinc-600">vs</span>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-amber-400 font-medium shrink-0">KING</span>
            {king?.model_uri ? (
              <a
                href={hippiusModelUrl(king.model_uri.split("@")[0])}
                target="_blank"
                rel="noreferrer"
                className="text-amber-200/90 hover:underline truncate max-w-[200px]"
              >
                {participantLabel(king)}
              </a>
            ) : (
              <span className="text-zinc-400">{participantLabel(king)}</span>
            )}
            {king?.king_version != null && (
              <span className="text-amber-500/80 mono">v{king.king_version}</span>
            )}
          </div>
        </div>

        {hasProgress && (
          <div className="mt-2">
            <div className="flex justify-between text-[9px] text-zinc-500 mb-0.5">
              <span>Sample progress</span>
              <span className="mono">
                {live.generated_sample_count}/{live.sample_count} · {progress.toFixed(0)}%
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-zinc-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-sky-400 transition-all duration-500"
                style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
              />
            </div>
          </div>
        )}

        {live.eval_run_id && (
          <p className="mt-1.5 text-[9px] text-zinc-600 mono truncate">
            eval {live.eval_run_id}
            {live.submission_id && ` · sub ${live.submission_id.slice(0, 8)}…`}
          </p>
        )}
      </div>
    </div>
  );
}
