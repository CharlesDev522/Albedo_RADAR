"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AlbedoScoringAnalysis, type AlbedoSampleDualZeros } from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

function SampleBlock({ sample }: { sample: AlbedoSampleDualZeros }) {
  const [open, setOpen] = useState(true);
  return (
    <article className="rounded border border-zinc-800 bg-zinc-900/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex flex-wrap items-center justify-between gap-2 px-2.5 py-2 text-left hover:bg-zinc-800/30"
      >
        <p className="text-[10px] font-medium text-zinc-200 truncate min-w-0" title={sample.sample_id}>
          {sample.sample_id}
        </p>
        <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[9px] text-amber-200 shrink-0">
          {sample.dual_zero_count} dual-zero
        </span>
      </button>
      {open && (
        <div className="border-t border-zinc-800 overflow-x-auto">
          <table className="w-full text-[9px] min-w-[900px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800/80">
                <th className="text-left py-1 px-2 w-10">Q</th>
                <th className="text-left py-1 px-2">Question</th>
                <th className="text-left py-1 px-2 w-[18%]">Ch · GLM</th>
                <th className="text-left py-1 px-2 w-[18%]">Ch · Qwen</th>
                <th className="text-left py-1 px-2 w-[18%]">King · GLM</th>
                <th className="text-left py-1 px-2 w-[18%]">King · Qwen</th>
              </tr>
            </thead>
            <tbody>
              {sample.questions.map((q) => (
                <tr key={q.question_id} className="border-b border-zinc-800/50 align-top">
                  <td className="py-1.5 px-2 mono text-zinc-500">{q.question_id.replace("q_", "")}</td>
                  <td className="py-1.5 px-2 text-zinc-300">{q.text}</td>
                  <td className="py-1.5 px-2 text-rose-200/90">{q.challenger_glm ?? "—"}</td>
                  <td className="py-1.5 px-2 text-rose-200/70">{q.challenger_qwen ?? "—"}</td>
                  <td className="py-1.5 px-2 text-emerald-200/90">{q.king_glm ?? "—"}</td>
                  <td className="py-1.5 px-2 text-emerald-200/70">{q.king_qwen ?? "—"}</td>
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
    return <div className="py-3 px-2 text-[10px] text-zinc-500">Loading dual-zero analysis…</div>;
  }
  if (error) {
    return <div className="py-3 px-2 text-[10px] text-rose-300">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="py-2 px-1 space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[10px] font-semibold text-zinc-200">Both-sides dual-zero (GLM + Qwen)</p>
          <p className="text-[9px] text-zinc-500 mt-0.5">
            {data.total_samples} samples · {data.samples_with_dual_zeros} with dual-zero ·{" "}
            {data.total_dual_zero_questions} questions
          </p>
          <p className="text-[8px] text-zinc-600 mt-0.5 max-w-3xl">
            GLM and Qwen both score 0 on challenger and king sides for the same rubric question.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleDownload()}
          disabled={downloading}
          className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2 py-1 text-[9px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50 shrink-0"
        >
          {downloading ? "Preparing…" : "Download JSONL"}
        </button>
      </div>

      {data.total_dual_zero_questions === 0 ? (
        <p className="text-[10px] text-zinc-500 px-1">
          No questions where GLM and Qwen both scored 0 on challenger and king sides.
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
