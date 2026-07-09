"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import {
  api,
  type AlbedoSampleScoreAnalysis,
  type GapDiffBin,
  type GapTypeSummary,
  type SampleGapBucket,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const GAP_COLORS: Record<SampleGapBucket, { bar: string; text: string; border: string; bg: string }> = {
  close: { bar: "bg-sky-500", text: "text-sky-200", border: "border-sky-500/30", bg: "bg-sky-500/10" },
  moderate: { bar: "bg-amber-500", text: "text-amber-200", border: "border-amber-500/30", bg: "bg-amber-500/10" },
  decisive: { bar: "bg-rose-500", text: "text-rose-200", border: "border-rose-500/30", bg: "bg-rose-500/10" },
};

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

function fmtTime(iso: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Stat({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="text-[13px] font-semibold text-zinc-100 mt-0.5">{value}</p>
      {sub && <p className="text-[9px] text-zinc-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function MarginStackBar({ types }: { types: GapTypeSummary[] }) {
  const active = types.filter((t) => t.margin_share_pct > 0);
  if (active.length === 0) {
    return <div className="h-3 rounded bg-zinc-800" />;
  }
  return (
    <div className="space-y-2">
      <div className="flex h-3 rounded overflow-hidden bg-zinc-800">
        {active.map((t) => (
          <div
            key={t.gap_type}
            className={`${GAP_COLORS[t.gap_type].bar} opacity-90`}
            style={{ width: `${t.margin_share_pct}%` }}
            title={`${t.label}: ${fmtPct(t.margin_share_pct)} of margin`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-zinc-500">
        {types.map((t) => (
          <span key={t.gap_type} className="flex items-center gap-1.5">
            <span className={`inline-block w-2 h-2 rounded-sm ${GAP_COLORS[t.gap_type].bar}`} />
            <span className={GAP_COLORS[t.gap_type].text}>{t.gap_type}</span>
            <span className="mono text-zinc-400">{fmtPct(t.margin_share_pct)}</span>
            <span className="text-zinc-600">· {t.total_gap_points.toFixed(0)} pt</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function GapHistogram({ bins, gapType }: { bins: GapDiffBin[]; gapType: SampleGapBucket }) {
  const active = bins.filter((b) => b.gap_points_sum > 0);
  if (active.length === 0) {
    return <p className="text-[9px] text-zinc-600 py-2">No margin in this type</p>;
  }
  const maxShare = Math.max(...active.map((b) => b.share_within_type_pct), 1);
  return (
    <div className="space-y-1.5">
      {active.map((bin) => (
        <div key={bin.label} className="grid grid-cols-[72px_1fr_52px_52px] gap-2 items-center text-[9px]">
          <span className="text-zinc-500 truncate" title={bin.label}>
            {bin.label}
          </span>
          <div className="h-2 rounded bg-zinc-800 overflow-hidden">
            <div
              className={`h-full ${GAP_COLORS[gapType].bar} opacity-80`}
              style={{ width: `${(bin.share_within_type_pct / maxShare) * 100}%` }}
            />
          </div>
          <span className="text-right mono text-zinc-400" title="Within type">
            {fmtPct(bin.share_within_type_pct)}
          </span>
          <span className="text-right mono text-amber-200/90" title="Of total margin">
            {fmtPct(bin.share_of_total_margin_pct)}
          </span>
        </div>
      ))}
      <div className="grid grid-cols-[72px_1fr_52px_52px] gap-2 text-[8px] text-zinc-600 pt-0.5">
        <span />
        <span>Score-diff bin</span>
        <span className="text-right">In type</span>
        <span className="text-right">Of margin</span>
      </div>
    </div>
  );
}

function GapTypeCard({ summary }: { summary: GapTypeSummary }) {
  const c = GAP_COLORS[summary.gap_type];
  return (
    <article className={`rounded-lg border ${c.border} ${c.bg} px-3 py-2.5 flex flex-col min-h-0`}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <h4 className={`text-[11px] font-semibold capitalize ${c.text}`}>{summary.gap_type}</h4>
          <p className="text-[9px] text-zinc-500 mt-0.5 leading-snug">{summary.criteria}</p>
        </div>
        <div className="text-right shrink-0">
          <p className={`text-[15px] font-bold mono ${c.text}`}>{fmtPct(summary.margin_share_pct)}</p>
          <p className="text-[8px] text-zinc-600">of total margin</p>
        </div>
      </div>
      <div className="flex gap-3 text-[9px] mb-2">
        <span className="text-zinc-500">
          Σ gap <span className="mono text-zinc-300">{summary.total_gap_points.toFixed(0)}</span>
        </span>
        <span className="text-zinc-500">
          avg <span className="mono text-zinc-300">{summary.avg_gap.toFixed(1)} pt</span>
        </span>
      </div>
      <GapHistogram bins={summary.gap_distribution} gapType={summary.gap_type} />
    </article>
  );
}

export default function AlbedoSampleScoreAnalysisPanel() {
  const { subnet } = useSubnet();
  const [data, setData] = useState<AlbedoSampleScoreAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDuel, setExpandedDuel] = useState<string | null>(null);
  const [expandedJudge, setExpandedJudge] = useState<string | null>(null);

  const load = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    try {
      const result = await api.getAlbedoSampleScoreAnalysis(subnet, forceRefresh);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load sample score analysis");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [subnet]);

  useEffect(() => {
    void load(false);
  }, [load]);

  if (loading && !data) {
    return <div className="panel p-4 text-[10px] text-zinc-500">Analyzing per-sample judge scores…</div>;
  }
  if (error && !data) {
    return <div className="panel p-4 text-[10px] text-rose-300">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-[11px] font-semibold text-zinc-200">Sample score margin analysis</h3>
            <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
              Per sample × judge rubric pass-rate gap. Three gap types partition every observation;
              charts show how each type&apos;s score-difference bins contribute to total margin (gap
              points), not observation counts.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={loading}
            className="rounded border border-zinc-700 bg-zinc-900/60 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800/80 disabled:opacity-50 shrink-0"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-3">
          <Stat label="Binary duels" value={data.binary_duels_total} />
          <Stat label="Scanned" value={data.binary_duels_scanned} />
          <Stat label="With samples" value={data.binary_duels_with_samples} />
          <Stat label="Samples" value={data.total_samples} />
          <Stat label="Observations" value={data.total_observations} sub={`${data.judge_models.length} judges`} />
          <Stat label="Total margin" value={data.total_gap_points.toFixed(0)} sub="Σ gap points" />
        </div>

        <div className="mt-4 pt-3 border-t border-zinc-800/80">
          <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-2">Margin by gap type</p>
          <MarginStackBar types={data.gap_types} />
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {data.gap_types.map((t) => (
          <GapTypeCard key={t.gap_type} summary={t} />
        ))}
      </section>

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge margin share</h4>
        <p className="text-[9px] text-zinc-600 mb-2">
          Each judge&apos;s contribution to total gap points, expandable by gap type.
        </p>
        <table className="w-full text-[10px] min-w-[640px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">Judge</th>
              <th className="text-right py-1 px-1">Σ gap</th>
              <th className="text-right py-1 px-1">% margin</th>
              <th className="text-left py-1 pl-2 min-w-[120px]">Share</th>
              <th className="text-right py-1 px-1">Avg gap</th>
              <th className="text-right py-1 px-1">Pick ch%</th>
              <th className="text-left py-1 pl-2">By type</th>
            </tr>
          </thead>
          <tbody>
            {data.judge_margin_shares.map((j) => {
              const open = expandedJudge === j.judge_model;
              return (
                <Fragment key={j.judge_model}>
                  <tr className="border-b border-zinc-800/50">
                    <td className="py-1.5 pr-2 font-medium text-zinc-200">{j.short_name}</td>
                    <td className="text-right py-1.5 px-1 mono text-zinc-300">{j.total_gap_points.toFixed(0)}</td>
                    <td className="text-right py-1.5 px-1 mono text-amber-200 font-semibold">
                      {fmtPct(j.gap_share_pct)}
                    </td>
                    <td className="py-1.5 pl-2">
                      <div className="h-2 rounded bg-zinc-800 overflow-hidden">
                        <div className="h-full bg-violet-500/80" style={{ width: `${j.gap_share_pct}%` }} />
                      </div>
                    </td>
                    <td className="text-right py-1.5 px-1 mono text-zinc-400">{j.avg_gap.toFixed(1)}</td>
                    <td className="text-right py-1.5 px-1 mono text-zinc-400">{fmtPct(j.pick_challenger_pct)}</td>
                    <td className="py-1.5 pl-2">
                      <button
                        type="button"
                        onClick={() => setExpandedJudge(open ? null : j.judge_model)}
                        className="text-[9px] text-sky-400 hover:underline"
                      >
                        {open ? "hide" : "expand"}
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-zinc-800/50 bg-zinc-900/40">
                      <td colSpan={7} className="py-2 px-2">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                          {j.by_gap_type.map((t) => (
                            <div
                              key={t.gap_type}
                              className={`rounded border ${GAP_COLORS[t.gap_type].border} px-2 py-1.5`}
                            >
                              <p className={`text-[9px] font-medium capitalize ${GAP_COLORS[t.gap_type].text}`}>
                                {t.gap_type} · {fmtPct(t.margin_share_pct)} margin
                              </p>
                              <GapHistogram bins={t.gap_distribution} gapType={t.gap_type} />
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">By judge (averages)</h4>
        <table className="w-full text-[10px] min-w-[560px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">Judge</th>
              <th className="text-right py-1 px-1">Obs</th>
              <th className="text-right py-1 px-1">Avg ch%</th>
              <th className="text-right py-1 px-1">Avg k%</th>
              <th className="text-right py-1 px-1">Avg gap</th>
              <th className="text-right py-1 px-1">% margin</th>
              <th className="text-right py-1 px-1">Pick ch%</th>
            </tr>
          </thead>
          <tbody>
            {data.by_judge.map((j) => (
              <tr key={j.judge_model} className="border-b border-zinc-800/50">
                <td className="py-1.5 pr-2">
                  <div className="font-medium text-zinc-200">{j.short_name}</div>
                  <div className="text-[9px] text-zinc-600 truncate max-w-[140px]" title={j.judge_model}>
                    {j.judge_model}
                  </div>
                </td>
                <td className="text-right py-1.5 px-1 mono text-zinc-400">{j.observations}</td>
                <td className="text-right py-1.5 px-1 mono text-rose-200">{j.avg_challenger_pct.toFixed(1)}</td>
                <td className="text-right py-1.5 px-1 mono text-emerald-200">{j.avg_king_pct.toFixed(1)}</td>
                <td className="text-right py-1.5 px-1 mono text-zinc-300">{j.avg_gap_pct.toFixed(1)}</td>
                <td className="text-right py-1.5 px-1 mono text-amber-200">{fmtPct(j.gap_share_pct)}</td>
                <td className="text-right py-1.5 px-1 mono text-zinc-300">{fmtPct(j.pick_challenger_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {data.judge_pairs.length > 0 && (
        <section className="panel px-3 py-2.5 overflow-x-auto">
          <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge agreement</h4>
          <p className="text-[9px] text-zinc-600 mb-2">Same gap type / same pick on shared samples.</p>
          <table className="w-full text-[10px] min-w-[480px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">Pair</th>
                <th className="text-right py-1 px-1">Samples</th>
                <th className="text-right py-1 px-1">Same type</th>
                <th className="text-right py-1 px-1">Same pick</th>
                <th className="text-right py-1 px-1">Avg ch Δ</th>
              </tr>
            </thead>
            <tbody>
              {data.judge_pairs.map((p) => (
                <tr key={`${p.judge_a}-${p.judge_b}`} className="border-b border-zinc-800/50">
                  <td className="py-1.5 pr-2 text-zinc-300">
                    {p.short_name_a} · {p.short_name_b}
                  </td>
                  <td className="text-right py-1.5 px-1 mono text-zinc-400">{p.observations}</td>
                  <td className="text-right py-1.5 px-1 mono text-sky-300">{fmtPct(p.same_bucket_pct)}</td>
                  <td className="text-right py-1.5 px-1 mono text-emerald-300">{fmtPct(p.same_pick_pct)}</td>
                  <td className="text-right py-1.5 px-1 mono text-zinc-400">{p.avg_score_delta_pct.toFixed(1)} pt</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">Per duel</h4>
        <table className="w-full text-[10px] min-w-[720px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">When</th>
              <th className="text-left py-1 pr-2">Matchup</th>
              <th className="text-left py-1 pr-2">Result</th>
              <th className="text-right py-1 px-1">Margin</th>
              <th className="text-left py-1 pl-2 min-w-[140px]">Type mix</th>
              <th className="text-left py-1 pl-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {data.duels.map((duel) => {
              const open = expandedDuel === duel.eval_run_id;
              return (
                <Fragment key={duel.eval_run_id}>
                  <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(duel.finished_at)}</td>
                    <td className="py-1.5 pr-2 text-zinc-300">
                      {duel.challenger_label} vs {duel.king_label}
                    </td>
                    <td className="py-1.5 pr-2 capitalize text-zinc-400">{duel.winner}</td>
                    <td className="text-right py-1.5 px-1 mono text-zinc-300">{duel.total_gap_points.toFixed(0)}</td>
                    <td className="py-1.5 pl-2">
                      <MarginStackBar types={duel.gap_types} />
                    </td>
                    <td className="py-1.5 pl-2">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedDuel((prev) => (prev === duel.eval_run_id ? null : duel.eval_run_id))
                        }
                        className="text-[9px] text-sky-400 hover:underline"
                      >
                        {open ? "hide" : "expand"}
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-zinc-800/50 bg-zinc-900/30">
                      <td colSpan={6} className="py-2 px-2 space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                          {duel.gap_types.map((t) => (
                            <GapTypeCard key={t.gap_type} summary={t} />
                          ))}
                        </div>
                        <div>
                          <p className="text-[9px] text-zinc-500 mb-1">Judge margin in this duel</p>
                          <table className="w-full text-[9px]">
                            <thead>
                              <tr className="text-zinc-600">
                                <th className="text-left py-0.5">Judge</th>
                                <th className="text-right py-0.5">% margin</th>
                                <th className="text-right py-0.5">Σ gap</th>
                                <th className="text-right py-0.5">Avg gap</th>
                              </tr>
                            </thead>
                            <tbody>
                              {duel.judge_margin_shares.map((j) => (
                                <tr key={j.judge_model}>
                                  <td className="py-0.5 text-zinc-400">{j.short_name}</td>
                                  <td className="text-right py-0.5 mono text-amber-300">{fmtPct(j.gap_share_pct)}</td>
                                  <td className="text-right py-0.5 mono">{j.total_gap_points.toFixed(0)}</td>
                                  <td className="text-right py-0.5 mono">{j.avg_gap.toFixed(1)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </section>
    </div>
  );
}
