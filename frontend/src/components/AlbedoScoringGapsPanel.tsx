"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AlbedoScoringAnalysis, type AlbedoSampleDualZeros } from "@/lib/api";
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

function SampleBlock({ sample }: { sample: AlbedoSampleDualZeros }) {
  const [open, setOpen] = useState(true);
  return (
    <article className="rounded border border-zinc-800 bg-zinc-900/40">
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
                <th className="text-left py-1 px-2">Question</th>
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

export default function AlbedoScoringGapsPanel({ evalRunId }: { evalRunId: string }) {
  const { subnet } = useSubnet();
  const [data, setData] = useState<AlbedoScoringAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getAlbedoScoringAnalysis(evalRunId, subnet, true);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load scoring analysis");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [evalRunId, subnet]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await api.downloadAlbedoScoringExport(evalRunId, subnet);
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
        <div>
          <p className="text-[10px] font-semibold text-zinc-200">GLM + Qwen dual-zero questions</p>
          <p className="text-[9px] text-zinc-500 mt-0.5">
            Challenger side · {data.total_samples} samples · {data.samples_with_dual_zeros} with dual-zero ·{" "}
            {data.total_dual_zero_questions} questions where both judges scored 0
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => void handleDownload()}
            disabled={downloading}
            className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2 py-1 text-[9px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {downloading ? "Preparing…" : "Download JSONL"}
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
          No rubric questions where both GLM and Qwen scored 0 on this duel.
        </p>
      ) : (
        <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
          {data.samples.map((sample) => (
            <SampleBlock key={sample.sample_id} sample={sample} />
          ))}
        </div>
      )}
    </div>
  );
}
