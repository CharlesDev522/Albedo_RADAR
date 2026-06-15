"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  shortAddr,
  shortHash,
  shortRepo,
  hippiusModelUrl,
  type Commitment,
  type CommitmentStats,
  type Registry,
  type SyncStatus,
} from "@/lib/api";
import {
  commitColumnDir,
  sortCommitRows,
  toggleCommitSort,
  type CommitRowSortKey,
} from "@/lib/slotSort";
import { useSubnet } from "@/lib/useSubnet";
import SortableTh from "@/components/SortableTh";

const LIVE_URL = "/api/v1/live/stream";
const POLL_MS = 3000;

interface LiveEvent {
  type: string;
  uid?: number;
  hotkey?: string;
  coldkey?: string;
  repo?: string;
  model_uri?: string;
  commit_block?: number;
  registered_at_block?: number;
  timestamp?: string;
}

interface LiveDashboardProps {
  initialStats?: CommitmentStats | null;
  initialCommits?: Commitment[];
  initialRegistry?: Registry | null;
}

export default function LiveDashboard({
  initialStats = null,
  initialCommits = [],
  initialRegistry = null,
}: LiveDashboardProps) {
  const { subnet } = useSubnet();
  const [stats, setStats] = useState<CommitmentStats | null>(initialStats);
  const [commits, setCommits] = useState<Commitment[]>(initialCommits);
  const [registry, setRegistry] = useState<Registry | null>(initialRegistry);
  const [commitSort, setCommitSort] = useState<CommitRowSortKey>("uid_asc");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(
    initialCommits.length > 0 ? new Date() : null
  );
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [liveStatus, setLiveStatus] = useState<"connecting" | "live" | "polling">("connecting");
  const [apiError, setApiError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(null);
  const [flashUids, setFlashUids] = useState<Set<number>>(new Set());
  const [feed, setFeed] = useState<LiveEvent[]>([]);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const knownUids = useRef<Set<number>>(new Set(initialCommits.map((c) => c.uid).filter((u): u is number => u != null)));
  const subnetRef = useRef(subnet);

  useEffect(() => {
    subnetRef.current = subnet;
    setStats(null);
    setCommits([]);
    setRegistry(null);
    setSyncStatus(null);
    setFeed([]);
    knownUids.current = new Set();
    setCommitSort("uid_asc");
  }, [subnet]);

  const sortedCommits = useMemo(() => sortCommitRows(commits, commitSort), [commits, commitSort]);

  const flash = useCallback((uid: number | undefined) => {
    if (uid == null) return;
    setFlashUids((prev) => new Set(prev).add(uid));
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlashUids(new Set()), 6000);
  }, []);

  const refresh = useCallback(async () => {
    const fetchSubnet = subnet;
    const t0 = performance.now();
    try {
      const [s, c, r, sync] = await Promise.all([
        api.getStats(fetchSubnet),
        api.getCommitments(fetchSubnet),
        api.getRegistry(fetchSubnet),
        api.getSyncStatus(fetchSubnet),
      ]);
      if (subnetRef.current !== fetchSubnet) return;
      for (const row of c.commitments) {
        if (row.uid != null && !knownUids.current.has(row.uid)) {
          flash(row.uid);
        }
      }
      knownUids.current = new Set(
        c.commitments.map((row) => row.uid).filter((u): u is number => u != null)
      );
      setStats(s);
      setCommits(c.commitments);
      setRegistry(r);
      setSyncStatus(sync);
      setLastRefresh(new Date());
      setLatencyMs(Math.round(performance.now() - t0));
      setApiError(null);
    } catch (err) {
      setLiveStatus("polling");
      setApiError(err instanceof Error ? err.message : "API unreachable");
    }
  }, [subnet, flash]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      es = new EventSource(`${LIVE_URL}?subnet=${subnet}`);
      setLiveStatus("connecting");

      es.addEventListener("connected", () => setLiveStatus("live"));
      es.addEventListener("commit", (e) => {
        try {
          const data: LiveEvent = JSON.parse(e.data);
          setFeed((prev) => [data, ...prev].slice(0, 30));
          flash(data.uid);
          refresh();
        } catch {
          /* ignore */
        }
      });
      es.addEventListener("ping", () => setLiveStatus("live"));
      es.onerror = () => {
        setLiveStatus("polling");
        es?.close();
        retryTimer = setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      es?.close();
      clearTimeout(retryTimer);
    };
  }, [subnet, flash, refresh]);

  const waiting = registry?.miners.filter((m) => !m.has_v5) ?? [];
  const v6Count = registry?.v6_count ?? commits.filter((c) => c.version === "v6" || c.reveal_string?.startsWith("v6|")).length;
  const v5Count = registry?.v5_count ?? commits.filter((c) => (c.version ?? "v5") === "v5" || c.reveal_string?.startsWith("v5|")).length;

  return (
    <div className="space-y-3">
      {apiError && (
        <div className="panel px-3 py-2 border-rose-500/20 bg-rose-500/5 text-[11px] text-rose-300">
          API error: {apiError} — browser calls <code className="mono text-rose-100">/api/v1</code> on port 3000,
          which proxies to the FastAPI service (check <code className="mono text-rose-100">API_URL</code> in frontend container).
        </div>
      )}
      {!apiError && syncStatus && !syncStatus.in_sync && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[11px] text-amber-300">
          Chain has <strong>{syncStatus.onchain_v5_count}</strong> model commits (v5/v6 · uids{" "}
          {syncStatus.onchain_uids.join(", ") || "—"}) but DB has{" "}
          <strong>{syncStatus.db_v5_count}</strong>
          {syncStatus.missing_in_db.length > 0 && (
            <> — missing uids: {syncStatus.missing_in_db.join(", ")}</>
          )}
          . Collector should catch up within ~10s — check{" "}
          <code className="mono text-amber-100">docker compose logs collector --tail 20</code>.
        </div>
      )}
      {!apiError && commits.length === 0 && stats?.committed_miners === 0 && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[11px] text-amber-300">
          No v5/v6 commits in database yet — check{" "}
          <code className="mono text-amber-100">docker compose logs collector</code> and{" "}
          <code className="mono text-amber-100">GET /api/v1/commitments/onchain</code>.
        </div>
      )}
      {/* status bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-zinc-500">
        <div className="flex items-center gap-3">
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border ${
              liveStatus === "live"
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
                : "border-amber-500/30 bg-amber-500/10 text-amber-400"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                liveStatus === "live" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
              }`}
            />
            {liveStatus === "live" ? "sse live" : liveStatus === "connecting" ? "connecting…" : `poll ${POLL_MS / 1000}s`}
          </span>
          {lastRefresh && (
            <span>
              refreshed {Math.round((Date.now() - lastRefresh.getTime()) / 1000)}s ago
              {latencyMs != null && ` · ${latencyMs}ms`}
            </span>
          )}
        </div>
        <span className="mono text-zinc-600">
          chain {syncStatus?.onchain_v5_count ?? "—"} · db {syncStatus?.db_v5_count ?? stats?.committed_miners ?? "—"} · poll ~3s
        </span>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <Kpi label="miners" value={String(stats?.total_neurons ?? "—")} />
        <Kpi label="model committed" value={String(stats?.committed_miners ?? "—")} accent />
        <Kpi
          label="v6 / v5"
          value={`${v6Count} / ${v5Count}`}
          accent
        />
        <Kpi label="no commit" value={String(stats?.uncommitted_miners ?? "—")} warn={(stats?.uncommitted_miners ?? 0) > 0} />
        <Kpi label="coverage" value={stats ? `${stats.coverage_pct}%` : "—"} />
        <Kpi label="latest blk" value={stats?.latest_commit_block?.toLocaleString() ?? "—"} mono />
        <Kpi label="scan" value={stats?.last_scan_at ? fmtTime(stats.last_scan_at) : "—"} small />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        {/* live feed */}
        <aside className="panel xl:col-span-3 order-2 xl:order-1">
          <div className="panel-head">
            <h2 className="text-[12px] font-semibold text-zinc-100">live feed</h2>
            <span className="pill-v5">instant</span>
          </div>
          <div className="max-h-[320px] overflow-y-auto divide-y divide-zinc-800/50">
            {feed.length === 0 ? (
              <p className="px-3 py-4 text-[10px] text-zinc-500">waiting for new commits…</p>
            ) : (
              feed.map((e, i) => (
                <div key={`${e.hotkey}-${i}`} className="px-3 py-2 bg-emerald-500/5">
                  <div className="flex justify-between gap-2">
                    <span className="pill-v5 text-[9px]">{e.type?.replace("commitment_", "")}</span>
                    <span className="text-[9px] text-zinc-600">{e.timestamp ? fmtTime(e.timestamp) : "now"}</span>
                  </div>
                  <p className="mono text-[11px] text-emerald-400 mt-1">uid {e.uid ?? "?"}</p>
                  <p className="text-[10px] text-zinc-500 truncate mt-0.5">
                    {e.repo ? (
                      <a
                        href={hippiusModelUrl(e.repo)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-sky-400 hover:underline"
                      >
                        {shortRepo(e.repo, 36)}
                      </a>
                    ) : (
                      e.model_uri
                    )}
                  </p>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* commits table */}
        <section className="panel xl:col-span-9 order-1 xl:order-2">
          <div className="panel-head">
            <div>
              <h2 className="text-[12px] font-semibold text-zinc-100">v5 / v6 commits · SN{subnet}</h2>
              <p className="text-[10px] text-zinc-500">click column headers to sort · new rows flash green</p>
            </div>
            <span className="pill-v5">{commits.length} active</span>
          </div>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <SortableTh
                    label="uid"
                    direction={commitColumnDir(commitSort, "uid")}
                    onClick={() => setCommitSort((s) => toggleCommitSort(s, "uid"))}
                  />
                  <th>hotkey</th>
                  <SortableTh
                    label="coldkey"
                    direction={commitColumnDir(commitSort, "coldkey")}
                    onClick={() => setCommitSort((s) => toggleCommitSort(s, "coldkey"))}
                  />
                  <th>reg</th>
                  <SortableTh
                    label="commit"
                    direction={commitColumnDir(commitSort, "commit")}
                    onClick={() => setCommitSort((s) => toggleCommitSort(s, "commit"))}
                  />
                  <th>model</th>
                  <th>hash</th>
                </tr>
              </thead>
              <tbody>
                {sortedCommits.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center text-zinc-500 py-8">
                      no model commits yet
                    </td>
                  </tr>
                ) : (
                  sortedCommits.map((c) => {
                    const isNew = c.uid != null && flashUids.has(c.uid);
                    return (
                      <tr
                        key={c.id}
                        className={isNew ? "bg-emerald-500/15 ring-1 ring-emerald-500/40" : ""}
                      >
                        <td className="mono font-medium text-zinc-200">
                          {c.uid ?? "—"}
                          <span className={`ml-1 text-[8px] uppercase ${(c.version ?? (c.reveal_string?.startsWith("v6|") ? "v6" : "v5")) === "v6" ? "text-lime-400" : "text-emerald-400"}`}>
                            {c.version ?? (c.reveal_string?.startsWith("v6|") ? "v6" : "v5")}
                          </span>
                          {isNew && <span className="ml-1 text-[9px] text-emerald-400">NEW</span>}
                        </td>
                        <td className="mono text-emerald-400/90" title={c.hotkey}>
                          {shortAddr(c.hotkey, 6)}
                        </td>
                        <td className="mono text-zinc-500" title={c.coldkey ?? ""}>
                          {c.coldkey ? shortAddr(c.coldkey, 4) : "—"}
                        </td>
                        <td className="mono text-zinc-500 tabular-nums">
                          {c.registered_at_block?.toLocaleString() ?? "—"}
                        </td>
                        <td className="mono text-zinc-300 tabular-nums">{c.commit_block.toLocaleString()}</td>
                        <td className="max-w-[160px]">
                          <a
                            href={hippiusModelUrl(c.repo)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sky-400/90 hover:underline truncate block text-[10px]"
                            title={hippiusModelUrl(c.repo)}
                          >
                            {shortRepo(c.repo)}
                          </a>
                        </td>
                        <td className="mono text-[10px] text-zinc-500">{shortHash(c.digest)}…</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* registry */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="text-[12px] font-semibold text-zinc-100">miner registry · SN{subnet}</h2>
          </div>
          <span className="text-[10px] text-zinc-500">{registry?.total ?? 0} miners · v6/v5 first</span>
        </div>
        <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
          <table className="tbl">
            <thead className="sticky top-0 z-10">
              <tr>
                <th>uid</th>
                <th>st</th>
                <th>hotkey</th>
                <th>coldkey</th>
                <th>reg</th>
                <th>model</th>
              </tr>
            </thead>
            <tbody>
              {(registry?.miners ?? []).map((m) => (
                <tr
                  key={m.uid}
                  className={`${m.has_v5 ? "" : "opacity-50"} ${
                    flashUids.has(m.uid) ? "bg-emerald-500/10" : ""
                  }`}
                >
                  <td className="mono text-zinc-200">{m.uid}</td>
                  <td>
                    {m.has_v5 ? (
                      <span className={m.version === "v6" ? "pill-v6" : "pill-v5"}>{m.version ?? "v5"}</span>
                    ) : (
                      <span className="pill-none">—</span>
                    )}
                  </td>
                  <td className="mono text-zinc-400">{shortAddr(m.hotkey, 6)}</td>
                  <td className="mono text-zinc-500">{shortAddr(m.coldkey, 4)}</td>
                  <td className="mono text-zinc-500 tabular-nums">{m.registered_at_block?.toLocaleString() ?? "—"}</td>
                  <td className="text-[10px] truncate max-w-[180px]">
                    {m.repo ? (
                      <a
                        href={hippiusModelUrl(m.repo)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-zinc-500 hover:text-sky-400 hover:underline"
                        title={hippiusModelUrl(m.repo)}
                      >
                        {shortRepo(m.repo)}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {waiting.length > 0 && (
          <div className="px-3 py-2 border-t border-zinc-800/80 text-[10px] text-zinc-600">
            {waiting.length} miners without v5/v6
          </div>
        )}
      </section>
    </div>
  );
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function Kpi({
  label,
  value,
  accent,
  warn,
  mono,
  small,
}: {
  label: string;
  value: string;
  accent?: boolean;
  warn?: boolean;
  mono?: boolean;
  small?: boolean;
}) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p
        className={`${small ? "text-[11px] font-normal text-zinc-400" : "stat-value"} ${
          mono ? "mono" : ""
        } ${accent ? "text-emerald-400" : ""} ${warn ? "text-amber-400" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}
