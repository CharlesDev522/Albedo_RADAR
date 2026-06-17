"use client";

import { useMemo, useState } from "react";
import {
  shortAddr,
  shortHash,
  shortRepo,
  modelCommitUrl,
} from "@/lib/api";
import {
  sortCommits,
  sortRegistry,
  type DashboardSortKey,
} from "@/lib/dashboardSort";
import { getSubnetProfile } from "@/lib/subnets";
import { DASHBOARD_POLL_MS, useDashboardSync } from "@/lib/DashboardSyncContext";
import { useSubnet } from "@/lib/useSubnet";
import TableSortBar from "@/components/TableSortBar";

export default function LiveDashboard() {
  const { subnet } = useSubnet();
  const profile = getSubnetProfile(subnet);
  const {
    stats,
    commits,
    registry,
    syncStatus,
    lastRefresh,
    latencyMs,
    apiError,
    liveStatus,
    flashUids,
    feed,
  } = useDashboardSync();
  const [commitSort, setCommitSort] = useState<DashboardSortKey>("commit_desc");
  const [registrySort, setRegistrySort] = useState<DashboardSortKey>("committed_first");

  const commitLabel = profile.features.commitLabel;
  const modelHost = profile.features.modelHost;

  const sortedCommits = useMemo(() => sortCommits(commits, commitSort), [commits, commitSort]);
  const sortedRegistry = useMemo(
    () => sortRegistry(registry?.miners ?? [], registrySort),
    [registry?.miners, registrySort]
  );

  const fmtIncentive = (n: number | null | undefined) => {
    if (n == null || n <= 0) return "—";
    if (n >= 0.999) return "100%";
    return `${(n * 100).toFixed(1)}%`;
  };

  const waiting = registry?.miners.filter((m) => !m.has_v6) ?? [];
  const committedCount = registry?.v6_count ?? commits.length;

  return (
    <div className="space-y-3">
      {apiError && (
        <div className="panel px-3 py-2 border-rose-500/20 bg-rose-500/5 text-[11px] text-rose-300">
          API error: {apiError} — browser calls <code className="mono text-rose-100">/api/v1</code> on port 3000,
          which proxies to the FastAPI service (check <code className="mono text-rose-100">API_URL</code> in frontend container).
        </div>
      )}
      {!apiError && syncStatus && syncStatus.in_sync === false && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[11px] text-amber-300">
          Chain has <strong>{syncStatus.onchain_v6_count ?? "—"}</strong> on-chain commits (uids{" "}
          {syncStatus.onchain_uids.join(", ") || "—"}) but DB has{" "}
          <strong>{syncStatus.db_v6_count}</strong>
          {syncStatus.missing_in_db.length > 0 && (
            <> — missing uids: {syncStatus.missing_in_db.join(", ")}</>
          )}
          {(syncStatus.stale_in_db?.length ?? 0) > 0 && (
            <> — stale in DB: {syncStatus.stale_in_db?.join(", ")}</>
          )}
          . Collector should catch up within ~10s — check{" "}
          <code className="mono text-amber-100">docker compose logs collector --tail 20</code>.
        </div>
      )}
      {!apiError && commits.length === 0 && stats?.committed_miners === 0 && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[11px] text-amber-300">
          No {commitLabel} commits in database yet — check{" "}
          <code className="mono text-amber-100">docker compose logs collector</code> and{" "}
          <code className="mono text-amber-100">GET /api/v1/commitments/onchain</code>.
        </div>
      )}
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
            {liveStatus === "live" ? "sse live" : liveStatus === "connecting" ? "connecting…" : `poll ${DASHBOARD_POLL_MS / 1000}s`}
          </span>
          {lastRefresh && (
            <span>
              refreshed {Math.round((Date.now() - lastRefresh.getTime()) / 1000)}s ago
              {latencyMs != null && ` · ${latencyMs}ms`}
            </span>
          )}
        </div>
        <span className="mono text-zinc-600">
          chain {syncStatus?.onchain_v6_count ?? "—"} · db {syncStatus?.db_v6_count ?? stats?.committed_miners ?? "—"} · sync ~{DASHBOARD_POLL_MS / 1000}s
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <Kpi label="miners" value={String(stats?.total_neurons ?? "—")} />
        <Kpi label={`${commitLabel} committed`} value={String(stats?.committed_miners ?? "—")} accent />
        <Kpi label={`${commitLabel} active`} value={String(committedCount)} accent />
        <Kpi label="no commit" value={String(stats?.uncommitted_miners ?? "—")} warn={(stats?.uncommitted_miners ?? 0) > 0} />
        <Kpi label="coverage" value={stats ? `${stats.coverage_pct}%` : "—"} />
        <Kpi label="latest blk" value={stats?.latest_commit_block?.toLocaleString() ?? "—"} mono />
        <Kpi label="scan" value={stats?.last_scan_at ? fmtTime(stats.last_scan_at) : "—"} small />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        <aside className="panel xl:col-span-3 order-2 xl:order-1">
          <div className="panel-head">
            <h2 className="text-[12px] font-semibold text-zinc-100">live feed</h2>
            <span className="pill-v6">instant</span>
          </div>
          <div className="max-h-[320px] overflow-y-auto divide-y divide-zinc-800/50">
            {feed.length === 0 ? (
              <p className="px-3 py-4 text-[10px] text-zinc-500">waiting for new commits…</p>
            ) : (
              feed.map((e, i) => (
                <div key={`${e.hotkey}-${i}`} className="px-3 py-2 bg-lime-500/5">
                  <div className="flex justify-between gap-2">
                    <span className="pill-v6 text-[9px]">{e.type?.replace("commitment_", "")}</span>
                    <span className="text-[9px] text-zinc-600">{e.timestamp ? fmtTime(e.timestamp) : "now"}</span>
                  </div>
                  <p className="mono text-[11px] text-lime-400 mt-1">uid {e.uid ?? "?"}</p>
                  <p className="text-[10px] text-zinc-500 truncate mt-0.5">
                    {e.repo ? (
                      <a
                        href={modelCommitUrl(e.repo, "", modelHost)}
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

        <section className="panel xl:col-span-9 order-1 xl:order-2">
          <div className="panel-head">
            <div>
              <h2 className="text-[12px] font-semibold text-zinc-100">{commitLabel} commits · SN{subnet}</h2>
              <p className="text-[10px] text-zinc-500">new rows flash green</p>
            </div>
            <span className="pill-v6">{commits.length} active</span>
          </div>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>uid</th>
                  <th>commit</th>
                  <th>reg</th>
                  <th>hotkey</th>
                  <th>coldkey</th>
                  <th>model</th>
                  <th>hash</th>
                </tr>
              </thead>
              <tbody>
                {sortedCommits.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="text-center text-zinc-500 py-8">
                      no {commitLabel} commits yet
                    </td>
                  </tr>
                ) : (
                  sortedCommits.map((c) => {
                    const isNew = c.uid != null && flashUids.has(c.uid);
                    return (
                      <tr
                        key={c.id}
                        className={isNew ? "bg-lime-500/15 ring-1 ring-lime-500/40" : ""}
                      >
                        <td className="mono font-medium text-zinc-200">
                          {c.uid ?? "—"}
                          <span className="ml-1 text-[8px] uppercase text-lime-400">{c.version ?? commitLabel}</span>
                          {isNew && <span className="ml-1 text-[9px] text-lime-400">NEW</span>}
                        </td>
                        <td className="mono text-zinc-300 tabular-nums">{c.commit_block.toLocaleString()}</td>
                        <td className="mono text-zinc-500 tabular-nums">
                          {c.registered_at_block?.toLocaleString() ?? "—"}
                        </td>
                        <td className="mono text-lime-400/90" title={c.hotkey}>
                          {shortAddr(c.hotkey, 6)}
                        </td>
                        <td className="mono text-zinc-500" title={c.coldkey ?? ""}>
                          {c.coldkey ? shortAddr(c.coldkey, 4) : "—"}
                        </td>
                        <td className="max-w-[160px]">
                          <a
                            href={modelCommitUrl(c.repo, c.digest, modelHost)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-sky-400/90 hover:underline truncate block text-[10px]"
                            title={modelCommitUrl(c.repo, c.digest, modelHost)}
                          >
                            {shortRepo(c.repo)}
                          </a>
                        </td>
                        <td className="mono text-[10px] text-zinc-500">
                          {c.digest.startsWith("revision:")
                            ? `${c.digest.slice("revision:".length).slice(0, 10)}…`
                            : `${shortHash(c.digest)}…`}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <TableSortBar sort={commitSort} onSort={setCommitSort} />
        </section>
      </div>

      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="text-[12px] font-semibold text-zinc-100">miner registry · SN{subnet}</h2>
          </div>
          <span className="text-[10px] text-zinc-500">
            {registry?.total ?? 0} miners · {registry?.v6_count ?? 0} {commitLabel}
          </span>
        </div>
        <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
          <table className="tbl">
            <thead className="sticky top-0 z-10 bg-zinc-950">
              <tr>
                <th>uid</th>
                <th>commit</th>
                <th>reg</th>
                {profile.features.incentiveColumn && <th>incentive</th>}
                <th>st</th>
                <th>hotkey</th>
                <th>coldkey</th>
                <th>model</th>
              </tr>
            </thead>
            <tbody>
              {sortedRegistry.length === 0 ? (
                <tr>
                  <td colSpan={profile.features.incentiveColumn ? 8 : 7} className="text-center text-zinc-500 py-8 text-[10px]">
                    {registry ? "no miners" : "loading registry…"}
                  </td>
                </tr>
              ) : (
              sortedRegistry.map((m) => (
                <tr
                  key={m.uid}
                  className={`${m.has_v6 ? "" : "opacity-50"} ${
                    flashUids.has(m.uid) ? "bg-lime-500/10" : ""
                  }`}
                >
                  <td className="mono text-zinc-200">{m.uid}</td>
                  <td className="mono text-zinc-400 tabular-nums">
                    {m.commit_block?.toLocaleString() ?? "—"}
                  </td>
                  <td className="mono text-zinc-500 tabular-nums">{m.registered_at_block?.toLocaleString() ?? "—"}</td>
                  {profile.features.incentiveColumn && (
                    <td
                      className={`mono tabular-nums ${
                        m.receiving_incentive ? "text-lime-400" : "text-zinc-600"
                      }`}
                    >
                      {fmtIncentive(m.incentive)}
                    </td>
                  )}
                  <td>
                    {m.has_v6 ? (
                      <span className="pill-v6">{m.version ?? commitLabel}</span>
                    ) : (
                      <span className="pill-none">—</span>
                    )}
                  </td>
                  <td className="mono text-zinc-400">{shortAddr(m.hotkey, 6)}</td>
                  <td className="mono text-zinc-500">{shortAddr(m.coldkey, 4)}</td>
                  <td className="text-[10px] truncate max-w-[180px]">
                    {m.repo ? (
                      <a
                        href={modelCommitUrl(m.repo, m.model_uri?.split("@")[1] ?? "", modelHost)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-zinc-500 hover:text-sky-400 hover:underline"
                        title={modelCommitUrl(m.repo, m.model_uri?.split("@")[1] ?? "", modelHost)}
                      >
                        {shortRepo(m.repo)}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))
              )}
            </tbody>
          </table>
        </div>
        <TableSortBar sort={registrySort} onSort={setRegistrySort} showStatus />
        {waiting.length > 0 && (
          <div className="px-3 py-2 border-t border-zinc-800/80 text-[10px] text-zinc-600">
            {waiting.length} miners without {commitLabel}
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
        } ${accent ? "text-lime-400" : ""} ${warn ? "text-amber-400" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}
