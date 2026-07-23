"use client";

import type { AlbedoScoringBucketRow, AlbedoScoringDuelAnalysis } from "@/lib/api";

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

function marginClass(n: number): string {
  if (n > 0.5) return "text-rose-300";
  if (n < -0.5) return "text-emerald-300";
  return "text-zinc-300";
}

function BucketTable({
  title,
  rows,
  showWeight,
}: {
  title: string;
  rows: AlbedoScoringBucketRow[];
  showWeight?: boolean;
}) {
  if (rows.length === 0) {
    return (
      <div>
        <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-1">{title}</p>
        <p className="text-[10px] text-zinc-600">No data</p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-1">{title}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-[9px] min-w-[640px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2 font-medium">Key</th>
              {showWeight && <th className="text-right py-1 px-1 font-medium">Weight</th>}
              <th className="text-right py-1 px-1 font-medium">Slots</th>
              <th className="text-right py-1 px-1 font-medium">Ch yes%</th>
              <th className="text-right py-1 px-1 font-medium">King yes%</th>
              <th className="text-right py-1 px-1 font-medium">Wtd ch</th>
              <th className="text-right py-1 px-1 font-medium">Wtd king</th>
              <th className="text-right py-1 px-1 font-medium">Wtd margin</th>
              <th className="text-right py-1 pl-1 font-medium">|Δ| share</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className="border-b border-zinc-900/80 text-zinc-300">
                <td className="py-1 pr-2 text-zinc-200">{row.key}</td>
                {showWeight && (
                  <td className="py-1 px-1 text-right tabular-nums text-zinc-500">
                    {row.weight_multiplier != null ? row.weight_multiplier.toFixed(1) : "—"}
                  </td>
                )}
                <td className="py-1 px-1 text-right tabular-nums">{row.question_slots}</td>
                <td className="py-1 px-1 text-right tabular-nums">{fmtPct(row.challenger_yes_rate)}</td>
                <td className="py-1 px-1 text-right tabular-nums">{fmtPct(row.king_yes_rate)}</td>
                <td className="py-1 px-1 text-right tabular-nums">{fmtPct(row.weighted_challenger_score)}</td>
                <td className="py-1 px-1 text-right tabular-nums">{fmtPct(row.weighted_king_score)}</td>
                <td className={`py-1 px-1 text-right tabular-nums ${marginClass(row.weighted_margin)}`}>
                  {row.weighted_margin > 0 ? "+" : ""}
                  {fmtPct(row.weighted_margin)}
                </td>
                <td className="py-1 pl-1 text-right tabular-nums text-zinc-500">
                  {fmtPct(row.share_of_abs_weighted_margin_pct)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function AlbedoScoringDuelAnalysisPanel({
  analysis,
}: {
  analysis: AlbedoScoringDuelAnalysis;
}) {
  return (
    <div className="mt-2 rounded border border-zinc-800 bg-zinc-950/60 px-2.5 py-2 space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px]">
        <div>
          <p className="text-[9px] text-zinc-500 uppercase">Samples</p>
          <p className="text-zinc-200 font-medium">{analysis.total_samples}</p>
        </div>
        <div>
          <p className="text-[9px] text-zinc-500 uppercase">Judge obs</p>
          <p className="text-zinc-200 font-medium">{analysis.judge_observations}</p>
        </div>
        <div>
          <p className="text-[9px] text-zinc-500 uppercase">Question slots</p>
          <p className="text-zinc-200 font-medium">{analysis.question_slots}</p>
        </div>
        <div>
          <p className="text-[9px] text-zinc-500 uppercase">Duel</p>
          <p
            className="text-zinc-400 truncate"
            title={`${analysis.challenger_label} vs ${analysis.king_label ?? "king"}`}
          >
            {analysis.challenger_label} vs {analysis.king_label ?? "king"}
          </p>
        </div>
      </div>

      <BucketTable title="By category" rows={analysis.categories} />
      <BucketTable title="By requires" rows={analysis.requires} showWeight />

      <p className="text-[9px] text-zinc-600">{analysis.note}</p>
    </div>
  );
}
