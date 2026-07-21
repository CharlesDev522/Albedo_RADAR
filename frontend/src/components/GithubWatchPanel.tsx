"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type GithubWatchOverview } from "@/lib/api";
import { usePageVisibility } from "@/lib/usePageVisibility";

const POLL_MS = 8_000;

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function shortSha(sha: string | null | undefined): string {
  if (!sha) return "—";
  return sha.slice(0, 7);
}

export default function GithubWatchPanel({ active }: { active: boolean }) {
  const pageVisible = usePageVisibility();
  const [data, setData] = useState<GithubWatchOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);

  const loadOverview = useCallback(async (forceRefresh = false) => {
    const overview = await api.getGithubWatch(30, forceRefresh);
    setData(overview);
    setLastFetch(new Date());
    setError(null);
    return overview;
  }, []);

  const refresh = useCallback(
    async (opts?: { pollGitHub?: boolean }) => {
      try {
        if (opts?.pollGitHub) {
          setSyncing(true);
          await api.syncGithubWatch();
        }
        await loadOverview(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : "GitHub watch unavailable");
      } finally {
        setLoading(false);
        setSyncing(false);
      }
    },
    [loadOverview]
  );

  useEffect(() => {
    if (!active || !pageVisible) return;
    setLoading(true);
    void refresh();
    const id = setInterval(() => void loadOverview(true), POLL_MS);
    return () => clearInterval(id);
  }, [active, pageVisible, refresh, loadOverview]);

  if (!loading && !data?.enabled && !error) {
    return null;
  }

  const targets = data?.configured_targets ?? [];
  const states = data?.watch_states ?? [];
  const alerts = data?.recent_alerts ?? [];

  return (
    <section className="panel px-3 py-2 mb-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
        <div>
          <h3 className="text-[11px] font-semibold text-zinc-200">GitHub repo watch</h3>
          <p className="text-[9px] text-zinc-500 mt-0.5">
            collector polls every {data?.poll_interval_seconds ?? "—"}s · UI refresh {POLL_MS / 1000}s
            {lastFetch && (
              <span className="ml-1 text-zinc-600">· fetched {lastFetch.toLocaleTimeString()}</span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh({ pollGitHub: true })}
          disabled={syncing || loading}
          className="text-[9px] px-2 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
        >
          {syncing ? "polling…" : "poll now"}
        </button>
      </div>

      {loading && !data && (
        <p className="text-[10px] text-zinc-500 py-2">Loading GitHub watch status…</p>
      )}

      {error && <p className="text-[10px] text-rose-300 mb-2">{error}</p>}

      {!loading && targets.length === 0 && !error && (
        <p className="text-[10px] text-amber-300/90 mb-2">
          No watches configured. Set <code className="mono">GITHUB_REPO_WATCHES</code> in{" "}
          <code className="mono">.env</code> and restart collector + api.
        </p>
      )}

      {targets.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {targets.map((t) => {
            const st = states.find(
              (s) => s.owner === t.owner && s.repo === t.repo && s.branch === t.branch
            );
            return (
              <a
                key={t.full_name + t.branch}
                href={t.tree_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex flex-col gap-0.5 px-2 py-1 rounded border border-zinc-800 bg-zinc-900/50 text-[9px] hover:border-zinc-600"
              >
                <span className="text-zinc-300 font-medium">
                  {t.repo}
                  <span className="text-zinc-500">@{t.branch}</span>
                </span>
                <span className="text-zinc-500 mono">
                  tip {shortSha(st?.last_seen_sha)} · checked {fmtTime(st?.last_checked_at)}
                </span>
              </a>
            );
          })}
        </div>
      )}

      {!loading && alerts.length === 0 ? (
        <p className="text-[10px] text-zinc-600 py-2">
          No new commits recorded yet. First poll seeds the current tip (no alert). Use poll now to
          check GitHub immediately.
        </p>
      ) : (
        alerts.length > 0 && (
          <ul className="max-h-[220px] overflow-y-auto space-y-1.5">
            {alerts.map((a) => (
              <li
                key={`${a.commit_sha}-${a.created_at}`}
                className="flex flex-col gap-0.5 px-2 py-1.5 rounded border border-zinc-800/80 bg-zinc-950/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <a
                    href={a.commit_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] text-sky-300 hover:underline truncate"
                  >
                    {a.repo}@{a.branch} · {a.commit_sha.slice(0, 7)}
                  </a>
                  <span className="text-[8px] text-zinc-600 shrink-0">{fmtTime(a.created_at)}</span>
                </div>
                <p className="text-[10px] text-zinc-400 truncate" title={a.commit_subject}>
                  {a.commit_subject}
                </p>
                {a.slack_sent && (
                  <span className="text-[8px] text-emerald-500/80">Slack sent</span>
                )}
              </li>
            ))}
          </ul>
        )
      )}
    </section>
  );
}
