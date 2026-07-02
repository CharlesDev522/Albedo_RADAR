"use client";

import { Fragment, useMemo, useState } from "react";
import {
  shortAddr,
  shortRepo,
  type AlbedoCrownLeaderboardRow,
  type AlbedoRepoColdkeyLink,
  type AlbedoRepoCrownAnalysis,
} from "@/lib/api";

type SortKey =
  | "coronations"
  | "slot_hours"
  | "active_hours"
  | "weight"
  | "win_pct"
  | "owners"
  | "total_alpha"
  | "total_tao"
  | "ongoing_daily"
  | "name";

type LinkSortKey =
  | "coronations"
  | "slot_hours"
  | "active_hours"
  | "total_alpha"
  | "total_tao"
  | "repo"
  | "coldkey";

function fmtAlpha(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "—";
  if (n >= 100) return `${n.toFixed(1)} α`;
  if (n >= 1) return `${n.toFixed(2)} α`;
  return `${n.toFixed(4)} α`;
}

function fmtTao(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "—";
  if (n >= 10) return `${n.toFixed(2)} τ`;
  if (n >= 0.01) return `${n.toFixed(4)} τ`;
  return `${n.toFixed(6)} τ`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function fmtHours(h: number | null | undefined): string {
  if (h == null || !Number.isFinite(h)) return "—";
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
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

function sortRepos(rows: AlbedoCrownLeaderboardRow[], sortBy: SortKey, desc: boolean): AlbedoCrownLeaderboardRow[] {
  const sorted = [...rows].sort((a, b) => {
    let cmp = 0;
    switch (sortBy) {
      case "coronations":
        cmp = a.coronations - b.coronations;
        break;
      case "slot_hours":
        cmp = a.total_slot_hours - b.total_slot_hours;
        break;
      case "active_hours":
        cmp = a.total_active_hours - b.total_active_hours;
        break;
      case "weight":
        cmp = a.current_weight_pct - b.current_weight_pct;
        break;
      case "win_pct":
        cmp = (a.challenger_win_pct ?? -1) - (b.challenger_win_pct ?? -1);
        break;
      case "owners":
        cmp = a.owner_count - b.owner_count;
        break;
      case "total_alpha":
        cmp = (a.total_estimated_alpha ?? -1) - (b.total_estimated_alpha ?? -1);
        break;
      case "total_tao":
        cmp = (a.total_estimated_tao ?? -1) - (b.total_estimated_tao ?? -1);
        break;
      case "ongoing_daily":
        cmp = (a.ongoing_daily_alpha ?? -1) - (b.ongoing_daily_alpha ?? -1);
        break;
      case "name":
        cmp = a.label.localeCompare(b.label);
        break;
    }
    return desc ? -cmp : cmp;
  });
  return sorted;
}

function sortLinks(rows: AlbedoRepoColdkeyLink[], sortBy: LinkSortKey, desc: boolean): AlbedoRepoColdkeyLink[] {
  const sorted = [...rows].sort((a, b) => {
    let cmp = 0;
    switch (sortBy) {
      case "coronations":
        cmp = a.coronations - b.coronations;
        break;
      case "slot_hours":
        cmp = a.total_slot_hours - b.total_slot_hours;
        break;
      case "active_hours":
        cmp = a.total_active_hours - b.total_active_hours;
        break;
      case "total_alpha":
        cmp = (a.total_estimated_alpha ?? -1) - (b.total_estimated_alpha ?? -1);
        break;
      case "total_tao":
        cmp = (a.total_estimated_tao ?? -1) - (b.total_estimated_tao ?? -1);
        break;
      case "repo":
        cmp = a.repo.localeCompare(b.repo);
        break;
      case "coldkey":
        cmp = a.coldkey.localeCompare(b.coldkey);
        break;
    }
    return desc ? -cmp : cmp;
  });
  return sorted;
}

export default function RepoCrownAnalysisPanel({
  analysis,
  compact = false,
}: {
  analysis: AlbedoRepoCrownAnalysis;
  compact?: boolean;
}) {
  const [sortBy, setSortBy] = useState<SortKey>("total_alpha");
  const [sortDesc, setSortDesc] = useState(true);
  const [linkSortBy, setLinkSortBy] = useState<LinkSortKey>("total_alpha");
  const [linkSortDesc, setLinkSortDesc] = useState(true);
  const [search, setSearch] = useState("");
  const [multiOwnerOnly, setMultiOwnerOnly] = useState(false);
  const [inReignOnly, setInReignOnly] = useState(false);
  const [minCrowns, setMinCrowns] = useState(1);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"repos" | "coldkeys" | "links">("repos");

  const activeRows = useMemo(() => {
    if (view === "coldkeys") return analysis.crowns_by_coldkey ?? [];
    return analysis.crowns_by_repo ?? [];
  }, [view, analysis.crowns_by_coldkey, analysis.crowns_by_repo]);

  const filteredRepos = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = activeRows;
    if (multiOwnerOnly) rows = rows.filter((r) => r.multi_owner);
    if (minCrowns > 1) rows = rows.filter((r) => r.coronations >= minCrowns);
    if (inReignOnly) rows = rows.filter((r) => r.reign_slots > 0 || r.current_weight_pct > 0);
    if (q) {
      rows = rows.filter(
        (r) =>
          r.label.toLowerCase().includes(q) ||
          r.coldkeys.some((ck) => ck.toLowerCase().includes(q)) ||
          r.hotkeys.some((hk) => hk.toLowerCase().includes(q))
      );
    }
    return sortRepos(rows, sortBy, sortDesc);
  }, [activeRows, search, multiOwnerOnly, minCrowns, inReignOnly, sortBy, sortDesc]);

  const filteredLinks = useMemo(() => {
    const q = search.trim().toLowerCase();
    let rows = analysis.repo_coldkey_links ?? [];
    if (inReignOnly) rows = rows.filter((r) => r.in_reign);
    if (q) {
      rows = rows.filter(
        (r) =>
          r.repo.toLowerCase().includes(q) ||
          r.coldkey.toLowerCase().includes(q) ||
          (r.hotkey ?? "").toLowerCase().includes(q)
      );
    }
    return sortLinks(rows, linkSortBy, linkSortDesc);
  }, [analysis.repo_coldkey_links, search, inReignOnly, linkSortBy, linkSortDesc]);

  const displayLimit = compact ? 8 : 20;

  function toggleExpand(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const basis = analysis.reward_basis ?? {
    daily_subnet_alpha: 0,
    calculation_source: "unavailable",
    default_weight_bps: 2000,
    note: "",
  };
  const hasRewards = (analysis.grand_total_estimated_alpha ?? 0) > 0;

  if (!analysis.crowns_by_repo?.length) {
    return (
      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200">Crown analysis by repo</h3>
        <p className="text-[10px] text-zinc-500 mt-2">No crown data yet.</p>
      </section>
    );
  }

  return (
    <section className="panel px-3 py-2 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] font-semibold text-zinc-200">Crown rewards by repo / coldkey</h3>
          <p className="text-[9px] text-zinc-600 mt-0.5">
            {analysis.total_repos_crowned} repos · {analysis.total_unique_coldkeys} coldkeys ·{" "}
            {analysis.multi_owner_repos.length} multi-owner
            {hasRewards && (
              <>
                {" "}
                · total <span className="text-violet-300 mono">{fmtAlpha(analysis.grand_total_estimated_alpha)}</span>
                {analysis.grand_total_estimated_tao != null && (
                  <span className="text-amber-300 mono"> ({fmtTao(analysis.grand_total_estimated_tao)})</span>
                )}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-1 text-[9px]">
          <button
            type="button"
            onClick={() => setView("repos")}
            className={`px-2 py-1 rounded border ${view === "repos" ? "border-amber-500/50 bg-amber-500/15 text-amber-100" : "border-zinc-700 text-zinc-500"}`}
          >
            By repo
          </button>
          <button
            type="button"
            onClick={() => setView("coldkeys")}
            className={`px-2 py-1 rounded border ${view === "coldkeys" ? "border-violet-500/50 bg-violet-500/15 text-violet-100" : "border-zinc-700 text-zinc-500"}`}
          >
            By coldkey
          </button>
          <button
            type="button"
            onClick={() => setView("links")}
            className={`px-2 py-1 rounded border ${view === "links" ? "border-sky-500/50 bg-sky-500/15 text-sky-100" : "border-zinc-700 text-zinc-500"}`}
          >
            Repo ↔ coldkey
          </button>
        </div>
      </div>

      {basis && (
        <div className="rounded border border-zinc-800 bg-zinc-950/50 px-2 py-1.5 text-[9px] text-zinc-500">
          <span className="text-zinc-400">Reward basis ({basis.calculation_source}): </span>
          subnet <span className="mono text-violet-300">{fmtAlpha(basis.daily_subnet_alpha)}</span>/day
          {basis.daily_subnet_tao != null && (
            <span className="mono text-amber-300"> · {fmtTao(basis.daily_subnet_tao)}/day</span>
          )}
          <span className="text-zinc-600"> · {basis.note}</span>
          <span className="block text-zinc-600 mt-0.5">
            Crowns keyed by Hippius model path; coldkeys resolved from commitment history and miner records (not only active hotkeys).
          </span>
          {analysis.crown_history_coverage_note && (
            <span className="block text-amber-300/90 mt-1">{analysis.crown_history_coverage_note}</span>
          )}
          {(analysis.missing_crown_versions?.length ?? 0) > 0 && (
            <span className="block text-rose-300/90 mt-1">
              Reward totals exclude {analysis.missing_crown_versions!.length} missing king
              {analysis.missing_crown_versions!.length === 1 ? "" : "s"} (v
              {analysis.missing_crown_versions![0]}
              {analysis.missing_crown_versions!.length > 1
                ? `–v${analysis.missing_crown_versions![analysis.missing_crown_versions!.length - 1]}`
                : ""}
              ). Add <code className="mono">data/albedo_crown_seed_sn97.json</code> on the API host.
            </span>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-[9px]">
        <input
          type="search"
          placeholder="Search repo / coldkey / hotkey…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[140px] rounded border border-zinc-700 bg-zinc-900/80 px-2 py-1 text-zinc-200 placeholder:text-zinc-600"
        />
        <label className="flex items-center gap-1 text-zinc-500 cursor-pointer">
          <input
            type="checkbox"
            checked={multiOwnerOnly}
            onChange={(e) => setMultiOwnerOnly(e.target.checked)}
            className="rounded"
          />
          Multi-owner only
        </label>
        <label className="flex items-center gap-1 text-zinc-500 cursor-pointer">
          <input
            type="checkbox"
            checked={inReignOnly}
            onChange={(e) => setInReignOnly(e.target.checked)}
            className="rounded"
          />
          In reign
        </label>
        <label className="flex items-center gap-1 text-zinc-500">
          Min crowns
          <select
            value={minCrowns}
            onChange={(e) => setMinCrowns(Number(e.target.value))}
            className="rounded border border-zinc-700 bg-zinc-900 px-1 py-0.5 text-zinc-300"
          >
            {[1, 2, 3, 5].map((n) => (
              <option key={n} value={n}>
                {n}+
              </option>
            ))}
          </select>
        </label>
      </div>

      {(view === "repos" || view === "coldkeys") && (
        <>
          <div className="flex flex-wrap gap-1 text-[9px]">
            {(
              [
                ["total_alpha", "Total α"],
                ["total_tao", "Total τ"],
                ["ongoing_daily", "Daily α"],
                ["coronations", "Crowns"],
                ["slot_hours", "Slot hrs"],
                ["active_hours", "Active hrs"],
                ["weight", "Weight"],
                ["win_pct", "Win %"],
                ["owners", view === "coldkeys" ? "Repos" : "Owners"],
                ["name", "Name"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  if (sortBy === key) setSortDesc(!sortDesc);
                  else {
                    setSortBy(key);
                    setSortDesc(key !== "name");
                  }
                }}
                className={`px-1.5 py-0.5 rounded border ${
                  sortBy === key
                    ? "border-amber-500/50 bg-amber-500/10 text-amber-100"
                    : "border-zinc-800 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {label}
                {sortBy === key ? (sortDesc ? " ↓" : " ↑") : ""}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 pr-2 w-6" />
                  <th className="text-left py-1 pr-2">{view === "coldkeys" ? "Coldkey" : "Repo"}</th>
                  <th className="text-right py-1 px-1">Total α</th>
                  <th className="text-right py-1 px-1">Total τ</th>
                  <th className="text-right py-1 px-1">Daily α</th>
                  <th className="text-right py-1 px-1">👑</th>
                  <th className="text-right py-1 px-1">Slot</th>
                  <th className="text-right py-1 px-1">Weight</th>
                </tr>
              </thead>
              <tbody>
                {filteredRepos.slice(0, displayLimit).map((row) => {
                  const isOpen = expanded.has(row.key);
                  const linksForRepo =
                    view === "repos"
                      ? (analysis.repo_coldkey_links ?? []).filter((l) => l.repo === row.key)
                      : (analysis.repo_coldkey_links ?? []).filter((l) => l.coldkey === row.key);
                  return (
                    <Fragment key={row.key}>
                      <tr
                        className="border-b border-zinc-800/50 align-top hover:bg-zinc-800/20 cursor-pointer"
                        onClick={() => toggleExpand(row.key)}
                      >
                        <td className="py-1.5 pr-1 text-zinc-600">{isOpen ? "▼" : "▶"}</td>
                        <td className="py-1.5 pr-2">
                          <p className="text-zinc-200 truncate max-w-[200px]" title={row.label}>
                            {view === "coldkeys" ? shortAddr(row.label, 10) : shortRepo(row.label, 34)}
                          </p>
                          {view === "repos" && row.multi_owner && (
                            <span className="inline-block mt-0.5 text-[8px] px-1 rounded border border-sky-500/40 text-sky-300 bg-sky-500/10">
                              {row.owner_count} coldkeys
                            </span>
                          )}
                          {view === "coldkeys" && row.owner_count > 1 && (
                            <span className="inline-block mt-0.5 text-[8px] px-1 rounded border border-violet-500/40 text-violet-300 bg-violet-500/10">
                              {row.owner_count} repos
                            </span>
                          )}
                        </td>
                        <td className="text-right py-1.5 px-1 mono text-violet-300">{fmtAlpha(row.total_estimated_alpha)}</td>
                        <td className="text-right py-1.5 px-1 mono text-amber-300">{fmtTao(row.total_estimated_tao)}</td>
                        <td className="text-right py-1.5 px-1 mono text-emerald-300">{fmtAlpha(row.ongoing_daily_alpha)}</td>
                        <td className="text-right py-1.5 px-1 mono text-zinc-400">{row.coronations}</td>
                        <td className="text-right py-1.5 px-1 mono text-zinc-500">{fmtHours(row.total_slot_hours)}</td>
                        <td className="text-right py-1.5 px-1 mono text-zinc-500">
                          {row.current_weight_pct > 0 ? fmtPct(row.current_weight_pct) : "—"}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="border-b border-zinc-800/30 bg-zinc-900/40">
                          <td colSpan={8} className="py-2 px-3">
                            <div className="grid sm:grid-cols-2 gap-3 text-[9px]">
                              <div>
                                <p className="text-zinc-500 mb-1">
                                  {view === "repos" ? `Coldkeys (${linksForRepo.length})` : `Repos (${linksForRepo.length})`}
                                </p>
                                <ul className="space-y-1">
                                  {linksForRepo.map((link) => (
                                    <li key={`${link.repo}:${link.coldkey}`} className="flex justify-between gap-2">
                                      <span className="text-zinc-300" title={view === "repos" ? link.coldkey : link.repo}>
                                        {view === "repos" ? shortAddr(link.coldkey, 8) : shortRepo(link.repo, 22)}
                                        {link.in_reign && <span className="ml-1 text-amber-400">reign</span>}
                                      </span>
                                      <span className="mono text-zinc-500">
                                        {fmtAlpha(link.total_estimated_alpha)}
                                        {link.ongoing_daily_alpha ? ` · ${fmtAlpha(link.ongoing_daily_alpha)}/d` : ""}
                                      </span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                              <div>
                                <p className="text-zinc-500 mb-1">Crown history</p>
                                {(row.crown_events ?? []).slice(0, 4).map((ev) => (
                                  <p key={ev.king_version} className="mono text-zinc-500">
                                    v{ev.king_version} · {fmtAlpha(ev.estimated_alpha)} · {fmtHours(ev.slot_hours ?? 0)}
                                  </p>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          {filteredRepos.length > displayLimit && (
            <p className="text-[9px] text-zinc-600">
              Showing {displayLimit} of {filteredRepos.length} {view === "coldkeys" ? "coldkeys" : "repos"}
            </p>
          )}
        </>
      )}

      {view === "links" && (
        <>
          <div className="flex flex-wrap gap-1 text-[9px]">
            {(
              [
                ["total_alpha", "Total α"],
                ["total_tao", "Total τ"],
                ["coronations", "Crowns"],
                ["slot_hours", "Slot hrs"],
                ["active_hours", "Active hrs"],
                ["repo", "Repo"],
                ["coldkey", "Coldkey"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  if (linkSortBy === key) setLinkSortDesc(!linkSortDesc);
                  else {
                    setLinkSortBy(key);
                    setLinkSortDesc(key === "repo" || key === "coldkey" ? false : true);
                  }
                }}
                className={`px-1.5 py-0.5 rounded border ${
                  linkSortBy === key
                    ? "border-sky-500/50 bg-sky-500/10 text-sky-100"
                    : "border-zinc-800 text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {label}
                {linkSortBy === key ? (linkSortDesc ? " ↓" : " ↑") : ""}
              </button>
            ))}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 pr-2">Repo</th>
                  <th className="text-left py-1 pr-2">Coldkey</th>
                  <th className="text-right py-1 px-1">Total α</th>
                  <th className="text-right py-1 px-1">Daily α</th>
                  <th className="text-right py-1 px-1">👑</th>
                  <th className="text-right py-1 px-1">Slot</th>
                  <th className="text-left py-1 pl-2">Last crowned</th>
                </tr>
              </thead>
              <tbody>
                {filteredLinks.slice(0, displayLimit).map((link) => (
                  <tr key={`${link.repo}:${link.coldkey}`} className="border-b border-zinc-800/50">
                    <td className="py-1 pr-2 text-zinc-300 truncate max-w-[140px]" title={link.repo}>
                      {shortRepo(link.repo, 28)}
                    </td>
                    <td className="py-1 pr-2 text-zinc-400" title={link.coldkey}>
                      {shortAddr(link.coldkey, 8)}
                      {link.in_reign && <span className="ml-1 text-[8px] text-amber-400">reign</span>}
                    </td>
                    <td className="text-right py-1 px-1 mono text-violet-300">{fmtAlpha(link.total_estimated_alpha)}</td>
                    <td className="text-right py-1 px-1 mono text-emerald-300">{fmtAlpha(link.ongoing_daily_alpha)}</td>
                    <td className="text-right py-1 px-1 mono text-zinc-400">{link.coronations}</td>
                    <td className="text-right py-1 px-1 mono text-zinc-500">{fmtHours(link.total_slot_hours)}</td>
                    <td className="py-1 pl-2 text-zinc-500">{fmtTime(link.last_crowned_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {analysis.multi_owner_repos.length > 0 && !compact && (
        <div className="rounded border border-sky-500/25 bg-sky-500/5 px-2 py-1.5 text-[9px] text-sky-200/90">
          <span className="text-sky-400 font-medium">Multi-owner repos: </span>
          {analysis.multi_owner_repos.slice(0, 6).map((repo) => shortRepo(repo, 24)).join(" · ")}
          {analysis.multi_owner_repos.length > 6 && ` · +${analysis.multi_owner_repos.length - 6} more`}
        </div>
      )}
    </section>
  );
}
