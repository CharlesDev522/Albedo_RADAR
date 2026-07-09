"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AlbedoDualZeroQuestion,
  type AlbedoScoringAnalysis,
  type AlbedoSampleDualZeros,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

function QuestionBlock({ q }: { q: AlbedoDualZeroQuestion }) {
  return (
    <div className="border-b border-zinc-800/40 last:border-0 py-2.5 px-2.5 space-y-2">
      <div className="flex gap-2 items-start min-w-0">
        <span className="mono text-[10px] text-zinc-500 shrink-0 w-6">{q.question_id.replace("q_", "")}</span>
        <div className="min-w-0 flex-1">
          <p className="text-[11px] leading-snug text-zinc-300 break-words">{q.text}</p>
          {q.example_bad && (
            <p className="text-[10px] leading-snug text-zinc-500 mt-1.5 break-words">
              <span className="text-zinc-600">Example bad: </span>
              {q.example_bad}
            </p>
          )}
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-1.5 pl-8 text-[10px] leading-snug min-w-0">
        <p className="min-w-0 break-words text-rose-200/90">
          <span className="text-zinc-600 font-medium">Ch·GLM </span>
          {q.challenger_glm ?? "—"}
        </p>
        <p className="min-w-0 break-words text-rose-200/70">
          <span className="text-zinc-600 font-medium">Ch·Qwen </span>
          {q.challenger_qwen ?? "—"}
        </p>
        <p className="min-w-0 break-words text-emerald-200/90">
          <span className="text-zinc-600 font-medium">King·GLM </span>
          {q.king_glm ?? "—"}
        </p>
        <p className="min-w-0 break-words text-emerald-200/70">
          <span className="text-zinc-600 font-medium">King·Qwen </span>
          {q.king_qwen ?? "—"}
        </p>
      </div>
    </div>
  );
}

function SampleBlock({ sample }: { sample: AlbedoSampleDualZeros }) {
  const [open, setOpen] = useState(true);
  return (
    <article className="rounded border border-zinc-800 bg-zinc-900/40 min-w-0 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex flex-wrap items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-zinc-800/30 min-w-0"
      >
        <p className="text-[11px] font-medium text-zinc-200 truncate min-w-0 flex-1" title={sample.sample_id}>
          {sample.sample_id}
        </p>
        <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-200 shrink-0">
          {sample.dual_zero_count} dual-zero
        </span>
      </button>
      {open && (
        <div className="border-t border-zinc-800 min-w-0 overflow-hidden">
          {sample.questions.map((q) => (
            <QuestionBlock key={q.question_id} q={q} />
          ))}
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
      await api.downloadAlbedoScoringExport(evalRunId, subnet, data?.export_filename);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to download JSONL export");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return <div className="py-3 px-2 text-[11px] text-zinc-500">Loading dual-zero analysis…</div>;
  }
  if (error) {
    return <div className="py-3 px-2 text-[11px] text-rose-300">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="min-w-0 max-w-full py-2 px-1 space-y-2 overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-2 min-w-0">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold text-zinc-200">Both-sides dual-zero (GLM + Qwen)</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            {data.total_samples} samples · {data.samples_with_dual_zeros} with dual-zero ·{" "}
            {data.total_dual_zero_questions} questions
          </p>
          <p className="text-[9px] text-zinc-600 mt-0.5 break-words">
            GLM and Qwen both score 0 on challenger and king sides for the same rubric question.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleDownload()}
          disabled={downloading || data.total_dual_zero_questions === 0}
          className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 shrink-0"
          title={data.export_filename ?? "Download JSONL"}
        >
          {downloading ? "Preparing…" : "Download JSONL"}
        </button>
      </div>

      {data.total_dual_zero_questions === 0 ? (
        <p className="text-[11px] text-zinc-500 px-1">
          No questions where GLM and Qwen both scored 0 on challenger and king sides.
        </p>
      ) : (
        <div className="space-y-2 max-h-[360px] overflow-y-auto overflow-x-hidden pr-1 min-w-0">
          {data.samples.map((sample) => (
            <SampleBlock key={sample.sample_id} sample={sample} />
          ))}
        </div>
      )}
    </div>
  );
}
