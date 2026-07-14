"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type AlbedoSampleScoreAnalysis,
  type GapTypeSummary,
  type SampleGapBucket,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const GAP_COLORS: Record<SampleGapBucket, { bar: string; text: string }> = {
  close: { bar: "bg-sky-500", text: "text-sky-200" },
  moderate: { bar: "bg-amber-500", text: "text-amber-200" },
  decisive: { bar: "bg-rose-500", text: "text-rose-200" },
};

type MarginRow = {
  key: string;
  label: string;
  gapType: SampleGapBucket;
  sharePct: number;
  depth: 0 | 1;
};

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(2)}%`;
}

function fmtSignedMarginPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
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
    if (t.share_pct > 0) {
      rows.push({
        key: `type-${t.gap_type}`,
        label: t.gap_type,
        gapType: t.gap_type,
        sharePct: t.share_pct,
        depth: 0,
      });
    }
    for (const bin of t.gap_distribution ?? []) {
      if (bin.share_pct <= 0) continue;
      rows.push({
        key: `bin-${t.gap_type}-${bin.label}`,
        label: bin.label,
        gapType: t.gap_type,
        sharePct: bin.share_pct,
        depth: 1,
      });
    }
  }
  return rows;
}

function ShareBar({ sharePct, colorClass }: { sharePct: number; colorClass: string }) {
  return (
    <div className="h-2 rounded bg-zinc-800 overflow-hidden">
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
            className={GAP_COLORS[t.gap_type].bar}
            style={{ width: `${t.share_pct}%` }}
            title={`${t.gap_type}: ${fmtPct(t.share_pct)}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-3 text-[9px]">
        {active.map((t) => (
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
  if (rows.length === 0) {
    return <p className="text-[10px] text-zinc-500">No margin data yet.</p>;
  }

  const body = (
    <>
      <h4 className="text-[11px] font-semibold text-zinc-200">{title}</h4>
      {subtitle && <p className="text-[9px] text-zinc-600 mb-2">{subtitle}</p>}
      <table className="w-full text-[10px] min-w-[360px]">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left py-1 pr-2">Segment</th>
            <th className="text-right py-1 px-1 w-20">% of total</th>
            <th className="text-left py-1 pl-2 min-w-[140px]">Share</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-zinc-800/50">
              <td className={`py-1.5 pr-2 ${row.depth === 0 ? "font-medium capitalize" : "pl-4 text-zinc-400"}`}>
                <span className={row.depth === 0 ? GAP_COLORS[row.gapType].text : ""}>{row.label}</span>
              </td>
              <td className="text-right py-1.5 px-1 mono text-amber-200 font-medium">{fmtPct(row.sharePct)}</td>
              <td className="py-1.5 pl-2">
                <ShareBar sharePct={row.sharePct} colorClass={GAP_COLORS[row.gapType].bar} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );

  if (embedded) return <div className="overflow-x-auto">{body}</div>;
  return <section className="panel px-3 py-2.5 overflow-x-auto">{body}</section>;
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
  const typeShareSum = gapTypes.reduce((sum, t) => sum + t.share_pct, 0);
  const needsApiRebuild = gapTypes.length === 0 && data.total_observations > 0;

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-[11px] font-semibold text-zinc-200">Sample margin breakdown</h3>
            <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
              Same margin % as duel analysis: per sample × judge, margin = challenger score − king score
              (subnet scale). Every value below is <strong className="text-zinc-400 font-normal">% of total
              margin mass</strong> — all segments sum to 100%.
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

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Whole score</p>
            <p className="text-[16px] font-bold text-zinc-100">100.00%</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Type sum check</p>
            <p className="text-[14px] font-semibold text-zinc-200">{fmtPct(typeShareSum)}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Observations</p>
            <p className="text-[14px] font-semibold text-zinc-200">{data.total_observations}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase text-zinc-600">Binary duels</p>
            <p className="text-[14px] font-semibold text-zinc-200">{data.binary_duels_with_samples}</p>
          </div>
        </div>

        <div className="mt-4 pt-3 border-t border-zinc-800/80">
          <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-2">100% by gap type</p>
          <TotalStackBar types={gapTypes} />
        </div>
      </section>

      {needsApiRebuild && (
        <section className="panel px-3 py-2.5 border border-amber-500/30 bg-amber-500/10">
          <p className="text-[10px] text-amber-200">
            Rebuild <span className="mono">api</span> and <span className="mono">frontend</span> containers to load
            margin breakdown data.
          </p>
        </section>
      )}

      <MarginBreakdownTable
        title="Where margin goes"
        subtitle="Gap types and score-diff bins — each row is % of the same 100% total."
        types={gapTypes}
      />

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judges (% of total)</h4>
        <table className="w-full text-[10px] min-w-[320px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">Judge</th>
              <th className="text-right py-1 px-1">% of total</th>
              <th className="text-right py-1 px-1">Avg margin</th>
              <th className="text-left py-1 pl-2 min-w-[120px]">Share</th>
            </tr>
          </thead>
          <tbody>
            {judgeMarginShares.map((j) => (
              <tr key={j.judge_model} className="border-b border-zinc-800/50">
                <td className="py-1.5 pr-2 font-medium text-zinc-200">{j.short_name}</td>
                <td className="text-right py-1.5 px-1 mono text-amber-200 font-semibold">{fmtPct(j.share_pct)}</td>
                <td className="text-right py-1.5 px-1 mono text-zinc-400">{fmtSignedMarginPct(j.avg_margin_pct)}</td>
                <td className="py-1.5 pl-2">
                  <ShareBar sharePct={j.share_pct} colorClass="bg-violet-500" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {judgePairs.length > 0 && (
        <section className="panel px-3 py-2.5 overflow-x-auto">
          <h4 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge agreement</h4>
          <table className="w-full text-[10px] min-w-[320px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">Pair</th>
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
                  <td className="text-right py-1.5 px-1 mono text-sky-300">{fmtPct(p.same_bucket_pct)}</td>
                  <td className="text-right py-1.5 px-1 mono text-emerald-300">{fmtPct(p.same_pick_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel px-3 py-2.5 overflow-x-auto">
        <h4 className="text-[11px] font-semibold text-zinc-200 mb-2">Per duel (each = 100%)</h4>
        <table className="w-full text-[10px] min-w-[560px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2">When</th>
              <th className="text-left py-1 pr-2">Matchup</th>
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
                      <td colSpan={4} className="py-2 px-2">
                        <MarginBreakdownTable title="Duel margin = 100%" types={duelGapTypes} embedded />
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
