"use client";

import { Fragment } from "react";
import { EntityNameCell } from "@/lib/entityLabels";
import {
  shortRepo,
  type AlbedoEntityJudgeStats,
  type AlbedoJudgeAnalytics,
  type AlbedoJudgeConsensus,
  type AlbedoJudgeDetail,
  type AlbedoJudgePairwise,
  type AlbedoJudgeSlice,
  type AlbedoMetricAggregate,
  type AlbedoRepoSubmissionStats,
} from "@/lib/api";

const JUDGE_COLORS: Record<string, string> = {
  "glm-5.1": "border-cyan-500/40 bg-cyan-500/10 text-cyan-200",
  "qwen3.5-397b-a17b": "border-violet-500/40 bg-violet-500/10 text-violet-200",
  "deepseek-v3.2": "border-amber-500/40 bg-amber-500/10 text-amber-200",
};

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function fmtScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function fmtMargin(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const pct = n * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function judgeStyle(shortName: string): string {
  return JUDGE_COLORS[shortName] ?? "border-zinc-700 bg-zinc-800/50 text-zinc-300";
}

function judgeShortLabel(name: string): string {
  if (name.startsWith("glm")) return "GLM";
  if (name.startsWith("qwen")) return "Qwen";
  if (name.startsWith("deepseek")) return "DS";
  return name.split("-")[0];
}

function sliceMap(slices: AlbedoJudgeSlice[]): Record<string, AlbedoJudgeSlice> {
  const map: Record<string, AlbedoJudgeSlice> = {};
  for (const s of slices) map[s.short_name] = s;
  return map;
}

function JudgeCard({ judge }: { judge: AlbedoJudgeDetail }) {
  return (
    <article className={`rounded-lg border p-3 ${judgeStyle(judge.short_name)}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="text-[12px] font-semibold">{judge.short_name}</h4>
          <p className="text-[9px] opacity-70 mt-0.5 truncate" title={judge.judge}>
            {judge.judge}
          </p>
        </div>
        <span className="text-[10px] mono opacity-80">{judge.duels} duels</span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-3 text-[10px]">
        <div>
          <p className="text-[9px] uppercase tracking-wide opacity-70">Avg challenger</p>
          <p className="font-semibold mt-0.5">{fmtScore(judge.avg_challenger_score)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wide opacity-70">Picks challenger</p>
          <p className="font-semibold mt-0.5">{fmtPct(judge.pick_challenger_pct)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wide opacity-70">Agrees w/ verdict</p>
          <p className="font-semibold mt-0.5">{fmtPct(judge.agree_verdict_pct)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wide opacity-70">Split-panel align</p>
          <p className="font-semibold mt-0.5">{fmtPct(judge.split_majority_align_pct)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wide opacity-70">When ch wins</p>
          <p className="font-semibold mt-0.5">{fmtScore(judge.avg_score_when_challenger_wins)}</p>
        </div>
        <div>
          <p className="text-[9px] uppercase tracking-wide opacity-70">When k wins</p>
          <p className="font-semibold mt-0.5">{fmtScore(judge.avg_score_when_king_wins)}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 mt-3 text-[9px]">
        <span className="rounded px-1.5 py-0.5 bg-black/20">overturns {judge.overturn_duels}</span>
        <span className="rounded px-1.5 py-0.5 bg-black/20">3–0 ch {judge.unanimous_challenger_duels}</span>
        <span className="rounded px-1.5 py-0.5 bg-black/20">0–3 k {judge.unanimous_king_duels}</span>
        <span className="rounded px-1.5 py-0.5 bg-black/20">split {judge.split_duels}</span>
      </div>
    </article>
  );
}

function ConsensusBar({
  rows,
}: {
  rows: { label: string; pct: number; duels: number; challenger_wins: number }[];
}) {
  const max = Math.max(...rows.map((r) => r.pct), 1);
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.label} className="text-[10px]">
          <div className="flex justify-between text-zinc-400 mb-0.5">
            <span>{row.label}</span>
            <span className="mono">
              {row.duels} · ch {row.challenger_wins}/{row.duels}
            </span>
          </div>
          <div className="h-2 rounded bg-zinc-800 overflow-hidden">
            <div className="h-full rounded bg-sky-500/70" style={{ width: `${(row.pct / max) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function PairwiseMatrix({
  judges,
  pairs,
}: {
  judges: string[];
  pairs: AlbedoJudgePairwise[];
}) {
  const lookup = new Map<string, AlbedoJudgePairwise>();
  for (const p of pairs) {
    lookup.set(`${p.short_name_a}|${p.short_name_b}`, p);
    lookup.set(`${p.short_name_b}|${p.short_name_a}`, p);
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px] min-w-[320px]">
        <thead>
          <tr className="text-zinc-500">
            <th className="text-left py-1 pr-2" />
            {judges.map((j) => (
              <th key={j} className={`text-center py-1 px-1 ${judgeStyle(j).split(" ")[2]}`}>
                {judgeShortLabel(j)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {judges.map((rowJ) => (
            <tr key={rowJ} className="border-t border-zinc-800/50">
              <td className={`py-1.5 pr-2 font-medium ${judgeStyle(rowJ).split(" ")[2]}`}>
                {judgeShortLabel(rowJ)}
              </td>
              {judges.map((colJ) => {
                if (rowJ === colJ) {
                  return (
                    <td key={colJ} className="py-1.5 px-1 text-center text-zinc-600 bg-zinc-800/30">
                      —
                    </td>
                  );
                }
                const pair = lookup.get(`${rowJ}|${colJ}`);
                if (!pair) {
                  return (
                    <td key={colJ} className="py-1.5 px-1 text-center text-zinc-700">
                      —
                    </td>
                  );
                }
                const intensity = Math.min(100, pair.agree_pct);
                return (
                  <td
                    key={colJ}
                    className="py-1.5 px-1 text-center mono"
                    style={{ backgroundColor: `rgba(52, 211, 153, ${intensity / 200})` }}
                    title={`${pair.duels} duels · Δ ${pair.avg_score_delta != null ? fmtScore(pair.avg_score_delta) : "—"} · r ${pair.score_correlation ?? "—"}`}
                  >
                    <div className="text-emerald-200">{fmtPct(pair.agree_pct)}</div>
                    <div className="text-[8px] text-zinc-500">r {pair.score_correlation ?? "—"}</div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[9px] text-zinc-600 mt-2">
        Cell = pick agreement % · r = score correlation · hover for delta
      </p>
    </div>
  );
}

function EntityJudgeTable({
  title,
  subtitle,
  rows,
  judgeOrder,
  groupBy,
  limit = 25,
}: {
  title: string;
  subtitle: string;
  rows: AlbedoEntityJudgeStats[];
  judgeOrder: string[];
  groupBy: "repo" | "coldkey";
  limit?: number;
}) {
  const visible = rows.slice(0, limit);
  if (!visible.length) {
    return (
      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200">{title}</h3>
        <p className="text-[10px] text-zinc-500 mt-2">No data yet.</p>
      </section>
    );
  }

  return (
    <section className="panel px-3 py-2">
      <h3 className="text-[11px] font-semibold text-zinc-200">{title}</h3>
      <p className="text-[9px] text-zinc-600 mt-0.5 mb-2">{subtitle}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-[10px] min-w-[720px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2 sticky left-0 bg-zinc-900/95">Miner</th>
              <th className="text-right py-1 px-1">Miners</th>
              <th className="text-right py-1 px-1">Duels</th>
              <th className="text-right py-1 px-1">Win%</th>
              <th className="text-right py-1 px-1">👑</th>
              <th className="text-right py-1 px-1">Margin</th>
              <th className="text-right py-1 px-1">Spread</th>
              <th className="text-right py-1 px-1">Unanimous</th>
              {judgeOrder.map((j) => (
                <th
                  key={j}
                  colSpan={3}
                  className={`text-center py-1 px-1 border-l border-zinc-800/50 ${judgeStyle(j).split(" ")[2]}`}
                >
                  {judgeShortLabel(j)}
                </th>
              ))}
            </tr>
            <tr className="text-zinc-600 border-b border-zinc-800/50 text-[9px]">
              <th className="sticky left-0 bg-zinc-900/95" />
              <th colSpan={7} />
              {judgeOrder.map((j) => (
                <Fragment key={`hdr-${j}`}>
                  <th className="text-right py-0.5 px-0.5 border-l border-zinc-800/30">avg</th>
                  <th className="text-right py-0.5 px-0.5">pick</th>
                  <th className="text-right py-0.5 px-0.5">align</th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const judges = sliceMap(row.judges);
              return (
                <tr key={row.key} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                  <td className="py-1 pr-2 sticky left-0 bg-zinc-900/90 truncate max-w-[200px]" title={row.label}>
                    <EntityNameCell
                      label={row.label}
                      repo={row.repo}
                      coldkey={row.coldkey}
                      coldkeys={row.coldkeys}
                      repos={row.repos}
                    />
                  </td>
                  <td className="text-right py-1 px-1 mono text-zinc-500">{row.miner_count || "—"}</td>
                  <td className="text-right py-1 px-1 mono text-zinc-400">{row.duels}</td>
                  <td className="text-right py-1 px-1 mono text-emerald-300">{fmtPct(row.win_pct)}</td>
                  <td className="text-right py-1 px-1 mono text-amber-300">{row.coronations || "—"}</td>
                  <td className="text-right py-1 px-1 mono text-zinc-500">{fmtMargin(row.avg_margin)}</td>
                  <td className="text-right py-1 px-1 mono text-zinc-500">{fmtScore(row.avg_judge_spread)}</td>
                  <td className="text-right py-1 px-1 mono text-zinc-500">{fmtPct(row.unanimous_pct)}</td>
                  {judgeOrder.map((j) => {
                    const s = judges[j];
                    if (!s) {
                      return (
                        <Fragment key={`${row.key}-${j}`}>
                          <td className="text-right py-1 px-0.5 border-l border-zinc-800/30 text-zinc-700">—</td>
                          <td className="text-right py-1 px-0.5 text-zinc-700">—</td>
                          <td className="text-right py-1 px-0.5 text-zinc-700">—</td>
                        </Fragment>
                      );
                    }
                    return (
                      <Fragment key={`${row.key}-${j}`}>
                        <td className="text-right py-1 px-0.5 mono border-l border-zinc-800/30 text-zinc-300">
                          {fmtScore(s.avg_challenger_score)}
                        </td>
                        <td className="text-right py-1 px-0.5 mono text-zinc-400">{fmtPct(s.pick_challenger_pct)}</td>
                        <td className="text-right py-1 px-0.5 mono text-sky-300">{fmtPct(s.agree_verdict_pct)}</td>
                      </Fragment>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function OutcomeComparison({
  slices,
  judgeOrder,
}: {
  slices: AlbedoJudgeAnalytics["by_outcome"];
  judgeOrder: string[];
}) {
  return (
    <div className="grid md:grid-cols-2 gap-3">
      {slices.map((slice) => (
        <div key={slice.outcome} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
          <h4 className="text-[11px] font-semibold text-zinc-200">
            {slice.label}
            <span className="text-zinc-500 font-normal ml-2">{slice.duels} duels</span>
          </h4>
          <table className="w-full text-[10px] mt-2">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1">Judge</th>
                <th className="text-right py-1 px-1">Avg ch</th>
                <th className="text-right py-1 px-1">Pick ch</th>
                <th className="text-right py-1 pl-1">Align</th>
              </tr>
            </thead>
            <tbody>
              {judgeOrder.map((j) => {
                const row = slice.judges.find((s) => s.short_name === j);
                if (!row) return null;
                return (
                  <tr key={j} className="border-b border-zinc-800/40">
                    <td className={`py-1 ${judgeStyle(j).split(" ")[2]}`}>{judgeShortLabel(j)}</td>
                    <td className="text-right py-1 px-1 mono text-zinc-300">{fmtScore(row.avg_challenger_score)}</td>
                    <td className="text-right py-1 px-1 mono text-zinc-400">{fmtPct(row.pick_challenger_pct)}</td>
                    <td className="text-right py-1 pl-1 mono text-emerald-300">{fmtPct(row.agree_verdict_pct)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function RepoDqStatsTable({ rows }: { rows: AlbedoRepoSubmissionStats[] }) {
  if (!rows.length) return null;
  return (
    <section className="panel px-3 py-2">
      <h3 className="text-[11px] font-semibold text-zinc-200">Committed-repo DQ rate</h3>
      <p className="text-[9px] text-zinc-600 mt-0.5 mb-2">
        Disqualification rate per on-chain committed repo (registry/commitments only — not Hippius model paths).
        DQ% = recent DQ ÷ (completed evals + recent DQ).
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-[10px] min-w-[520px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">Miner</th>
              <th className="text-right py-1 px-1">Evals</th>
              <th className="text-right py-1 px-1">DQ</th>
              <th className="text-right py-1 px-1">Attempts</th>
              <th className="text-right py-1 pl-1">DQ%</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 20).map((row) => (
              <tr key={row.key} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                <td className="py-1 pr-2 truncate max-w-[220px]" title={row.label}>
                  <EntityNameCell label={row.label} repo={row.repo} coldkeys={row.coldkeys} />
                </td>
                <td className="text-right py-1 px-1 mono text-zinc-400">{row.eval_submissions}</td>
                <td className="text-right py-1 px-1 mono text-rose-300">{row.recent_dq}</td>
                <td className="text-right py-1 px-1 mono text-zinc-500">{row.total_attempts}</td>
                <td className="text-right py-1 pl-1 mono text-rose-300/90">{fmtPct(row.dq_rate_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AlbedoJudgeAnalysisPanel({
  analytics,
  judgeDetails,
  judgeConsensus,
  metricAggregates,
  repoSubmissionStats = [],
}: {
  analytics: AlbedoJudgeAnalytics;
  judgeDetails: AlbedoJudgeDetail[];
  judgeConsensus: AlbedoJudgeConsensus[];
  metricAggregates: AlbedoMetricAggregate[];
  repoSubmissionStats?: AlbedoRepoSubmissionStats[];
}) {
  const judgeOrder =
    judgeDetails.length > 0
      ? judgeDetails.map((j) => j.short_name)
      : analytics.judge_models.map((j) => j.split("/").pop() ?? j);

  const spread = analytics.spread_summary;

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2.5">
        <h3 className="text-[11px] font-semibold text-zinc-200">Judge panel summary</h3>
        <p className="text-[9px] text-zinc-600 mt-0.5 mb-3">
          {analytics.total_submissions} evaluated submissions · aggregated by repo and coldkey (min 2 duels)
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
          {[
            { label: "Submissions", value: String(analytics.total_submissions) },
            { label: "Avg judge spread", value: fmtScore(spread.avg_spread) },
            { label: "High spread (≥15%)", value: `${spread.high_spread_duels} (${fmtPct(spread.high_spread_pct)})` },
            { label: "Unanimous panels", value: `${spread.unanimous_duels} (${fmtPct(spread.unanimous_pct)})` },
            { label: "Split panels", value: `${spread.split_duels} (${fmtPct(spread.split_pct)})` },
            { label: "Judges tracked", value: String(judgeOrder.length) },
          ].map((kpi) => (
            <div key={kpi.label} className="rounded border border-zinc-800 bg-zinc-900/50 px-2 py-1.5">
              <p className="text-[9px] uppercase tracking-wide text-zinc-500">{kpi.label}</p>
              <p className="text-[12px] font-semibold text-zinc-100 mt-0.5">{kpi.value}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="panel px-3 py-2.5">
        <h3 className="text-[11px] font-semibold text-zinc-200 mb-3">Per-judge ensemble stats</h3>
        <div className="grid md:grid-cols-3 gap-3">
          {judgeDetails.map((j) => (
            <JudgeCard key={j.judge} judge={j} />
          ))}
        </div>
      </section>

      <div className="grid lg:grid-cols-2 gap-3">
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Judge pairwise relations</h3>
          <p className="text-[9px] text-zinc-600 mb-2">Pick agreement and score correlation between judges</p>
          <PairwiseMatrix judges={judgeOrder} pairs={analytics.pairwise} />
        </section>
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Panel consensus patterns</h3>
          <ConsensusBar
            rows={(judgeConsensus ?? []).map((c) => ({
              label: c.label,
              pct: c.pct,
              duels: c.duels,
              challenger_wins: c.challenger_wins,
            }))}
          />
        </section>
      </div>

      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Judge behavior by final outcome</h3>
        <p className="text-[9px] text-zinc-600 mb-2">How each judge scores when challenger wins vs king defends</p>
        <OutcomeComparison slices={analytics.by_outcome} judgeOrder={judgeOrder} />
      </section>

      <RepoDqStatsTable rows={repoSubmissionStats} />

      <EntityJudgeTable
        title="Per-repo judge analysis"
        subtitle="Repo name with coldkey — win rate, DQ%, GLM · Qwen · DeepSeek splits"
        rows={analytics.by_repo}
        judgeOrder={judgeOrder}
        groupBy="repo"
      />

      <EntityJudgeTable
        title="Per-coldkey judge analysis"
        subtitle="Primary repo(s) with coldkey — spans hotkeys under same owner"
        rows={analytics.by_coldkey}
        judgeOrder={judgeOrder}
        groupBy="coldkey"
      />

      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Scoring metrics (challenger avg)</h3>
        <div className="space-y-1.5">
          {(metricAggregates ?? []).map((m) => (
            <div key={m.metric} className="flex items-center gap-2 text-[10px]">
              <span className="w-20 text-zinc-400 capitalize">{m.metric}</span>
              <div className="flex-1 h-2 rounded bg-zinc-800 overflow-hidden">
                <div
                  className="h-full rounded bg-violet-500/60"
                  style={{ width: `${m.avg_challenger_score * 100}%` }}
                />
              </div>
              <span className="w-10 text-right mono text-zinc-300">{fmtScore(m.avg_challenger_score)}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
