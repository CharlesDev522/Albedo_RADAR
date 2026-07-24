"use client";

import type {
  AlbedoScoringBucketRow,
  AlbedoScoringDuelAnalysis,
  AlbedoScoringFormula,
} from "@/lib/api";

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

function fmtScore01(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function marginClass(n: number): string {
  if (n > 0.5) return "text-rose-300";
  if (n < -0.5) return "text-emerald-300";
  return "text-zinc-300";
}

function rowLabel(key: string): string {
  if (key === "_total") return "Total";
  return key;
}

function FormulaBlock({ formula }: { formula: AlbedoScoringFormula }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/40 px-2 py-1.5 text-[9px] text-zinc-500 space-y-0.5">
      <p className="text-zinc-400 font-medium">Albedo validator rubric</p>
      <p>
        Weights:{" "}
        {Object.entries(formula.requires_weights)
          .map(([key, weight]) => `${key}=${weight}`)
          .join(", ")}
      </p>
      <p>Size multiplier floor: {formula.size_factor_floor}</p>
      <p>Side score: {formula.side_score}</p>
      <p>Duel score: {formula.duel_score}</p>
      <p>Contribution: {formula.bucket_contribution}</p>
      <p>Partial rate: {formula.bucket_partial_rate}</p>
    </div>
  );
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
        <table className="w-full text-[9px] min-w-[720px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2 font-medium">Key</th>
              {showWeight && <th className="text-right py-1 px-1 font-medium">Wt</th>}
              <th className="text-right py-1 px-1 font-medium">Share</th>
              <th className="text-right py-1 px-1 font-medium">Ch partial</th>
              <th className="text-right py-1 px-1 font-medium">K partial</th>
              <th className="text-right py-1 px-1 font-medium">Ch contrib</th>
              <th className="text-right py-1 px-1 font-medium">K contrib</th>
              <th className="text-right py-1 pl-1 font-medium">Contrib Δ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const isTotal = row.key === "_total";
              const isSize = row.key === "size";
              return (
                <tr
                  key={row.key}
                  className={`border-b border-zinc-900/80 ${
                    isTotal ? "bg-zinc-900/40 text-zinc-100" : "text-zinc-300"
                  }`}
                  title={row.note ?? undefined}
                >
                  <td className="py-1 pr-2 font-medium">{rowLabel(row.key)}</td>
                  {showWeight && (
                    <td className="py-1 px-1 text-right tabular-nums text-zinc-500">
                      {row.weight_multiplier != null ? row.weight_multiplier.toFixed(2) : "—"}
                    </td>
                  )}
                  <td className="py-1 px-1 text-right tabular-nums text-zinc-500">
                    {isSize ? "×" : fmtPct(row.weight_share_pct)}
                  </td>
                  <td className="py-1 px-1 text-right tabular-nums">
                    {isSize ? fmtPct(row.challenger_yes_rate) : fmtPct(row.challenger_yes_rate)}
                  </td>
                  <td className="py-1 px-1 text-right tabular-nums">
                    {fmtPct(row.king_yes_rate)}
                  </td>
                  <td className="py-1 px-1 text-right tabular-nums">
                    {fmtPct(row.weighted_challenger_score)}
                  </td>
                  <td className="py-1 px-1 text-right tabular-nums">
                    {fmtPct(row.weighted_king_score)}
                  </td>
                  <td
                    className={`py-1 pl-1 text-right tabular-nums ${marginClass(row.weighted_margin)}`}
                  >
                    {row.weighted_margin > 0 ? "+" : ""}
                    {fmtPct(row.weighted_margin)}
                  </td>
                </tr>
              );
            })}
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
  const overall = analysis.overall;

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
          <p className="text-[9px] text-zinc-500 uppercase">Size Qs</p>
          <p className="text-zinc-200 font-medium">{analysis.size_question_slots}</p>
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

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[10px]">
        <div className="rounded border border-zinc-800 px-2 py-1.5">
          <p className="text-[9px] text-zinc-500 uppercase mb-1">Duel score (replicated)</p>
          <p className="text-zinc-300">
            Challenger {fmtPct(overall.weighted_challenger_score_pct)} · King{" "}
            {fmtPct(overall.weighted_king_score_pct)} · Margin{" "}
            <span className={marginClass(overall.weighted_margin_pct)}>
              {overall.weighted_margin_pct > 0 ? "+" : ""}
              {fmtPct(overall.weighted_margin_pct)}
            </span>
          </p>
          {overall.base_challenger_score_pct != null && (
            <p className="text-[9px] text-zinc-600 mt-0.5">
              Base (pre-size): ch {fmtPct(overall.base_challenger_score_pct)} · k{" "}
              {fmtPct(overall.base_king_score_pct ?? 0)}
            </p>
          )}
        </div>
        <div
          className={`rounded border px-2 py-1.5 ${
            overall.jsonl_matches_dashboard
              ? "border-emerald-500/30 bg-emerald-500/5"
              : "border-zinc-800"
          }`}
        >
          <p className="text-[9px] text-zinc-500 uppercase mb-1">Dashboard</p>
          <p className="text-zinc-300">
            Challenger {fmtScore01(overall.dashboard_score_challenger)} · King{" "}
            {fmtScore01(overall.dashboard_score_king)} · Margin{" "}
            {overall.dashboard_win_margin != null
              ? fmtScore01(overall.dashboard_win_margin)
              : "—"}
          </p>
          <p className="text-[9px] text-zinc-600 mt-0.5">
            {overall.jsonl_matches_dashboard ? "Matches replicated score" : "Compare with replicated"}
            {overall.requires_contrib_matches_duel && " · requires rows sum to duel total"}
          </p>
        </div>
      </div>

      <FormulaBlock formula={analysis.formula} />
      <BucketTable title="By requires (additive contributions)" rows={analysis.requires} showWeight />
      <BucketTable title="By category (additive contributions)" rows={analysis.categories} />

      <p className="text-[9px] text-zinc-600">{analysis.note}</p>
    </div>
  );
}
