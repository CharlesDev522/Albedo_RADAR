"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import LatestHippiusReposPanel from "@/components/LatestHippiusReposPanel";
import LatestHuggingFaceReposPanel from "@/components/LatestHuggingFaceReposPanel";
import GithubWatchPanel from "@/components/GithubWatchPanel";
import {
  api,
  hfModelUrl,
  hippiusModelUrl,
  modelCommitUrl,
  shortAddr,
  shortHash,
  shortRepo,
  type HippiusLatestRepo,
  type HuggingFaceLatestRepo,
  type RepoActivityEvent,
  type RepoActivityOverview,
  type RepoTrackEntry,
} from "@/lib/api";
import { ModelFamilyBadge } from "@/components/ModelFamilyBadge";
import SearchBar from "@/components/SearchBar";
import { inferAlbedoModelFamily } from "@/lib/modelFamily";
import {
  REPO_TRACK_SORT_OPTIONS,
  type RepoTrackSortKey,
  hasDefiniteRemoteTime,
  sortRepoTracks,
} from "@/lib/repoActivitySort";
import {
  isSearchActive,
  matchesRepoActivityEvent,
  matchesRepoTrack,
} from "@/lib/searchFilter";
import { useSubnet } from "@/lib/useSubnet";
import { usePageVisibility } from "@/lib/usePageVisibility";

const POLL_MS = 12_000;
const TRACKED_REPOS_PREVIEW = 10;

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

function repoUrl(entry: RepoTrackEntry): string {
  if (entry.repo_host === "huggingface") {
    return hfModelUrl(entry.repo, entry.chain_digest ?? entry.hub_digest ?? undefined);
  }
  return hippiusModelUrl(entry.repo, entry.hub_revision);
}

function eventLabel(type: string): string {
  switch (type) {
    case "hub_manifest_update":
      return "hub update";
    case "hub_repo_added":
      return "new repo";
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
    case "hub_repo_added":
      return "text-lime-300 border-lime-500/30 bg-lime-500/10";
    case "on_chain_commit":
      return "text-lime-300 border-lime-500/30 bg-lime-500/10";
    case "digest_mismatch":
      return "text-rose-300 border-rose-500/30 bg-rose-500/10";
    default:
      return "text-zinc-400 border-zinc-600 bg-zinc-800/30";
  }
}

function hostBadge(host: string): string {
  return host === "huggingface"
    ? "text-orange-300 border-orange-500/30 bg-orange-500/10"
    : "text-sky-300 border-sky-500/30 bg-sky-500/10";
}

function trackSourceLabel(source: string | null | undefined): string | null {
  switch (source) {
    case "hub_watch":
      return "hub watch";
    case "slot":
      return "slot · hub pending";
    case "hub_poll":
      return "hub polled";
    case "commitment":
      return "on-chain";
    default:
      return source ?? null;
  }
}

function trackSourceColor(source: string | null | undefined): string {
  switch (source) {
    case "hub_watch":
      return "text-violet-300 border-violet-500/30 bg-violet-500/10";
    case "slot":
      return "text-amber-300 border-amber-500/30 bg-amber-500/10";
    case "commitment":
      return "text-lime-300 border-lime-500/30 bg-lime-500/10";
    case "hub_poll":
      return "text-sky-300 border-sky-500/30 bg-sky-500/10";
    default:
      return "text-zinc-400 border-zinc-600 bg-zinc-800/30";
  }
}

export default function RepoActivityPanel() {
  const { subnet, view } = useSubnet();
  const pageVisible = usePageVisibility();
  const panelActive = view === "activity" && pageVisible;
  const [overview, setOverview] = useState<RepoActivityOverview | null>(null);
  const [hippiusLatest, setHippiusLatest] = useState<HippiusLatestRepo[]>([]);
  const [hippiusIndexTotal, setHippiusIndexTotal] = useState<number | null>(null);
  const [hippiusLatestError, setHippiusLatestError] = useState<string | null>(null);
  const [hfLatest, setHfLatest] = useState<HuggingFaceLatestRepo[]>([]);
  const [hfIndexTotal, setHfIndexTotal] = useState<number | null>(null);
  const [hfLatestError, setHfLatestError] = useState<string | null>(null);
  const [tracks, setTracks] = useState<RepoTrackEntry[]>([]);
  const [feed, setFeed] = useState<RepoActivityEvent[]>([]);
  const [family, setFamily] = useState<FamilyFilter>("all");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [expandedRepo, setExpandedRepo] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<RepoTrackSortKey>("remote_newest");
  const [showAllTracks, setShowAllTracks] = useState(false);

  const familyParam = family === "all" ? undefined : family;

  const refresh = useCallback(async (forceRefresh = false) => {
    try {
      const [ov, tr, fd] = await Promise.all([
        api.getRepoActivityOverview(subnet, forceRefresh),
        api.getRepoTracks(subnet, familyParam, undefined, forceRefresh),
        api.getRepoActivityFeed(subnet, { family: familyParam, limit: 60, forceRefresh }),
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

    try {
      const latest = await api.getHippiusLatestRepos(TRACKED_REPOS_PREVIEW, forceRefresh);
      setHippiusLatest(latest.repos);
      setHippiusIndexTotal(latest.total_indexed);
      setHippiusLatestError(null);
    } catch (e) {
      setHippiusLatest([]);
      setHippiusIndexTotal(null);
      setHippiusLatestError(
        e instanceof Error ? e.message : "Hippius Hub index unavailable"
      );
    }

    try {
      const latest = await api.getHuggingFaceLatestRepos(TRACKED_REPOS_PREVIEW, forceRefresh);
      setHfLatest(latest.repos);
      setHfIndexTotal(latest.total_indexed);
      setHfLatestError(null);
    } catch (e) {
      setHfLatest([]);
      setHfIndexTotal(null);
      setHfLatestError(e instanceof Error ? e.message : "Hugging Face Hub unavailable");
    }
  }, [subnet, familyParam]);

  const runSync = useCallback(async () => {
    setSyncing(true);
    setSyncError(null);
    try {
      const result = await api.syncRepoActivity(subnet);
      await refresh(true);
      if ((result.miners_checked as number) === 0) {
        setSyncError(
          "sync ran but found 0 qwen repos to poll — check slot scan and HF discovery"
        );
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "registry sync failed";
      setSyncError(msg);
      setError(msg);
    } finally {
      setSyncing(false);
    }
  }, [subnet, refresh]);

  useEffect(() => {
    if (!panelActive) return;
    setLoading(true);
    void refresh(false);
    const id = setInterval(() => void refresh(true), POLL_MS);
    return () => clearInterval(id);
  }, [panelActive, refresh]);

  useEffect(() => {
    setSearch("");
  }, [subnet]);

  const filteredFeed = useMemo(() => {
    if (!isSearchActive(search)) return feed;
    return feed.filter((e) => matchesRepoActivityEvent(search, e));
  }, [feed, search]);

  const filteredTracks = useMemo(() => {
    const matched = isSearchActive(search)
      ? tracks.filter((t) => matchesRepoTrack(search, t))
      : tracks;
    return sortRepoTracks(matched, sortKey);
  }, [tracks, search, sortKey]);

  const displayTracks = useMemo(() => {
    if (showAllTracks || isSearchActive(search)) return filteredTracks;
    return filteredTracks.slice(0, TRACKED_REPOS_PREVIEW);
  }, [filteredTracks, showAllTracks, search]);

  const searchActive = isSearchActive(search);

  return (
    <div className="space-y-3">
      <GithubWatchPanel active={panelActive} />
      <div className="panel px-3 py-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">Model repo activity</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5 max-w-2xl">
            Hub-first tracking: Qwen3.6-35B / Qwen3-4B repos from Hippius Hub index
            (hub.hippius.com?q=albedo), chain slots, and HF discovery — polled on
            Hippius/HF in near real-time.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void runSync()}
          disabled={syncing}
          className="px-2 py-1 rounded text-[10px] border border-zinc-700 text-zinc-300 hover:border-sky-500/40 hover:text-sky-200 disabled:opacity-50"
        >
          {syncing ? "syncing…" : "sync registries"}
        </button>
      </div>

      {syncError && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[10px] text-amber-300">
          Registry sync: {syncError}
        </div>
      )}

      {error && (
        <div className="panel px-3 py-2 border-rose-500/20 bg-rose-500/5 text-[10px] text-rose-300">
          {error}
        </div>
      )}

      {overview && overview.tracked_miners === 0 && !loading && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[10px] text-amber-300">
          No Qwen repos found yet from slot scan or hub discovery. Ensure the collector is running
          (<code className="mono">docker compose logs collector --tail 30</code>) and click sync
          registries.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder="Search uid, hotkey, repo, digest, host…"
          resultCount={searchActive ? filteredTracks.length : undefined}
          totalCount={searchActive ? tracks.length : undefined}
          className="w-full sm:w-auto sm:flex-1"
        />
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as RepoTrackSortKey)}
          aria-label="Sort repos"
          className="px-2 py-1 rounded text-[10px] border border-zinc-800 bg-zinc-950/80 text-zinc-300 focus:outline-none focus:border-zinc-600"
        >
          {REPO_TRACK_SORT_OPTIONS.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {(["all", "qwen3.6-35b", "qwen3-4b"] as FamilyFilter[]).map((f) => (
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
            {f === "all" ? "all miners" : f === "qwen3.6-35b" ? "Qwen3.6-35B" : "Qwen3-4B"}
          </button>
        ))}
        <span className="text-[9px] text-zinc-600 ml-auto">
          {loading
            ? "loading…"
            : `${searchActive ? `${filteredTracks.length}/${tracks.length} repos` : `${tracks.length} repos`} · refresh ${POLL_MS / 1000}s · hub poll ${fmtTime(overview?.last_poll_at)}`}
        </span>
      </div>

      {overview && overview.tracked_miners > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 xl:grid-cols-12 gap-2">
          <Kpi label="repos tracked" value={String(overview.tracked_miners)} />
          <Kpi label="slot only" value={String(overview.slot_only_count ?? 0)} accent="text-amber-300" />
          <Kpi label="on-chain" value={String(overview.chain_committed_count ?? 0)} accent="text-lime-300" />
          <Kpi label="hub watches" value={String(overview.hub_watch_count ?? 0)} accent="text-violet-300" />
          <Kpi label="unique repos" value={String(overview.unique_repos)} small />
          <Kpi label="hippius" value={String(overview.hippius_count)} accent="text-sky-400" />
          <Kpi label="hugging face" value={String(overview.huggingface_count)} accent="text-orange-400" />
          <Kpi label="Qwen3.6-35B" value={String(overview.qwen36_35b_repos)} accent="text-sky-300" />
          <Kpi label="in sync" value={String(overview.in_sync_count)} accent="text-lime-400" />
          <Kpi label="mismatch" value={String(overview.mismatch_count)} warn={overview.mismatch_count > 0} />
          <Kpi label="pending poll" value={String(overview.pending_hub_poll)} />
          <Kpi label="hub 24h" value={String(overview.hub_updates_24h)} accent="text-sky-300" />
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <LatestHippiusReposPanel
          repos={hippiusLatest}
          loading={loading && hippiusLatest.length === 0 && !hippiusLatestError}
          totalHint={hippiusIndexTotal}
          error={hippiusLatestError}
        />
        <LatestHuggingFaceReposPanel
          repos={hfLatest}
          loading={loading && hfLatest.length === 0 && !hfLatestError}
          totalHint={hfIndexTotal}
          error={hfLatestError}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        <section className="panel xl:col-span-5">
          <div className="panel-head">
            <h3 className="text-[11px] font-semibold text-zinc-100">Activity feed</h3>
            <span className="text-[9px] text-zinc-600">
              {searchActive ? `${filteredFeed.length}/${feed.length}` : feed.length} events
            </span>
          </div>
          <div className="scroll-pane max-h-[420px] overflow-y-auto divide-y divide-zinc-800/50">
            {filteredFeed.length === 0 ? (
              <p className="px-3 py-6 text-[10px] text-zinc-500 text-center">
                {loading
                  ? "loading activity…"
                  : searchActive
                    ? "no events match search"
                    : tracks.length > 0
                      ? "no events yet — click sync registries to poll Hippius/HF"
                      : "no qwen repos from slots or hub discovery yet"}
              </p>
            ) : (
              filteredFeed.map((e) => (
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
                    href={modelCommitUrl(
                      e.repo,
                      e.chain_digest ?? e.hub_digest ?? "",
                      (e.meta?.host as string) === "huggingface" ? "huggingface" : "hippius"
                    )}
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
                  {(e.chain_digest || e.hub_digest) && (
                    <p className="text-[9px] mono text-zinc-600 mt-1">
                      {e.chain_digest && <>chain {shortHash(e.chain_digest)} </>}
                      {e.hub_digest && <>remote {shortHash(e.hub_digest)}</>}
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
              <h3 className="text-[11px] font-semibold text-zinc-100">Tracked repos</h3>
              <p className="text-[10px] text-zinc-500">
                {!showAllTracks && !searchActive && filteredTracks.length > TRACKED_REPOS_PREVIEW
                  ? `Latest ${TRACKED_REPOS_PREVIEW} of ${filteredTracks.length}`
                  : searchActive
                    ? `${filteredTracks.length}/${tracks.length} shown`
                    : `${filteredTracks.length} entries`}
                {sortKey === "remote_newest"
                  ? " · sorted by remote update time"
                  : ` · ${REPO_TRACK_SORT_OPTIONS.find((o) => o.key === sortKey)?.label ?? sortKey}`}
              </p>
            </div>
            {!searchActive && filteredTracks.length > TRACKED_REPOS_PREVIEW && (
              <button
                type="button"
                onClick={() => setShowAllTracks((v) => !v)}
                className="px-2 py-1 rounded text-[10px] border border-zinc-700 text-zinc-400 hover:border-sky-500/40 hover:text-sky-200"
              >
                {showAllTracks ? "show latest 10" : `show all ${filteredTracks.length}`}
              </button>
            )}
          </div>
          <div className="scroll-pane overflow-x-auto max-h-[420px] overflow-y-auto">
            <table className="tbl">
              <thead className="sticky top-0 z-10 bg-zinc-950">
                <tr>
                  <th>uid</th>
                  <th>host</th>
                  <th>repo</th>
                  <th>era</th>
                  <th>sync</th>
                  <th>files</th>
                  <th>source</th>
                  <th>remote updated</th>
                  <th>chain</th>
                  <th>remote</th>
                </tr>
              </thead>
              <tbody>
                {displayTracks.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="text-center text-zinc-500 py-8 text-[10px]">
                      {loading
                        ? "loading…"
                        : searchActive
                          ? "no repos match search"
                          : "no qwen repos from slots or hub discovery yet"}
                    </td>
                  </tr>
                ) : (
                  displayTracks.map((t) => {
                    const expanded = expandedRepo === `${t.hotkey}-${t.repo}`;
                    return (
                      <Fragment key={`${t.hotkey}-${t.repo}`}>
                        <tr
                          className="cursor-pointer"
                          onClick={() => setExpandedRepo(expanded ? null : `${t.hotkey}-${t.repo}`)}
                        >
                          <td className="mono text-zinc-200">{t.uid ?? "—"}</td>
                          <td>
                            <span
                              className={`inline-flex px-1 py-px rounded border text-[8px] uppercase ${hostBadge(t.repo_host)}`}
                            >
                              {t.repo_host === "huggingface" ? "HF" : "hippius"}
                            </span>
                          </td>
                          <td className="max-w-[140px]">
                            <a
                              href={repoUrl(t)}
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
                            {t.pending_hub_poll && (
                              <span className="text-zinc-500 text-[9px]">pending</span>
                            )}
                            {!t.pending_hub_poll && t.digest_in_sync === true && (
                              <span className="text-lime-400 text-[9px]">synced</span>
                            )}
                            {!t.pending_hub_poll && t.digest_in_sync === false && (
                              <span className="text-rose-400 text-[9px]">mismatch</span>
                            )}
                          </td>
                          <td className="mono text-[10px] text-zinc-500 tabular-nums">
                            {t.file_count ?? "—"}
                          </td>
                          <td>
                            {trackSourceLabel(t.track_source) ? (
                              <span
                                className={`inline-flex px-1 py-px rounded border text-[8px] ${trackSourceColor(t.track_source)}`}
                              >
                                {trackSourceLabel(t.track_source)}
                              </span>
                            ) : (
                              <span className="text-[9px] text-zinc-600">—</span>
                            )}
                          </td>
                          <td className="text-[10px] text-zinc-500">
                            <span className={hasDefiniteRemoteTime(t) ? "text-zinc-300" : "text-zinc-600"}>
                              {fmtTime(t.hub_updated_at ?? t.last_hub_change_at)}
                            </span>
                            {!hasDefiniteRemoteTime(t) && t.pending_hub_poll && (
                              <span className="block text-[8px] text-zinc-600">no remote time</span>
                            )}
                          </td>
                          <td className="mono text-[9px] text-zinc-600">
                            {t.chain_digest ? `${shortHash(t.chain_digest)}…` : "—"}
                          </td>
                          <td className="mono text-[9px] text-zinc-600">
                            {t.hub_digest ? `${shortHash(t.hub_digest)}…` : "—"}
                          </td>
                        </tr>
                        {expanded && (t.hub_commit_message || t.coldkey) && (
                          <tr className="bg-zinc-900/40">
                            <td colSpan={10} className="text-[10px] text-zinc-500 py-2">
                              {t.hub_commit_message && (
                                <>
                                  <span className="text-zinc-400">remote:</span> {t.hub_commit_message}{" "}
                                </>
                              )}
                              {t.coldkey && (
                                <span className="mono text-zinc-600">coldkey {shortAddr(t.coldkey, 4)}</span>
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
