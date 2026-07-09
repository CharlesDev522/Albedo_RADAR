"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type AlbedoSampleScoreAnalysis,
  type GapTypeSummary,
  type SampleGapBucket,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const GAP_COLORS: Record<SampleGapBucket, { bar: string; text: string; border: string; bg: string }> = {
  close: { bar: "bg-sky-500", text: "text-sky-200", border: "border-sky-500/30", bg: "bg-sky-500/10" },
  moderate: { bar: "bg-amber-500", text: "text-amber-200", border: "border-amber-500/30", bg: "bg-amber-500/10" },
  decisive: { bar: "bg-rose-500", text: "text-rose-200", border: "border-rose-500/30", bg: "bg-rose-500/10" },
};

type MarginRow = {
  key: string;
  label: string;
  gapType: SampleGapBucket;
  sharePct: number;
  gapPoints: number;
  depth: 0 | 1;
};

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
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

function flattenMarginRows(types: GapTypeSummary[]): MarginRow[] {
  const rows: MarginRow[] = [];
  for (const t of types) {
    rows.push({
      key: `type-${t.gap_type}`,
      label: t.gap_type,
      gapType: t.gap_type,
      sharePct: t.share_pct,
      gapPoints: t.total_gap_points,
      depth: 0,
    });
    for (const bin of t.gap_distribution ?? []) {
      if (bin.share_pct <= 0 && bin.gap_points_sum <= 0) continue;
      rows.push({
        key: `bin-${t.gap_type}-${bin.label}`,
        label: bin.label,
        gapType: t.gap_type,
        sharePct: bin.share_pct,
        gapPoints: bin.gap_points_sum,
        depth: 1,
      });
    }
  }
  return rows;
}

function ShareBar({ sharePct, colorClass, height = "h-2" }: { sharePct: number; colorClass: string; height?: string }) {
  return (
    <div className={`${height} rounded bg-zinc-800 overflow-hidden`}>
      <div className={`h-full ${colorClass} opacity-85`} style={{ width: `${Math.min(sharePct, 100)}%` }} />
    </div>
  );
}

function TotalStackBar({ types }: { types: GapTypeSummary[] }) {
  const active = types.filter((t) => t.share_pct > 0);
  if (active.length === 0) return <div className="h-4 rounded bg-zinc-800" />;
  return (
    <div className="space-y-2">
      <div className="flex h-4 rounded overflow-hidden bg-zinc-800">
        {active.map((t) => (
          <div
            key={t.gap_type}
            className={`${GAP_COLORS[t.gap_type].bar}`}
            style={{ width: `${t.share_pct}%` }}
            title={`${t.gap_type}: ${fmtPct(t.share_pct)}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-3 text-[9px]">
        {types.map((t) => (
          <span key={t.gap_type} className="flex items-center gap-1.5 text-zinc-500">
            <span className={`w-2 h-2 rounded-sm ${GAP_COLORS[t.gap_type].bar}`} />
            <span className={`capitalize ${GAP_COLORS[t.gap_type].text}`}>{t.gap_type}</span>
            <span className="mono text-zinc-300">{fmtPct(t.share_pct)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function MarginBreakdownTable({
  title,
  subtitle,
  types,
  embedded = false,
}: {
  title: string;
  subtitle?: string;
  types: GapTypeSummary[];
  embedded?: boolean;
}) {
  const rows = useMemo(() => flattenMarginRows(types), [types]);
  const visible = rows.filter((r) => r.sharePct > 0 || r.gapPoints > 0);
  if (visible.length === 0) return null;

  const table = (
    <>
      <h4 className="text-[11px] font-semibold text-zinc-200">{title}</h4>
      {subtitle && <p className="text-[9px] text-zinc-600 mb-2">{subtitle}</p>}
      <table className="w-full text-[10px] min-w-[480px]">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left py-1 pr-2">Segment</th>
            <th className="text-right py-1 px-1 w-16">% total</th>
            <th className="text-right py-1 px-1 w-16">Gap pt</th>
            <th className="text-left py-1 pl-2 min-w-[140px]">Share of 100%</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => (
            <tr key={row.key} className="border-b border-zinc-800/50">
              <td className={`py-1.5 pr-2 ${row.depth === 0 ? "font-medium capitalize" : "pl-4 text-zinc-400"}`}>
                <span className={row.depth === 0 ? GAP_COLORS[row.gapType].text : ""}>{row.label}</span>
              </td>
              <td className="text-right py-1.5 px-1 mono text-amber-200">{fmtPct(row.sharePct)}</td>
              <td className="text-right py-1.5 px-1 mono text-zinc-400">{row.gapPoints.toFixed(0)}</td>
              <td className="py-1.5 pl-2">
                <ShareBar sharePct={row.sharePct} colorClass={GAP_COLORS[row.gapType].bar} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );

  if (embedded) {
    return <div className="overflow-x-auto">{table}</div>;
  }
  return <section className="panel px-3 py-2.5 overflow-x-auto">{table}</section>;
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

  const gapTypes = data.gap_types ?? [];
  const judgeMarginShares = data.judge_margin_shares ?? [];
  const judgePairs = data.judge_pairs ?? [];
  const duels = data.duels ?? [];
  const needsApiRebuild = gapTypes.length === 0 && data.total_gap_points > 0 && data.total_observations > 0;
  const typeShareSum = gapTypes.reduce((sum, t) => sum + t.share_pct, 0);

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-[11px] font-semibold text-zinc-200">Score margin breakdown</h3>
            <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
              Every number is a share of the same whole: <strong className="text-zinc-400 font-normal">100% = all gap points</strong>{" "}
              ({data.total_gap_points.toFixed(0)} pt across sample × judge observations). Types and score-diff bins
              use the same scale and sum to 100%.
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

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 text-[10px]">
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Total score</p>
            <p className="text-[16px] font-bold text-zinc-100">100%</p>
            <p className="text-[9px] text-zinc-600">{data.total_gap_points.toFixed(0)} gap points</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Observations</p>
            <p className="text-[14px] font-semibold text-zinc-200">{data.total_observations}</p>
            <p className="text-[9px] text-zinc-600">{data.judge_models.length} judges · {data.total_samples} samples</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Binary duels</p>
            <p className="text-[14px] font-semibold text-zinc-200">{data.binary_duels_with_samples}</p>
            <p className="text-[9px] text-zinc-600">{data.binary_duels_scanned} scanned</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Type check</p>
            <p className="text-[14px] font-semibold text-zinc-200">{fmtPct(typeShareSum)}</p>
            <p className="text-[9px] text-zinc-600">close + moderate + decisive</p>
          </div>
        </div>

        <div className="mt-4 pt-3 border-t border-zinc-800/80">
          <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-2">100% split by gap type</p>
          <TotalStackBar types={gapTypes} />
        </div>
      </section>

      {needsApiRebuild && (
        <section className="panel px-3 py-2.5 border border-amber-500/30 bg-amber-500/10">
          <p className="text-[10px] text-amber-200">
            API needs redeploy: <span className="mono">docker compose build api frontend && docker compose up -d api frontend</span>
          </p>
        </section>
      )}

      <MarginBreakdownTable
        title="Full margin map"
        subtitle="Each row is % of the same 100% total. Type rows + bin rows all use one scale."
        types={gapTypes}
      />

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judges (% of same 100%)</h4>
        <p className="text-[9px] text-zinc-600 mb-2">Each judge&apos;s gap points as a slice of total margin.</p>
        <table className="w-full text-[10px] min-w-[420px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">Judge</th>
              <th className="text-right py-1 px-1">% total</th>
              <th className="text-right py-1 px-1">Gap pt</th>
              <th className="text-left py-1 pl-2 min-w-[120px]">Share</th>
            </tr>
          </thead>
          <tbody>
            {judgeMarginShares.map((j) => (
              <tr key={j.judge_model} className="border-b border-zinc-800/50">
                <td className="py-1.5 pr-2 font-medium text-zinc-200">{j.short_name}</td>
                <td className="text-right py-1.5 px-1 mono text-amber-200 font-semibold">{fmtPct(j.share_pct)}</td>
                <td className="text-right py-1.5 px-1 mono text-zinc-400">{j.total_gap_points.toFixed(0)}</td>
                <td className="py-1.5 pl-2">
                  <ShareBar sharePct={j.share_pct} colorClass="bg-violet-500" height="h-2.5" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {judgePairs.length > 0 && (
        <section className="panel px-3 py-2.5 overflow-x-auto">
          <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge agreement</h4>
          <table className="w-full text-[10px] min-w-[400px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">Pair</th>
                <th className="text-right py-1 px-1">Samples</th>
                <th className="text-right py-1 px-1">Same type</th>
                <th className="text-right py-1 px-1">Same pick</th>
              </tr>
            </thead>
            <tbody>
              {judgePairs.map((p) => (
                <tr key={`${p.judge_a}-${p.judge_b}`} className="border-b border-zinc-800/50">
                  <td className="py-1.5 pr-2 text-zinc-300">
                    {p.short_name_a} · {p.short_name_b}
                  </td>
                  <td className="text-right py-1.5 px-1 mono text-zinc-400">{p.observations}</td>
                  <td className="text-right py-1.5 px-1 mono text-sky-300">{fmtPct(p.same_bucket_pct)}</td>
                  <td className="text-right py-1.5 px-1 mono text-emerald-300">{fmtPct(p.same_pick_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">Per duel (each duel = its own 100%)</h4>
        <table className="w-full text-[10px] min-w-[640px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">When</th>
              <th className="text-left py-1 pr-2">Matchup</th>
              <th className="text-right py-1 px-1">Total pt</th>
              <th className="text-left py-1 pl-2 min-w-[140px]">Type split</th>
              <th className="text-left py-1 pl-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {duels.map((duel) => {
              const open = expandedDuel === duel.eval_run_id;
              const duelGapTypes = duel.gap_types ?? [];
              return (
                <Fragment key={duel.eval_run_id}>
                  <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                    <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(duel.finished_at)}</td>
                    <td className="py-1.5 pr-2 text-zinc-300">
                      {duel.challenger_label} vs {duel.king_label}
                      <span className="text-zinc-600 ml-1 capitalize">· {duel.winner}</span>
                    </td>
                    <td className="text-right py-1.5 px-1 mono text-zinc-300">{duel.total_gap_points.toFixed(0)}</td>
                    <td className="py-1.5 pl-2">
                      <TotalStackBar types={duelGapTypes} />
                    </td>
                    <td className="py-1.5 pl-2">
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedDuel((prev) => (prev === duel.eval_run_id ? null : duel.eval_run_id))
                        }
                        className="text-[9px] text-sky-400 hover:underline"
                      >
                        {open ? "hide" : "breakdown"}
                      </button>
                    </td>
                  </tr>
                  {open && (
                    <tr className="border-b border-zinc-800/50 bg-zinc-900/30">
                      <td colSpan={5} className="py-2 px-2">
                        <MarginBreakdownTable
                          title={`Duel margin = 100% (${duel.total_gap_points.toFixed(0)} pt)`}
                          types={duelGapTypes}
                          embedded
                        />
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
