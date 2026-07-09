"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { api, type AlbedoSampleScoreAnalysis, type GapBucketDistribution } from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

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

function DistributionBar({ dist, compact = false }: { dist: GapBucketDistribution; compact?: boolean }) {
  const total = dist.counts.total || 1;
  const segments = [
    { key: "close", pct: dist.close_pct, count: dist.counts.close, color: "bg-sky-500" },
    { key: "moderate", pct: dist.moderate_pct, count: dist.counts.moderate, color: "bg-amber-500" },
    { key: "decisive", pct: dist.decisive_pct, count: dist.counts.decisive, color: "bg-rose-500" },
  ];
  return (
    <div className={compact ? "space-y-1" : "space-y-2"}>
      <div className="flex h-2.5 rounded overflow-hidden bg-zinc-800">
        {segments.map((s) =>
          s.count > 0 ? (
            <div
              key={s.key}
              className={`${s.color} opacity-90`}
              style={{ width: `${(s.count / total) * 100}%` }}
              title={`${s.key}: ${s.count} (${fmtPct(s.pct)})`}
            />
          ) : null
        )}
      </div>
      {!compact && (
        <div className="flex flex-wrap gap-3 text-[9px] text-zinc-500">
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm bg-sky-500" />
            Close ≤20 ({dist.counts.close})
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm bg-amber-500" />
            Moderate 20–50 ({dist.counts.moderate})
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded-sm bg-rose-500" />
            Decisive &gt;50 &amp; &gt;90% ({dist.counts.decisive})
          </span>
        </div>
      )}
    </div>
  );
}

export default function AlbedoSampleScoreAnalysisPanel() {
  const { subnet } = useSubnet();
  const [data, setData] = useState<AlbedoSampleScoreAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedDuel, setExpandedDuel] = useState<string | null>(null);

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
            <h3 className="text-[11px] font-semibold text-zinc-200">Sample score gap analysis</h3>
            <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
              Per sample × judge: rubric pass-rate (0–100%) for challenger vs king. Buckets by point
              gap — close ≤20, moderate 20–50 (or wide low-confidence), decisive &gt;50 with leader
              &gt;90%. All binary-rubric duels with scoring artifacts.
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
          <Stat
            label="Observations"
            value={data.total_observations}
            sub={`${data.judge_models.length} judges`}
          />
          <Stat label="Updated" value={fmtTime(data.updated_at ?? "")} />
        </div>
      </section>

      <section className="panel px-3 py-2.5">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">Overall distribution</h4>
        <DistributionBar dist={data.overall} />
        <div className="grid grid-cols-3 gap-2 mt-3 text-center">
          <div className="rounded border border-sky-500/25 bg-sky-500/10 px-2 py-1.5">
            <p className="text-[9px] text-zinc-500">Close</p>
            <p className="text-[14px] font-semibold text-sky-200">{fmtPct(data.overall.close_pct)}</p>
          </div>
          <div className="rounded border border-amber-500/25 bg-amber-500/10 px-2 py-1.5">
            <p className="text-[9px] text-zinc-500">Moderate</p>
            <p className="text-[14px] font-semibold text-amber-200">{fmtPct(data.overall.moderate_pct)}</p>
          </div>
          <div className="rounded border border-rose-500/25 bg-rose-500/10 px-2 py-1.5">
            <p className="text-[9px] text-zinc-500">Decisive</p>
            <p className="text-[14px] font-semibold text-rose-200">{fmtPct(data.overall.decisive_pct)}</p>
          </div>
        </div>
      </section>

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">By judge model</h4>
        <table className="w-full text-[10px] min-w-[720px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">Judge</th>
              <th className="text-right py-1 px-1">Obs</th>
              <th className="text-right py-1 px-1">Avg ch%</th>
              <th className="text-right py-1 px-1">Avg k%</th>
              <th className="text-right py-1 px-1">Avg gap</th>
              <th className="text-right py-1 px-1">Pick ch%</th>
              <th className="text-left py-1 pl-2 min-w-[180px]">Distribution</th>
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
                <td className="text-right py-1.5 px-1 mono text-zinc-300">{fmtPct(j.pick_challenger_pct)}</td>
                <td className="py-1.5 pl-2">
                  <DistributionBar dist={j.distribution} compact />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {data.judge_pairs.length > 0 && (
        <section className="panel px-3 py-2.5 overflow-x-auto">
          <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge agreement (per sample)</h4>
          <p className="text-[9px] text-zinc-600 mb-2">
            Same bucket / same pick when both judges scored the same sample.
          </p>
          <table className="w-full text-[10px] min-w-[480px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">Pair</th>
                <th className="text-right py-1 px-1">Samples</th>
                <th className="text-right py-1 px-1">Same bucket</th>
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
                  <td className="text-right py-1.5 px-1 mono text-zinc-400">
                    {p.avg_score_delta_pct.toFixed(1)} pt
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">Per duel summary</h4>
        <table className="w-full text-[10px] min-w-[800px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">When</th>
              <th className="text-left py-1 pr-2">Matchup</th>
              <th className="text-left py-1 pr-2">Result</th>
              <th className="text-right py-1 px-1">Samples</th>
              <th className="text-right py-1 px-1">Obs</th>
              <th className="text-left py-1 pl-2 min-w-[160px]">Gap mix</th>
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
                    <td className="text-right py-1.5 px-1 mono text-zinc-400">{duel.sample_count}</td>
                    <td className="text-right py-1.5 px-1 mono text-zinc-400">{duel.observations}</td>
                    <td className="py-1.5 pl-2">
                      <DistributionBar dist={duel.distribution} compact />
                    </td>
                    <td className="py-1.5 pl-2">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedDuel((prev) => (prev === duel.eval_run_id ? null : duel.eval_run_id))
                        }
                        className="text-[9px] text-sky-400 hover:underline"
                      >
                        {open ? "hide judges" : "by judge"}
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-zinc-800/50 bg-zinc-900/30">
                      <td colSpan={7} className="py-2 px-2">
                        <table className="w-full text-[9px]">
                          <thead>
                            <tr className="text-zinc-600">
                              <th className="text-left py-0.5">Judge</th>
                              <th className="text-right py-0.5">Obs</th>
                              <th className="text-right py-0.5">Close</th>
                              <th className="text-right py-0.5">Mod</th>
                              <th className="text-right py-0.5">Dec</th>
                              <th className="text-right py-0.5">Avg gap</th>
                            </tr>
                          </thead>
                          <tbody>
                            {duel.judges.map((j) => (
                              <tr key={j.judge_model}>
                                <td className="py-0.5 text-zinc-400">{j.short_name}</td>
                                <td className="text-right py-0.5 mono">{j.observations}</td>
                                <td className="text-right py-0.5 mono text-sky-300">
                                  {fmtPct(j.distribution.close_pct)}
                                </td>
                                <td className="text-right py-0.5 mono text-amber-300">
                                  {fmtPct(j.distribution.moderate_pct)}
                                </td>
                                <td className="text-right py-0.5 mono text-rose-300">
                                  {fmtPct(j.distribution.decisive_pct)}
                                </td>
                                <td className="text-right py-0.5 mono">{j.avg_gap_pct.toFixed(1)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
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
