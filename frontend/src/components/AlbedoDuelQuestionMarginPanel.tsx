"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AlbedoDuelQuestionMarginAnalysis, type AlbedoQuestionMarginRow } from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

function fmtPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

function BucketBar({ buckets }: { buckets: AlbedoDuelQuestionMarginAnalysis["buckets"] }) {
  const d = buckets.default_q1_20_share_pct;
  const o = buckets.other_share_pct;
  return (
    <div className="space-y-1.5 mb-3">
      <div className="flex h-3 rounded overflow-hidden border border-zinc-800">
        <div
          className="bg-violet-500/70"
          style={{ width: `${Math.max(0, Math.min(100, d))}%` }}
          title={`Default q1–20: ${fmtPct(d)}`}
        />
        <div
          className="bg-sky-500/60"
          style={{ width: `${Math.max(0, Math.min(100, o))}%` }}
          title={`Other questions: ${fmtPct(o)}`}
        />
      </div>
      <div className="flex flex-wrap gap-3 text-[10px]">
        <span className="text-violet-300">
          <span className="inline-block w-2 h-2 rounded-sm bg-violet-500/70 mr-1" />
          default q1–20 · {fmtPct(d)}
        </span>
        <span className="text-sky-300">
          <span className="inline-block w-2 h-2 rounded-sm bg-sky-500/60 mr-1" />
          other · {fmtPct(o)}
        </span>
      </div>
    </div>
  );
}

function QuestionRow({ row }: { row: AlbedoQuestionMarginRow }) {
  const w = Math.min(100, Math.max(0, row.share_of_abs_margin_pct));
  return (
    <tr className="border-b border-zinc-800/50">
      <td className="mono text-[10px] text-zinc-400 py-1 pr-2">
        {row.question_index ?? row.question_id.replace("q_", "")}
      </td>
      <td className="text-[10px] text-zinc-300 py-1 max-w-[200px] truncate" title={row.text}>
        {row.text || row.question_id}
      </td>
      <td className="text-[9px] py-1">
        {row.is_default_q1_20 ? (
          <span className="text-violet-300/90">default</span>
        ) : (
          <span className="text-zinc-600">other</span>
        )}
      </td>
      <td className="text-[10px] text-zinc-400 py-1 text-right mono">{fmtPct(row.share_of_abs_margin_pct)}</td>
      <td className="py-1 pl-2 w-[28%]">
        <div className="h-1.5 rounded bg-zinc-800 overflow-hidden">
          <div className="h-full bg-amber-500/70" style={{ width: `${w}%` }} />
        </div>
      </td>
    </tr>
  );
}

export default function AlbedoDuelQuestionMarginPanel({ evalRunId }: { evalRunId: string }) {
  const { subnet } = useSubnet();
  const [data, setData] = useState<AlbedoDuelQuestionMarginAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "default" | "other">("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.getAlbedoQuestionMarginAnalysis(evalRunId, subnet, true);
      setData(result);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load question margins");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [evalRunId, subnet]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => {
    const qs = data?.questions ?? [];
    if (filter === "default") return qs.filter((q) => q.is_default_q1_20);
    if (filter === "other") return qs.filter((q) => !q.is_default_q1_20);
    return qs;
  }, [data?.questions, filter]);

  if (loading) {
    return <div className="py-3 px-2 text-[11px] text-zinc-500">Loading question margin breakdown…</div>;
  }
  if (error) {
    return <div className="py-3 px-2 text-[11px] text-rose-300">{error}</div>;
  }
  if (!data) return null;

  return (
    <div className="py-2 px-1 min-w-0">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <div>
          <h4 className="text-[11px] font-semibold text-zinc-200">Question margin share</h4>
          <p className="text-[9px] text-zinc-500 mt-0.5 max-w-xl">
            {data.total_samples} samples · {data.total_observations} sample×judge observations
            {data.questions_per_sample != null && data.questions_per_sample > 0
              ? ` · ${data.questions_per_sample} questions/sample`
              : ""}
            {data.avg_margin_pct_per_observation != null && (
              <span className="ml-1">
                · avg margin {data.avg_margin_pct_per_observation.toFixed(2)} pts
              </span>
            )}
          </p>
        </div>
        <div className="inline-flex rounded border border-zinc-700 overflow-hidden text-[9px]">
          {(["all", "default", "other"] as const).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 ${
                filter === f ? "bg-zinc-700 text-zinc-100" : "text-zinc-500 hover:bg-zinc-800"
              }`}
            >
              {f === "all" ? "all" : f === "default" ? "q1–20" : "other"}
            </button>
          ))}
        </div>
      </div>

      <BucketBar buckets={data.buckets} />

      <p className="text-[9px] text-zinc-600 mb-2">{data.note}</p>

      <div className="max-h-[320px] overflow-y-auto border border-zinc-800/80 rounded">
        <table className="tbl w-full">
          <thead className="sticky top-0 bg-zinc-950/95">
            <tr>
              <th className="text-left">#</th>
              <th className="text-left">question</th>
              <th>bucket</th>
              <th className="text-right">share</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <QuestionRow key={row.question_id} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
