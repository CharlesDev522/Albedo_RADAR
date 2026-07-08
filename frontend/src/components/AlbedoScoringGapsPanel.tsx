"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AlbedoScoringAnalysis,
  type AlbedoScoringSide,
  type AlbedoSampleDualZeros,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

function fmtScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function categoryLabel(category: string | null | undefined): string {
  if (!category) return "—";
  if (category.startsWith("cat_")) return `Category ${category.slice(4)}`;
  return category.replace(/_/g, " ");
}

function SampleBlock({ sample, side }: { sample: AlbedoSampleDualZeros; side: AlbedoScoringSide }) {
  const [open, setOpen] = useState(true);
  const sideAccent =
    side === "king"
      ? "border-emerald-500/25 bg-emerald-500/5"
      : "border-rose-500/25 bg-rose-500/5";

  return (
    <article className={`rounded border ${sideAccent}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex flex-wrap items-center justify-between gap-2 px-2.5 py-2 text-left hover:bg-zinc-800/30"
      >
        <div className="min-w-0">
          <p className="text-[10px] font-medium text-zinc-200 truncate" title={sample.sample_id}>
            {sample.sample_label}
          </p>
          <p className="text-[8px] text-zinc-600 truncate" title={sample.sample_id}>
            {sample.sample_id}
          </p>
        </div>
        <div className="flex items-center gap-2 text-[9px] shrink-0">
          <span className="text-rose-300 mono">{fmtScore(sample.challenger_score)}</span>
          <span className="text-zinc-600">/</span>
          <span className="text-emerald-300 mono">{fmtScore(sample.king_score)}</span>
          <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-amber-200">
            {sample.dual_zero_count} dual-zero
          </span>
        </div>
      </button>
      {open && (
        <div className="border-t border-zinc-800 overflow-x-auto">
          <table className="w-full text-[9px] min-w-[720px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800/80">
                <th className="text-left py-1 px-2 w-10">Q</th>
                <th className="text-left py-1 px-2 w-16">Category</th>
                <th className="text-left py-1 px-2">Question ({side})</th>
                <th className="text-left py-1 px-2 w-[28%]">GLM reason</th>
                <th className="text-left py-1 px-2 w-[28%]">Qwen reason</th>
              </tr>
            </thead>
            <tbody>
              {sample.questions.map((q) => (
                <tr key={q.question_id} className="border-b border-zinc-800/50 align-top">
                  <td className="py-1.5 px-2 mono text-zinc-500">{q.question_id.replace("q_", "")}</td>
                  <td className="py-1.5 px-2 text-zinc-500">{categoryLabel(q.category)}</td>
                  <td className="py-1.5 px-2 text-zinc-300">{q.text}</td>
                  <td className="py-1.5 px-2 text-cyan-200/90">{q.glm_explanation ?? "—"}</td>
                  <td className="py-1.5 px-2 text-violet-200/90">{q.qwen_explanation ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}

function SideTabs({
  side,
  onChange,
}: {
  side: AlbedoScoringSide;
  onChange: (side: AlbedoScoringSide) => void;
}) {
  const tabs: { id: AlbedoScoringSide; label: string }[] = [
    { id: "challenger", label: "Challenger side" },
    { id: "king", label: "King side" },
  ];
  return (
    <div className="inline-flex rounded border border-zinc-800 bg-zinc-900/60 p-0.5">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`px-2 py-0.5 rounded text-[9px] font-medium border transition-colors ${
            side === tab.id
              ? tab.id === "king"
                ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
                : "border-rose-500/40 bg-rose-500/15 text-rose-200"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export default function AlbedoScoringGapsPanel({ evalRunId }: { evalRunId: string }) {
  const { subnet } = useSubnet();
  const [side, setSide] = useState<AlbedoScoringSide>("challenger");
  const [data, setData] = useState<AlbedoScoringAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getAlbedoScoringAnalysis(evalRunId, subnet, true, side);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load scoring analysis");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [evalRunId, subnet, side]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await api.downloadAlbedoScoringExport(evalRunId, subnet, side);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to download JSONL export");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return <div className="py-3 px-2 text-[10px] text-zinc-500">Loading scoring-results.jsonl analysis…</div>;
  }
  if (error) {
    return <div className="py-3 px-2 text-[10px] text-rose-300">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="py-2 px-1 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[10px] font-semibold text-zinc-200">GLM + Qwen dual-zero questions</p>
            <SideTabs side={side} onChange={setSide} />
          </div>
          <p className="text-[9px] text-zinc-500">
            {data.side_label ?? (side === "king" ? "King model output" : "Challenger model output")} ·{" "}
            {data.total_samples} samples · {data.samples_with_dual_zeros} with dual-zero ·{" "}
            {data.total_dual_zero_questions} questions where both judges scored 0
          </p>
          <p className="text-[8px] text-zinc-600 max-w-3xl">
            {data.side_description ??
              (side === "king"
                ? "Score 0 = judge said No to this rubric question about the king's answer in the sample."
                : "Score 0 = judge said No to this rubric question about the challenger's answer in the sample.")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => void handleDownload()}
            disabled={downloading}
            className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2 py-1 text-[9px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {downloading ? "Preparing…" : `Download ${side} JSONL`}
          </button>
          {data.scoring_results_url && (
            <a
              href={data.scoring_results_url}
              target="_blank"
              rel="noreferrer"
              className="text-[9px] text-sky-400 hover:underline"
            >
              source jsonl
            </a>
          )}
        </div>
      </div>

      {data.total_dual_zero_questions === 0 ? (
        <p className="text-[10px] text-zinc-500 px-1">
          No rubric questions where both GLM and Qwen scored 0 on the {side} side for this duel.
        </p>
      ) : (
        <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          {data.samples.map((sample) => (
            <SampleBlock key={sample.sample_id} sample={sample} side={side} />
          ))}
        </div>
      )}
    </div>
  );
}
