"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  modelLinkFromUri,
  shortRepo,
  type AlbedoMergeAdvisorRecommendation,
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

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function UsageGuide() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded border border-zinc-800 bg-zinc-950/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-2.5 py-2 text-left hover:bg-zinc-900/50"
      >
        <span className="text-[10px] font-medium text-zinc-300">How to use the merge advisor</span>
        <span className="text-[10px] text-zinc-500">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <div className="px-2.5 pb-2.5 space-y-2.5 text-[10px] text-zinc-400 border-t border-zinc-800/80">
          <div>
            <p className="text-zinc-300 font-medium mb-0.5">1. Read the recommendation</p>
            <p>
              The panel loads automatically from live SN97 duel data. The <strong className="text-zinc-300">base (king)</strong> is
              always the current reign holder. <strong className="text-zinc-300">Donors</strong> are challengers that performed well
              against that king (wins, margins, coronations, optional per-question sample mass).
            </p>
          </div>
          <div>
            <p className="text-zinc-300 font-medium mb-0.5">2. Tune the two filters</p>
            <ul className="list-disc list-inside space-y-0.5 ml-0.5">
              <li>
                <strong className="text-zinc-300">Sample mass</strong> — fetches recent{" "}
                <code className="text-zinc-500">SCORING_RESULTS</code> JSONL and weights donors by how often they win
                individual rubric questions (slower, more precise).
              </li>
              <li>
                <strong className="text-zinc-300">Consensus duels only</strong> — ignores split judge panels (e.g. 1–1)
                when estimating strengths; use when judges disagree a lot.
              </li>
            </ul>
            <p className="mt-1">Click <strong className="text-zinc-300">Refresh</strong> after changing filters.</p>
          </div>
          <div>
            <p className="text-zinc-300 font-medium mb-0.5">3. Understand the table columns</p>
            <ul className="list-disc list-inside space-y-0.5 ml-0.5">
              <li><strong className="text-zinc-300">Weight</strong> — normalized merge share for task-vector methods (TIES / DARE / task arithmetic).</li>
              <li><strong className="text-zinc-300">BT</strong> — Bradley–Terry strength from all pairwise duel outcomes.</li>
              <li><strong className="text-zinc-300">Margin</strong> — average duel win margin vs the king (positive = challenger ahead).</li>
              <li><strong className="text-zinc-300">Sample</strong> — per-question win rate from scoring JSONL (only when sample mass is on).</li>
              <li><strong className="text-zinc-300">Density</strong> — suggested TIES/DARE sparsity for that donor (higher = bolder task-vector injection).</li>
            </ul>
          </div>
          <div>
            <p className="text-zinc-300 font-medium mb-0.5">4. Pick a merge method</p>
            <p>
              The advisor auto-selects based on donor count and duel noise:{" "}
              <strong className="text-zinc-300">NuSLERP</strong> for one strong donor,{" "}
              <strong className="text-zinc-300">TIES</strong> for 2–3 clean donors,{" "}
              <strong className="text-zinc-300">DARE TIES</strong> when judges split or donors are many,{" "}
              <strong className="text-zinc-300">task arithmetic</strong> on tight margins. Check{" "}
              <strong className="text-zinc-300">Alternatives</strong> if you want a different trade-off.
            </p>
          </div>
          <div>
            <p className="text-zinc-300 font-medium mb-0.5">5. Export and run mergekit</p>
            <ol className="list-decimal list-inside space-y-0.5 ml-0.5">
              <li>Click <strong className="text-zinc-300">Download YAML</strong> or <strong className="text-zinc-300">Copy</strong> the config.</li>
              <li>
                Ensure model paths in the YAML resolve on your machine (Hippius{" "}
                <code className="text-zinc-500">org/model@sha256:…</code> or Hugging Face repo paths).
              </li>
              <li>
                From the <code className="text-zinc-500">research/mergekit</code> submodule:{" "}
                <code className="text-zinc-500">mergekit-yaml your-config.yaml --out ./merged-model</code>
              </li>
              <li>
                NuSLERP configs use per-model <strong className="text-zinc-300">weight</strong> on king + top donor
                (no duplicate base_model). TIES/DARE configs put the king in <strong className="text-zinc-300">base_model</strong> only.
              </li>
              <li>Upload the merged checkpoint and submit it as a challenger — only real Albedo duels validate the merge.</li>
            </ol>
          </div>
          <div>
            <p className="text-zinc-300 font-medium mb-0.5">6. API (optional)</p>
            <p className="font-mono text-[9px] text-zinc-500 break-all">
              GET /api/v1/albedo/merge-advisor/recommendation?subnet=97&amp;include_sample_mass=true&amp;consensus_only=false
            </p>
            <p className="font-mono text-[9px] text-zinc-500 break-all mt-0.5">
              GET /api/v1/albedo/merge-advisor/config — same params, returns YAML attachment
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export default function AlbedoMergeAdvisorPanel() {
  const { subnet } = useSubnet();
  const [rec, setRec] = useState<AlbedoMergeAdvisorRecommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [includeSampleMass, setIncludeSampleMass] = useState(true);
  const [consensusOnly, setConsensusOnly] = useState(false);

  const load = useCallback(
    async (forceRefresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const result = await api.getAlbedoMergeAdvisorRecommendation(
          subnet,
          forceRefresh,
          includeSampleMass,
          consensusOnly
        );
        setRec(result);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load merge recommendation");
        setRec(null);
      } finally {
        setLoading(false);
      }
    },
    [subnet, includeSampleMass, consensusOnly]
  );

  useEffect(() => {
    void load();
  }, [load]);

  const downloadYaml = async () => {
    setDownloading(true);
    try {
      await api.downloadAlbedoMergeAdvisorConfig(
        subnet,
        false,
        includeSampleMass,
        consensusOnly
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  };

  const copyYaml = async () => {
    if (!rec?.mergekit_yaml) return;
    try {
      await navigator.clipboard.writeText(rec.mergekit_yaml);
    } catch {
      setError("Clipboard copy failed");
    }
  };

  return (
    <section className="panel px-3 py-2.5 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-[11px] font-semibold text-zinc-200">Smart merge advisor</h3>
          <p className="text-[9px] text-zinc-600 mt-0.5 max-w-2xl">
            Builds a mergekit YAML from duel outcomes, reign history, and optional per-sample scoring.
            Scroll down on this tab for the full how-to guide.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1.5 text-[10px] text-zinc-400">
            <input
              type="checkbox"
              checked={includeSampleMass}
              onChange={(e) => setIncludeSampleMass(e.target.checked)}
              className="rounded border-zinc-600"
            />
            Sample mass
          </label>
          <label className="inline-flex items-center gap-1.5 text-[10px] text-zinc-400">
            <input
              type="checkbox"
              checked={consensusOnly}
              onChange={(e) => setConsensusOnly(e.target.checked)}
              className="rounded border-zinc-600"
            />
            Consensus duels only
          </label>
          <button
            type="button"
            onClick={() => void load(true)}
            disabled={loading}
            className="px-2 py-1 text-[10px] rounded border border-zinc-700 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
          <button
            type="button"
            onClick={() => void downloadYaml()}
            disabled={!rec || downloading}
            className="px-2 py-1 text-[10px] rounded border border-emerald-600/40 text-emerald-200 bg-emerald-500/10 hover:bg-emerald-500/20 disabled:opacity-50"
          >
            {downloading ? "…" : "Download YAML"}
          </button>
        </div>
      </div>

      <UsageGuide />

      {error && (
        <p className="text-[10px] text-rose-300 border border-rose-500/30 rounded px-2 py-1 bg-rose-500/10">
          {error}
        </p>
      )}

      {rec && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            <Stat label="Method" value={rec.method.pretty_name} />
            <Stat label="Duels analyzed" value={rec.duels_analyzed} />
            <Stat label="Binary w/ scoring" value={rec.binary_duels_analyzed} />
            <Stat label="Consensus duels" value={rec.judge_consensus_duels} />
            <Stat label="Sample-mass duels" value={rec.sample_mass_duels} />
            <Stat label="Donors" value={rec.donors.length} />
          </div>

          <div className="rounded border border-zinc-800 bg-zinc-950/50 px-2.5 py-2">
            <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-1">Base (king)</p>
            <p className="text-[11px] text-zinc-100 font-medium">{shortRepo(rec.base_label, 48)}</p>
            <p className="text-[9px] text-zinc-600 font-mono mt-0.5 truncate">{rec.base_mergekit_ref}</p>
            {modelLinkFromUri(rec.base_model_uri) && (
              <a
                href={modelLinkFromUri(rec.base_model_uri)!}
                target="_blank"
                rel="noreferrer"
                className="text-[9px] text-sky-400 hover:underline mt-1 inline-block"
              >
                Open model
              </a>
            )}
          </div>

          {rec.donors.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px] min-w-[720px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-1 pr-2 font-medium">Donor</th>
                    <th className="text-right py-1 px-1 font-medium">Weight</th>
                    <th className="text-right py-1 px-1 font-medium">Win%</th>
                    <th className="text-right py-1 px-1 font-medium">Duels</th>
                    <th className="text-right py-1 px-1 font-medium">BT</th>
                    <th className="text-right py-1 px-1 font-medium">Margin</th>
                    <th className="text-right py-1 px-1 font-medium">Sample</th>
                    <th className="text-right py-1 pl-1 font-medium">Density</th>
                  </tr>
                </thead>
                <tbody>
                  {rec.donors.map((d) => (
                    <tr key={d.model_uri} className="border-b border-zinc-900/80 text-zinc-300">
                      <td className="py-1 pr-2">
                        <span className="text-zinc-100">{shortRepo(d.label, 28)}</span>
                      </td>
                      <td className="text-right py-1 px-1 tabular-nums text-emerald-300">
                        {(d.merge_weight * 100).toFixed(1)}%
                      </td>
                      <td className="text-right py-1 px-1 tabular-nums">{d.win_pct.toFixed(1)}%</td>
                      <td className="text-right py-1 px-1 tabular-nums">{d.duels}</td>
                      <td className="text-right py-1 px-1 tabular-nums">{d.bt_strength.toFixed(2)}</td>
                      <td className="text-right py-1 px-1 tabular-nums">{fmtPct(d.avg_margin ?? null)}</td>
                      <td className="text-right py-1 px-1 tabular-nums">
                        {d.sample_mass != null ? `${(d.sample_mass * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td className="text-right py-1 pl-1 tabular-nums">
                        {d.density != null ? d.density.toFixed(2) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {rec.method.alternatives.length > 0 && (
            <div>
              <p className="text-[9px] uppercase tracking-wide text-zinc-500 mb-1">Alternatives</p>
              <ul className="space-y-1">
                {rec.method.alternatives.map((alt) => (
                  <li key={alt.method} className="text-[10px] text-zinc-400">
                    <span className="text-zinc-300 font-medium">{alt.method}</span>
                    <span className="text-zinc-600"> ({alt.score})</span> — {alt.rationale}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {rec.rationale.length > 0 && (
            <ul className="list-disc list-inside text-[10px] text-zinc-400 space-y-0.5">
              {rec.rationale.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}

          <div>
            <div className="flex items-center justify-between gap-2 mb-1">
              <p className="text-[9px] uppercase tracking-wide text-zinc-500">mergekit YAML</p>
              <button
                type="button"
                onClick={() => void copyYaml()}
                className="text-[9px] text-zinc-400 hover:text-zinc-200"
              >
                Copy
              </button>
            </div>
            <pre className="text-[9px] leading-relaxed text-zinc-300 bg-zinc-950 border border-zinc-800 rounded p-2 overflow-x-auto max-h-56">
              {rec.mergekit_yaml}
            </pre>
          </div>

          {rec.note && <p className="text-[9px] text-zinc-600">{rec.note}</p>}
        </>
      )}

      {!rec && !loading && !error && (
        <p className="text-[10px] text-zinc-500">No recommendation available.</p>
      )}
    </section>
  );
}
