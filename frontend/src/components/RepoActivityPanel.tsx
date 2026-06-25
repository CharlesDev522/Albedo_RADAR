"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  hippiusModelUrl,
  shortAddr,
  shortHash,
  shortRepo,
  type RepoActivityEvent,
  type RepoActivityOverview,
  type RepoTrackEntry,
} from "@/lib/api";
import { ModelFamilyBadge } from "@/components/ModelFamilyBadge";
import { inferAlbedoModelFamily } from "@/lib/modelFamily";
import { getSubnetProfile } from "@/lib/subnets";
import { useSubnet } from "@/lib/useSubnet";

const POLL_MS = 30_000;

type FamilyFilter = "all" | "qwen3.6-35b" | "qwen3-4b";

function fmtBytes(n: number | null | undefined): string {
  if (n == null || n <= 0) return "—";
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${(n / 1e3).toFixed(0)} KB`;
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function eventLabel(type: string): string {
  switch (type) {
    case "hub_manifest_update":
      return "hub update";
    case "on_chain_commit":
      return "on-chain commit";
    case "digest_mismatch":
      return "digest mismatch";
    default:
      return type;
  }
}

function eventColor(type: string): string {
  switch (type) {
    case "hub_manifest_update":
      return "text-sky-300 border-sky-500/30 bg-sky-500/10";
    case "on_chain_commit":
      return "text-lime-300 border-lime-500/30 bg-lime-500/10";
    case "digest_mismatch":
      return "text-rose-300 border-rose-500/30 bg-rose-500/10";
    default:
      return "text-zinc-400 border-zinc-600 bg-zinc-800/30";
  }
}

export default function RepoActivityPanel() {
  const { subnet } = useSubnet();
  const profile = getSubnetProfile(subnet);
  const [overview, setOverview] = useState<RepoActivityOverview | null>(null);
  const [tracks, setTracks] = useState<RepoTrackEntry[]>([]);
  const [feed, setFeed] = useState<RepoActivityEvent[]>([]);
  const [family, setFamily] = useState<FamilyFilter>("qwen3.6-35b");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedRepo, setExpandedRepo] = useState<string | null>(null);

  const familyParam = family === "all" ? undefined : family;

  const refresh = useCallback(async () => {
    try {
      const [ov, tr, fd] = await Promise.all([
        api.getRepoActivityOverview(subnet),
        api.getRepoTracks(subnet, familyParam),
        api.getRepoActivityFeed(subnet, { family: familyParam, limit: 60 }),
      ]);
      setOverview(ov);
      setTracks(tr);
      setFeed(fd);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load repo activity");
    } finally {
      setLoading(false);
    }
  }, [subnet, familyParam]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const qwen36Tracks = useMemo(
    () => tracks.filter((t) => t.model_family === "qwen3.6-35b"),
    [tracks]
  );

  return (
    <div className="space-y-3">
      <div className="panel px-3 py-2">
        <h2 className="text-[12px] font-semibold text-zinc-100">Hippius repo tracker</h2>
        <p className="text-[10px] text-zinc-500 mt-0.5">
          Tracks published miner repos on Hippius Hub ({profile.name} SN{subnet}) — manifest changes,
          on-chain commits, and digest sync status. Focus: Qwen3.6-35B competition repos.
        </p>
      </div>

      {error && (
        <div className="panel px-3 py-2 border-rose-500/20 bg-rose-500/5 text-[10px] text-rose-300">
          {error}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(["qwen3.6-35b", "qwen3-4b", "all"] as FamilyFilter[]).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFamily(f)}
            className={`px-2 py-0.5 rounded text-[10px] border transition-colors ${
              family === f
                ? f === "qwen3.6-35b"
                  ? "border-sky-500/40 bg-sky-500/10 text-sky-200"
                  : f === "qwen3-4b"
                    ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                    : "border-zinc-500/40 bg-zinc-800/40 text-zinc-200"
                : "border-zinc-800 text-zinc-500 hover:border-zinc-700"
            }`}
          >
            {f === "all" ? "all families" : f === "qwen3.6-35b" ? "Qwen3.6-35B" : "Qwen3-4B"}
          </button>
        ))}
        <span className="text-[9px] text-zinc-600 ml-auto">
          {loading ? "loading…" : `poll ${POLL_MS / 1000}s · last ${fmtTime(overview?.last_poll_at)}`}
        </span>
      </div>

      {overview && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          <Kpi label="tracked" value={String(overview.tracked_repos)} />
          <Kpi label="Qwen3.6-35B" value={String(overview.qwen36_35b_repos)} accent="text-sky-400" />
          <Kpi label="Qwen3-4B" value={String(overview.qwen3_4b_repos)} accent="text-amber-400" />
          <Kpi label="in sync" value={String(overview.in_sync_count)} accent="text-lime-400" />
          <Kpi label="mismatch" value={String(overview.mismatch_count)} warn={overview.mismatch_count > 0} />
          <Kpi label="hub 24h" value={String(overview.hub_updates_24h)} accent="text-sky-300" />
          <Kpi label="chain 24h" value={String(overview.on_chain_events_24h)} accent="text-lime-300" />
          <Kpi label="shown" value={String(tracks.length)} small />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        <section className="panel xl:col-span-5">
          <div className="panel-head">
            <h3 className="text-[11px] font-semibold text-zinc-100">Activity feed</h3>
            <span className="text-[9px] text-zinc-600">{feed.length} events</span>
          </div>
          <div className="scroll-pane max-h-[420px] overflow-y-auto divide-y divide-zinc-800/50">
            {feed.length === 0 ? (
              <p className="px-3 py-6 text-[10px] text-zinc-500 text-center">
                {loading ? "loading activity…" : "no repo activity yet — collector polls Hippius every ~2 min"}
              </p>
            ) : (
              feed.map((e) => (
                <div key={e.id} className="px-3 py-2 hover:bg-zinc-800/20">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex px-1.5 py-px rounded border text-[9px] ${eventColor(e.event_type)}`}>
                      {eventLabel(e.event_type)}
                    </span>
                    <span className="text-[9px] text-zinc-600">{fmtTime(e.detected_at)}</span>
                  </div>
                  <p className="text-[10px] text-zinc-300 mt-1">
                    uid {e.uid ?? "—"}{" "}
                    <span className="mono text-zinc-500">{e.hotkey ? shortAddr(e.hotkey, 5) : ""}</span>
                  </p>
                  <a
                    href={hippiusModelUrl(e.repo)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-sky-400/90 hover:underline truncate block mt-0.5"
                  >
                    {shortRepo(e.repo, 42)}
                  </a>
                  {e.model_family && (
                    <div className="mt-1">
                      <ModelFamilyBadge repo={e.repo} family={e.model_family} />
                    </div>
                  )}
                  {e.commit_message && (
                    <p className="text-[9px] text-zinc-500 mt-1 truncate" title={e.commit_message}>
                      {e.commit_message}
                    </p>
                  )}
                  {(e.chain_digest || e.hub_digest) && (
                    <p className="text-[9px] mono text-zinc-600 mt-1">
                      {e.chain_digest && <>chain {shortHash(e.chain_digest)} </>}
                      {e.hub_digest && <>hub {shortHash(e.hub_digest)}</>}
                    </p>
                  )}
                  {e.changed_files.length > 0 && (
                    <p className="text-[9px] text-zinc-500 mt-1">
                      {e.changed_files.length} file change{e.changed_files.length !== 1 ? "s" : ""}
                      {e.changed_files.slice(0, 3).map((f) => (
                        <span key={f.name} className="ml-1 text-zinc-600">
                          {f.change}:{f.name}
                        </span>
                      ))}
                    </p>
                  )}
                </div>
              ))
            )}
          </div>
        </section>

        <section className="panel xl:col-span-7">
          <div className="panel-head flex-wrap gap-2">
            <div>
              <h3 className="text-[11px] font-semibold text-zinc-100">Tracked miner repos</h3>
              <p className="text-[10px] text-zinc-500">
                {family === "qwen3.6-35b"
                  ? `${qwen36Tracks.length} Qwen3.6-35B repos · chain vs Hippius main digest`
                  : "on-chain published repos polled on Hippius registry"}
              </p>
            </div>
          </div>
          <div className="scroll-pane overflow-x-auto max-h-[420px] overflow-y-auto">
            <table className="tbl">
              <thead className="sticky top-0 z-10 bg-zinc-950">
                <tr>
                  <th>uid</th>
                  <th>repo</th>
                  <th>era</th>
                  <th>sync</th>
                  <th>files</th>
                  <th>hub updated</th>
                  <th>chain digest</th>
                  <th>hub digest</th>
                </tr>
              </thead>
              <tbody>
                {tracks.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center text-zinc-500 py-8 text-[10px]">
                      {loading ? "loading repos…" : "no tracked repos for this filter"}
                    </td>
                  </tr>
                ) : (
                  tracks.map((t) => {
                    const expanded = expandedRepo === t.repo;
                    return (
                      <Fragment key={t.id}>
                        <tr
                          className="cursor-pointer"
                          onClick={() => setExpandedRepo(expanded ? null : t.repo)}
                        >
                          <td className="mono text-zinc-200">{t.uid ?? "—"}</td>
                          <td className="max-w-[160px]">
                            <a
                              href={hippiusModelUrl(t.repo, t.hub_revision)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sky-400/90 hover:underline text-[10px] truncate block"
                              onClick={(ev) => ev.stopPropagation()}
                            >
                              {shortRepo(t.repo)}
                            </a>
                          </td>
                          <td>
                            <ModelFamilyBadge
                              repo={t.repo}
                              family={t.model_family ?? inferAlbedoModelFamily(t.repo)}
                            />
                          </td>
                          <td>
                            {t.digest_in_sync === true && (
                              <span className="text-lime-400 text-[9px]">synced</span>
                            )}
                            {t.digest_in_sync === false && (
                              <span className="text-rose-400 text-[9px]">mismatch</span>
                            )}
                            {t.digest_in_sync == null && <span className="text-zinc-600 text-[9px]">—</span>}
                          </td>
                          <td className="mono text-[10px] text-zinc-500 tabular-nums">
                            {t.file_count ?? "—"}
                            <span className="text-zinc-700 ml-1">{fmtBytes(t.total_bytes)}</span>
                          </td>
                          <td className="text-[10px] text-zinc-500">{fmtTime(t.hub_updated_at)}</td>
                          <td className="mono text-[9px] text-zinc-600">
                            {t.chain_digest ? `${shortHash(t.chain_digest)}…` : "—"}
                          </td>
                          <td className="mono text-[9px] text-zinc-600">
                            {t.hub_digest ? `${shortHash(t.hub_digest)}…` : "—"}
                          </td>
                        </tr>
                        {expanded && t.hub_commit_message && (
                          <tr className="bg-zinc-900/40">
                            <td colSpan={8} className="text-[10px] text-zinc-500 py-2">
                              <span className="text-zinc-400">last hub message:</span> {t.hub_commit_message}
                              {t.coldkey && (
                                <span className="ml-3 mono text-zinc-600">coldkey {shortAddr(t.coldkey, 4)}</span>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  accent,
  warn,
  small,
}: {
  label: string;
  value: string;
  accent?: string;
  warn?: boolean;
  small?: boolean;
}) {
  return (
    <div className="panel px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wider text-zinc-600">{label}</p>
      <p
        className={`${small ? "text-[11px]" : "text-[13px]"} font-medium tabular-nums ${
          warn ? "text-rose-400" : accent ?? "text-zinc-200"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
