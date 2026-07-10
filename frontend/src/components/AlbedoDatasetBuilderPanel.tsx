"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type AlbedoDatasetBuildSummary, type ScoringConsensusPolarity } from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const POLARITY_LABEL: Record<ScoringConsensusPolarity, string> = {
  zero: "dual-zero",
  one: "dual-one",
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="text-[12px] font-semibold text-zinc-100 mt-0.5">{value}</p>
    </div>
  );
}

function PolarityToggle({
  polarity,
  onChange,
  disabled,
}: {
  polarity: ScoringConsensusPolarity;
  onChange: (next: ScoringConsensusPolarity) => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded border border-zinc-700 overflow-hidden shrink-0">
      {(["zero", "one"] as const).map((value) => (
        <button
          key={value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(value)}
          className={`px-2 py-1 text-[10px] disabled:opacity-50 ${
            polarity === value
              ? "bg-zinc-700 text-zinc-100"
              : "bg-zinc-900/60 text-zinc-400 hover:bg-zinc-800/80"
          }`}
        >
          {POLARITY_LABEL[value]}
        </button>
      ))}
    </div>
  );
}

export default function AlbedoDatasetBuilderPanel() {
  const { subnet } = useSubnet();
  const [polarity, setPolarity] = useState<ScoringConsensusPolarity>("zero");
  const [summary, setSummary] = useState<AlbedoDatasetBuildSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [downloadingScript, setDownloadingScript] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const modeLabel = POLARITY_LABEL[polarity];

  const loadSummary = useCallback(
    async (forceRefresh = false) => {
      setLoading(true);
      try {
        const result = await api.getAlbedoDatasetSummary(subnet, forceRefresh, polarity);
        setSummary(result);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load dataset summary");
        setSummary(null);
      } finally {
        setLoading(false);
      }
    },
    [subnet, polarity]
  );

  useEffect(() => {
    void loadSummary(false);
  }, [loadSummary]);

  const handleBuildDownload = async () => {
    setBuilding(true);
    try {
      await api.downloadAlbedoDatasetExport(subnet, true, polarity);
      await loadSummary(true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to build dataset");
    } finally {
      setBuilding(false);
    }
  };

  const handleDownloadScript = async () => {
    setDownloadingScript(true);
    try {
      await api.downloadAlbedoDatasetDedupScript(subnet);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to download dedup script");
    } finally {
      setDownloadingScript(false);
    }
  };

  return (
    <section className="rounded-lg border border-cyan-500/25 bg-cyan-500/5 px-3 py-2.5 mb-3 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[11px] font-semibold text-cyan-100">Dataset builder</h3>
            <PolarityToggle
              polarity={polarity}
              onChange={setPolarity}
              disabled={loading || building}
            />
          </div>
          <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
            Combine {modeLabel} JSONL exports from the latest{" "}
            {summary?.recent_duels_limit ?? 20} binary rubric duels into one file. Only samples
            with more than 5 consensus questions are included. Duplicate sample_ids are removed
            automatically (first occurrence kept).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => void loadSummary(true)}
            disabled={loading || building}
            className="rounded border border-zinc-700 bg-zinc-900/60 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800/80 disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh summary"}
          </button>
          <button
            type="button"
            onClick={() => void handleDownloadScript()}
            disabled={downloadingScript || building}
            className="rounded border border-zinc-700 bg-zinc-900/60 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800/80 disabled:opacity-50"
          >
            {downloadingScript ? "Preparing…" : "Dedup script"}
          </button>
          <button
            type="button"
            onClick={() => void handleBuildDownload()}
            disabled={building || loading || (summary?.unique_samples ?? 0) === 0}
            className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {building ? "Building…" : "Build & download JSONL"}
          </button>
        </div>
      </div>

      {error && <p className="text-[10px] text-rose-300 mt-2">{error}</p>}

      {loading && !summary ? (
        <p className="text-[10px] text-zinc-500 mt-3">Scanning binary rubric duels…</p>
      ) : summary ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-9 gap-3 mt-3 min-w-0">
          <Stat label="Binary duels" value={summary.binary_duels_total} />
          <Stat label="With scoring" value={summary.binary_duels_with_scoring} />
          <Stat label="Scanned (recent)" value={summary.binary_duels_scanned} />
          <Stat label={`With ${modeLabel}`} value={summary.binary_duels_with_dual_zero} />
          <Stat label="Lines before dedup" value={summary.samples_before_dedup} />
          <Stat label="Unique samples" value={summary.unique_samples} />
          <Stat label="Duplicates removed" value={summary.duplicates_removed} />
          <Stat
            label="Skipped (≤5 questions)"
            value={summary.samples_skipped_min_questions ?? 0}
          />
          <Stat label={`${modeLabel} questions`} value={summary.total_dual_zero_questions} />
          <Stat label="Output file" value={summary.export_filename} />
        </div>
      ) : null}
    </section>
  );
}
