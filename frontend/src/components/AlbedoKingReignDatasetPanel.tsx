"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  shortRepo,
  type AlbedoDatasetBuildSummary,
  type AlbedoKingCoronation,
  type ScoringConsensusPolarity,
} from "@/lib/api";
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

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function AlbedoKingReignDatasetPanel({
  kingHistory,
}: {
  kingHistory: AlbedoKingCoronation[];
}) {
  const { subnet } = useSubnet();
  const [polarity, setPolarity] = useState<ScoringConsensusPolarity>("zero");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [summary, setSummary] = useState<AlbedoDatasetBuildSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const kings = useMemo(
    () => [...kingHistory].sort((a, b) => b.king_version - a.king_version),
    [kingHistory]
  );
  const selectedVersions = useMemo(
    () => [...selected].sort((a, b) => a - b),
    [selected]
  );
  const modeLabel = POLARITY_LABEL[polarity];

  const toggleKing = (version: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(version)) next.delete(version);
      else next.add(version);
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(kings.map((k) => k.king_version)));
  };

  const clearSelection = () => {
    setSelected(new Set());
    setSummary(null);
    setError(null);
  };

  const loadSummary = useCallback(
    async (versions: number[], forceRefresh = false) => {
      if (versions.length === 0) {
        setSummary(null);
        return;
      }
      setLoading(true);
      try {
        const result = await api.getAlbedoKingReignDatasetSummary(
          versions,
          subnet,
          forceRefresh,
          polarity
        );
        setSummary(result);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load king reign dataset summary");
        setSummary(null);
      } finally {
        setLoading(false);
      }
    },
    [subnet, polarity]
  );

  useEffect(() => {
    if (selectedVersions.length === 0) {
      setSummary(null);
      return;
    }
    void loadSummary(selectedVersions, false);
  }, [selectedVersions, loadSummary]);

  const handleBuildDownload = async () => {
    if (selectedVersions.length === 0) return;
    setBuilding(true);
    try {
      await api.downloadAlbedoKingReignDatasetExport(selectedVersions, subnet, true, polarity);
      await loadSummary(selectedVersions, true);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to build king reign dataset");
    } finally {
      setBuilding(false);
    }
  };

  return (
    <section className="rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2.5 mb-3 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3 min-w-0">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[11px] font-semibold text-amber-100">King reign dataset builder</h3>
            <PolarityToggle
              polarity={polarity}
              onChange={setPolarity}
              disabled={loading || building}
            />
          </div>
          <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
            Select one or more kings to combine {modeLabel} JSONL from every binary rubric duel they
            defended from coronation until the next king was crowned. Duplicate sample_ids are removed
            automatically.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={selectAll}
            disabled={loading || building || kings.length === 0}
            className="rounded border border-zinc-700 bg-zinc-900/60 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800/80 disabled:opacity-50"
          >
            Select all
          </button>
          <button
            type="button"
            onClick={clearSelection}
            disabled={loading || building || selected.size === 0}
            className="rounded border border-zinc-700 bg-zinc-900/60 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800/80 disabled:opacity-50"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={() => void loadSummary(selectedVersions, true)}
            disabled={loading || building || selectedVersions.length === 0}
            className="rounded border border-zinc-700 bg-zinc-900/60 px-2.5 py-1.5 text-[10px] text-zinc-300 hover:bg-zinc-800/80 disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh summary"}
          </button>
          <button
            type="button"
            onClick={() => void handleBuildDownload()}
            disabled={
              building || loading || selectedVersions.length === 0 || (summary?.unique_samples ?? 0) === 0
            }
            className="rounded border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] text-emerald-200 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {building ? "Building…" : "Build & download JSONL"}
          </button>
        </div>
      </div>

      {error && <p className="text-[10px] text-rose-300 mt-2">{error}</p>}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-[10px] min-w-[640px]">
          <thead>
            <tr className="text-zinc-500 border-b border-zinc-800">
              <th className="text-left py-1 pr-2 w-8" />
              <th className="text-left py-1 pr-2">Ver</th>
              <th className="text-left py-1 pr-2">Crowned</th>
              <th className="text-left py-1 pr-2">Miner</th>
              <th className="text-right py-1 px-1">Duels scanned</th>
              <th className="text-right py-1 pl-1">With {modeLabel}</th>
            </tr>
          </thead>
          <tbody>
            {kings.map((entry) => {
              const breakdown = summary?.king_reign_breakdown?.find(
                (row) => row.king_version === entry.king_version
              );
              const checked = selected.has(entry.king_version);
              return (
                <tr
                  key={entry.eval_run_id}
                  className={`border-b border-zinc-800/50 ${checked ? "bg-amber-500/5" : ""}`}
                >
                  <td className="py-1 pr-2">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleKing(entry.king_version)}
                      disabled={building}
                      className="accent-amber-400"
                      aria-label={`Select king v${entry.king_version}`}
                    />
                  </td>
                  <td className="py-1 pr-2 mono text-amber-300">v{entry.king_version}</td>
                  <td className="py-1 pr-2 text-zinc-500 whitespace-nowrap">
                    {fmtTime(entry.finished_at)}
                  </td>
                  <td
                    className="py-1 pr-2 truncate max-w-[200px] text-zinc-300"
                    title={entry.repo ?? entry.model_name ?? undefined}
                  >
                    {shortRepo(entry.repo ?? entry.model_name ?? "—", 28)}
                  </td>
                  <td className="text-right py-1 px-1 mono text-zinc-400">
                    {checked && breakdown ? breakdown.binary_duels_scanned : checked && loading ? "…" : "—"}
                  </td>
                  <td className="text-right py-1 pl-1 mono text-zinc-400">
                    {checked && breakdown
                      ? breakdown.binary_duels_with_dual_zero
                      : checked && loading
                        ? "…"
                        : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selectedVersions.length > 0 && loading && !summary ? (
        <p className="text-[10px] text-zinc-500 mt-3">Scanning reign duels…</p>
      ) : summary && selectedVersions.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 mt-3 min-w-0">
          <Stat label="Kings selected" value={selectedVersions.length} />
          <Stat label="Duels scanned" value={summary.binary_duels_scanned} />
          <Stat label={`With ${modeLabel}`} value={summary.binary_duels_with_dual_zero} />
          <Stat label="Lines before dedup" value={summary.samples_before_dedup} />
          <Stat label="Unique samples" value={summary.unique_samples} />
          <Stat label="Duplicates removed" value={summary.duplicates_removed} />
          <Stat label={`${modeLabel} questions`} value={summary.total_dual_zero_questions} />
          <Stat label="Output file" value={summary.export_filename} />
        </div>
      ) : null}
    </section>
  );
}
