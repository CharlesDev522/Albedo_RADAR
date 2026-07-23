"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  shortRepo,
  type AlbedoScoringExportDuel,
  type AlbedoScoringExportOverview,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="text-[12px] font-semibold text-zinc-100 mt-0.5">{value}</p>
    </div>
  );
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function resultLabel(duel: AlbedoScoringExportDuel): string {
  if (duel.coronated) return "crowned";
  return duel.challenger_won ? "challenger" : "defended";
}

export default function AlbedoScoringDatasetPanel() {
  const { subnet } = useSubnet();
  const [overview, setOverview] = useState<AlbedoScoringExportOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (forceRefresh = false) => {
      setLoading(true);
      try {
        const result = await api.getAlbedoScoringExportOverview(subnet, forceRefresh, { limit: 50 });
        setOverview(result);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load scoring exports");
        setOverview(null);
      } finally {
        setLoading(false);
      }
    },
    [subnet]
  );

  useEffect(() => {
    void load(false);
  }, [load]);

  const handleDownload = async (evalRunId: string) => {
    setDownloadingId(evalRunId);
    try {
      await api.downloadAlbedoScoringResults(evalRunId, subnet, true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloadingId(null);
    }
  };

  return (
    <section className="rounded-lg border border-cyan-500/25 bg-cyan-500/5 px-3 py-2.5 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3 min-w-0">
        <div className="min-w-0 flex-1">
          <h3 className="text-[11px] font-semibold text-cyan-100">Scoring-results dataset</h3>
          <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
            Download the raw <code className="text-zinc-400">scoring-results.jsonl</code> artifact for
            each finished duel. No filtering or transformation — one file per duel.
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

      {error && <p className="text-[10px] text-rose-300 mt-2">{error}</p>}

      {loading && !overview ? (
        <p className="text-[10px] text-zinc-500 mt-3">Scanning duels for scoring artifacts…</p>
      ) : overview ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3 min-w-0">
            <Stat label="Finished duels" value={overview.duels_total} />
            <Stat label="With scoring JSONL" value={overview.duels_with_scoring} />
            <Stat label="Listed below" value={overview.duels.length} />
          </div>

          {overview.duels.length === 0 ? (
            <p className="text-[10px] text-zinc-500 mt-3">
              No duels with a scoring-results artifact in the recent feed.
            </p>
          ) : (
            <div className="overflow-x-auto mt-3">
              <table className="w-full text-[10px] min-w-[720px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-1 pr-2 font-medium">When</th>
                    <th className="text-left py-1 pr-2 font-medium">Challenger</th>
                    <th className="text-left py-1 pr-2 font-medium">King</th>
                    <th className="text-left py-1 pr-2 font-medium">Mode</th>
                    <th className="text-right py-1 px-1 font-medium">Samples</th>
                    <th className="text-left py-1 pr-2 font-medium">Result</th>
                    <th className="text-right py-1 pl-2 font-medium">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.duels.map((duel) => (
                    <tr key={duel.eval_run_id} className="border-b border-zinc-900/80 text-zinc-300">
                      <td className="py-1 pr-2 text-zinc-500 whitespace-nowrap">
                        {fmtTime(duel.finished_at)}
                      </td>
                      <td className="py-1 pr-2 truncate max-w-[160px]" title={duel.challenger_label}>
                        {shortRepo(duel.challenger_label, 28)}
                      </td>
                      <td className="py-1 pr-2 truncate max-w-[120px] text-zinc-500">
                        {duel.king_label ? shortRepo(duel.king_label, 18) : "—"}
                      </td>
                      <td className="py-1 pr-2 text-zinc-500">{duel.scoring_mode ?? "—"}</td>
                      <td className="py-1 px-1 text-right tabular-nums">
                        {duel.scored_sample_count ?? "—"}
                      </td>
                      <td className="py-1 pr-2 text-zinc-400">{resultLabel(duel)}</td>
                      <td className="py-1 pl-2 text-right">
                        <button
                          type="button"
                          onClick={() => void handleDownload(duel.eval_run_id)}
                          disabled={downloadingId === duel.eval_run_id}
                          className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2 py-0.5 text-[9px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
                        >
                          {downloadingId === duel.eval_run_id ? "…" : duel.export_filename}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : null}
    </section>
  );
}
