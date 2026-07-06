"use client";

import { useCallback, useEffect, useState } from "react";
import { api, hippiusModelUrl, shortRepo, type AlbedoLiveDuel, type AlbedoLiveDuelParticipant } from "@/lib/api";
import { DEFAULT_SUBNET } from "@/lib/subnets";
import { useSubnet } from "@/lib/useSubnet";
import { usePageVisibility } from "@/lib/usePageVisibility";

const POLL_MS = 8_000;
const POLL_BACKGROUND_MS = 30_000;

function fmtElapsed(sec: number | null | undefined): string {
  if (sec == null || !Number.isFinite(sec)) return "";
  if (sec < 60) return `${Math.round(sec)}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
  return `${Math.floor(sec / 3600)}h ${Math.floor((sec % 3600) / 60)}m`;
}

function modelUrl(p: AlbedoLiveDuelParticipant | null | undefined): string | null {
  if (!p?.model_uri) return null;
  return hippiusModelUrl(p.model_uri.split("@")[0]);
}

function repoLabel(p: AlbedoLiveDuelParticipant | null | undefined): string {
  if (!p) return "—";
  return shortRepo(p.repo ?? `${p.namespace}/${p.model_name}`, 28);
}

function FighterCard({
  role,
  tone,
  participant,
}: {
  role: string;
  tone: "challenger" | "king";
  participant: AlbedoLiveDuelParticipant | null | undefined;
}) {
  const url = modelUrl(participant);
  const styles =
    tone === "challenger"
      ? "border-emerald-500/25 bg-emerald-500/5"
      : "border-amber-500/25 bg-amber-500/5";
  const accent = tone === "challenger" ? "text-emerald-300" : "text-amber-300";

  return (
    <div className={`flex-1 min-w-[140px] rounded-lg border px-3 py-2 ${styles}`}>
      <p className={`text-[9px] font-semibold uppercase tracking-wider ${accent}`}>{role}</p>
      {url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          className="block text-[12px] font-medium text-zinc-100 hover:text-sky-300 truncate mt-1"
          title={participant?.repo ?? undefined}
        >
          {repoLabel(participant)}
        </a>
      ) : (
        <p className="text-[12px] font-medium text-zinc-300 truncate mt-1">{repoLabel(participant)}</p>
      )}
      <p className="text-[9px] text-zinc-500 mt-1 mono">
        {participant?.uid != null && `uid ${participant.uid}`}
        {participant?.king_version != null && ` · v${participant.king_version}`}
      </p>
    </div>
  );
}

export default function LiveDuelBanner() {
  const [live, setLive] = useState<AlbedoLiveDuel | null>(null);
  const { view } = useSubnet();
  const pageVisible = usePageVisibility();
  const pollMs = view === "duels" || view === "dashboard" ? POLL_MS : POLL_BACKGROUND_MS;

  const refresh = useCallback(async (forceRefresh = false) => {
    try {
      setLive(await api.getAlbedoLiveDuel(DEFAULT_SUBNET, forceRefresh));
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    if (!pageVisible) return;
    void refresh(false);
    const id = setInterval(() => void refresh(true), pollMs);
    return () => clearInterval(id);
  }, [pageVisible, pollMs, refresh]);

  if (!live?.is_active) return null;

  const elapsed = fmtElapsed(live.elapsed_seconds);

  return (
    <div className="border-b border-sky-500/20 bg-zinc-950/95 backdrop-blur-sm">
      <div className="max-w-[1400px] mx-auto px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 shrink-0">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-60" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-400" />
            </span>
            <div>
              <p className="text-[11px] font-semibold text-sky-200 leading-tight">Live duel</p>
              <p className="text-[9px] text-zinc-500 leading-tight sm:hidden">{live.phase_label}</p>
            </div>
          </div>

          <div className="hidden sm:block w-px h-8 bg-zinc-800" />

          <div className="flex flex-1 items-stretch gap-2 min-w-[280px]">
            <FighterCard role="Challenger" tone="challenger" participant={live.challenger} />
            <div className="flex items-center text-[10px] text-zinc-600 font-medium px-0.5">vs</div>
            <FighterCard role="King" tone="king" participant={live.king} />
          </div>

          <div className="flex flex-col items-end shrink-0 ml-auto min-w-[88px]">
            {elapsed ? (
              <p className="text-[22px] sm:text-[26px] font-semibold text-zinc-50 mono leading-none tracking-tight tabular-nums">
                {elapsed}
              </p>
            ) : (
              <p className="text-[14px] font-medium text-zinc-400 leading-none">In progress</p>
            )}
            <p className="text-[10px] text-sky-300/90 mt-1.5 text-right max-w-[140px] leading-snug hidden sm:block">
              {live.phase_label}
            </p>
            <div className="flex flex-wrap justify-end gap-x-2 gap-y-0.5 mt-1 text-[9px] text-zinc-500">
              {live.eval_queue_depth > 0 && <span>{live.eval_queue_depth} queued</span>}
              <a
                href={live.dashboard_url}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline"
              >
                dashboard ↗
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
