"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import RepoCrownAnalysisPanel from "@/components/RepoCrownAnalysisPanel";
import { EntityNameCell } from "@/lib/entityLabels";
import AlbedoEvalQueueOverviewPanel from "@/components/AlbedoEvalQueueOverview";
import AlbedoEvalFailsPanel from "@/components/AlbedoEvalFailsPanel";
import AlbedoScoringGapsPanel from "@/components/AlbedoScoringGapsPanel";
import AlbedoDatasetBuilderPanel from "@/components/AlbedoDatasetBuilderPanel";
import AlbedoKingReignDatasetPanel from "@/components/AlbedoKingReignDatasetPanel";
import AlbedoSampleScoreAnalysisPanel from "@/components/AlbedoSampleScoreAnalysisPanel";
import {
  api,
  hippiusModelUrl,
  shortAddr,
  shortRepo,
  type AlbedoAnalysisOverview,
  type AlbedoDuelJudgeVote,
  type AlbedoDuelSummary,
  type AlbedoEvalQueueOverview,
  type AlbedoKingTenure,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";
import { usePageVisibility } from "@/lib/usePageVisibility";

const POLL_MS = 30_000;
const QUEUE_POLL_MS = 8_000;
type Section = "overview" | "kings" | "duels" | "analysis" | "dq";

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function fmtScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function fmtMargin(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const pct = n * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function fmtHours(h: number | null | undefined): string {
  if (h == null || !Number.isFinite(h)) return "—";
  if (h < 1) return `${Math.round(h * 60)}m`;
  if (h < 48) return `${h.toFixed(1)}h`;
  return `${(h / 24).toFixed(1)}d`;
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

function modelLink(modelUri: string): string {
  return hippiusModelUrl(modelUri.split("@")[0]);
}

function scoringModeLabel(mode: string | null | undefined): string {
  if (!mode) return "legacy";
  if (mode === "binary") return "binary rubric";
  if (mode === "glm_categories") return "GLM categories";
  if (mode === "mixed") return "mixed";
  return mode.replace(/_/g, " ");
}

function scoringModeClass(mode: string | null | undefined): string {
  if (mode === "binary") return "text-cyan-300 border-cyan-500/30 bg-cyan-500/10";
  if (mode === "glm_categories") return "text-violet-300 border-violet-500/30 bg-violet-500/10";
  if (mode === "mixed") return "text-amber-300 border-amber-500/30 bg-amber-500/10";
  return "text-zinc-400 border-zinc-600 bg-zinc-800/50";
}

function scoringResultsAvailable(duel: AlbedoDuelSummary): boolean {
  return Boolean(duel.artifacts?.SCORING_RESULTS ?? duel.artifacts?.scoring_results);
}

function SectionTabs({
  section,
  onChange,
}: {
  section: Section;
  onChange: (s: Section) => void;
}) {
  const tabs: { id: Section; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "dq", label: "DQ" },
    { id: "kings", label: "Kings & rewards" },
    { id: "duels", label: "Duel feed" },
    { id: "analysis", label: "Score analysis" },
  ];
  return (
    <div className="inline-flex rounded-md border border-zinc-800 bg-zinc-900/60 p-0.5">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`px-2.5 py-1 rounded text-[10px] font-medium border transition-colors ${
            section === tab.id
              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
              : "border-transparent text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-0">
      <p className="text-[9px] uppercase tracking-wide text-zinc-500 truncate">{label}</p>
      <p className="text-[13px] font-semibold text-zinc-100 mt-0.5">{value}</p>
      {sub && <p className="text-[9px] text-zinc-600 mt-0.5">{sub}</p>}
    </div>
  );
}

function KingTenureCard({ tenure }: { tenure: AlbedoKingTenure }) {
  const accent = tenure.is_current_king
    ? "border-amber-500/50 bg-gradient-to-br from-amber-500/15 to-zinc-900/80"
    : "border-zinc-800 bg-zinc-900/50";

  return (
    <article className={`rounded-lg border p-3 min-w-[220px] flex-shrink-0 ${accent}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-[10px] text-zinc-500">
            #{tenure.reign_rank} · v{tenure.king_version}
            {tenure.is_current_king && (
              <span className="ml-1 text-amber-300 font-medium">ACTIVE KING</span>
            )}
          </p>
          <h4 className="text-[11px] font-semibold text-zinc-100 mt-0.5 truncate" title={tenure.model_name}>
            {shortRepo(tenure.model_name, 24)}
          </h4>
          <p className="text-[9px] text-zinc-500 mt-0.5">
            uid {tenure.uid} · {shortAddr(tenure.hotkey, 4)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[14px] font-bold text-amber-200">{fmtPct(tenure.weight_pct)}</p>
          <p className="text-[9px] text-zinc-500">weight</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 mt-3 text-[10px]">
        <Stat label="Active reign" value={fmtHours(tenure.active_tenure_hours)} sub="as #1 king" />
        <Stat label="Slot tenure" value={fmtHours(tenure.slot_tenure_hours)} sub="earning weight" />
        <Stat
          label="Defenses"
          value={`${tenure.defenses}/${tenure.attacks_faced}`}
          sub={tenure.defense_pct != null ? `${fmtPct(tenure.defense_pct)} held` : undefined}
        />
        <Stat label="Crown margin" value={fmtMargin(tenure.coronation_margin)} />
      </div>

      <div className="flex flex-wrap gap-1 mt-2 text-[9px]">
        {tenure.reign_slots > 1 && (
          <span className="rounded border border-sky-500/40 bg-sky-500/15 px-1.5 py-0.5 text-sky-200">
            {tenure.reign_slots} slots
          </span>
        )}
        {tenure.coronation_at && (
          <span className="text-zinc-600">crowned {fmtTime(tenure.coronation_at)}</span>
        )}
      </div>
    </article>
  );
}

function judgeShortFromModel(judge: string): string {
  const slash = judge.lastIndexOf("/");
  return slash >= 0 ? judge.slice(slash + 1) : judge;
}

function judgeShortHeader(name: string): string {
  if (name.startsWith("glm")) return "GLM";
  if (name.startsWith("qwen")) return "Qwen";
  if (name.startsWith("deepseek")) return "DS";
  return name.split("-")[0];
}

function JudgeScoreCell({ vote }: { vote: AlbedoDuelJudgeVote | undefined }) {
  if (!vote) {
    return <td className="py-1.5 px-1 text-center text-zinc-700 border-l border-zinc-800/50">—</td>;
  }

  const pickCh = vote.pick_challenger;
  const pickLabel = pickCh ? "ch" : "k";
  const diagnosis = `${pickLabel} ${fmtMargin(pickCh ? vote.margin_from_neutral : -vote.margin_from_neutral)}`;

  return (
    <td
      className={`py-1.5 px-1 text-center mono text-[10px] border-l border-zinc-800/50 min-w-[68px] ${
        pickCh ? "text-rose-300 bg-rose-500/15" : "text-emerald-300 bg-emerald-500/15"
      }`}
      title={[
        vote.judge,
        `challenger ${fmtScore(vote.challenger_score)}`,
        `king ${fmtScore(vote.king_score)}`,
        `Δ ${fmtMargin(vote.margin_from_neutral)}`,
        `pick ${pickCh ? "challenger" : "king"}`,
        vote.agrees_with_verdict ? "agrees with verdict" : "dissents from verdict",
      ].join("\n")}
    >
      <div className="leading-tight">
        <span className="text-rose-200/90">{fmtScore(vote.challenger_score)}</span>
        <span className="text-zinc-600 mx-0.5">/</span>
        <span className="text-emerald-200/90">{fmtScore(vote.king_score)}</span>
      </div>
      <div className={`text-[9px] font-semibold mt-0.5 ${pickCh ? "text-rose-300" : "text-emerald-300"}`}>
        {diagnosis}
      </div>
    </td>
  );
}

function judgeVoteMap(duel: AlbedoDuelSummary): Record<string, AlbedoDuelJudgeVote> {
  const map: Record<string, AlbedoDuelJudgeVote> = {};
  for (const v of duel.judge_votes ?? []) {
    for (const key of [v.short_name, v.judge, judgeShortFromModel(v.judge)]) {
      if (key) map[key] = v;
    }
  }
  return map;
}

const JUDGE_COLUMNS = ["glm-5.1", "qwen3.5-397b-a17b", "deepseek-v3.2"];

function DuelRow({
  duel,
  judgeOrder,
  colSpan,
  scoringExpanded,
  onToggleScoring,
}: {
  duel: AlbedoDuelSummary;
  judgeOrder: string[];
  colSpan: number;
  scoringExpanded: boolean;
  onToggleScoring: () => void;
}) {
  const won = duel.challenger_won;
  const votes = judgeVoteMap(duel);
  const req = duel.required_win_margin;
  const marginBelowBar =
    req != null && duel.win_margin > 0 && duel.win_margin < req && !won;
  const hasScoring = scoringResultsAvailable(duel);
  return (
    <Fragment>
    <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
      <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">
        <div>{fmtTime(duel.finished_at)}</div>
        {duel.scoring_mode && (
          <span
            className={`inline-block mt-0.5 px-1 py-0.5 rounded text-[8px] border ${scoringModeClass(duel.scoring_mode)}`}
          >
            {scoringModeLabel(duel.scoring_mode)}
          </span>
        )}
      </td>
      <td className="py-1.5 pr-2">
        <a href={modelLink(duel.model_uri)} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline block truncate max-w-[130px]">
          {shortRepo(duel.repo ?? `${duel.namespace}/${duel.model_name}`, 26)}
        </a>
        <span className="text-[9px] text-zinc-600">uid {duel.uid}</span>
      </td>
      <td className="py-1.5 pr-2 text-zinc-500 truncate max-w-[90px]">
        vs {duel.king_model_name ? shortRepo(duel.king_model_name, 12) : "—"}
      </td>
      {judgeOrder.map((name) => (
        <JudgeScoreCell key={name} vote={votes[name]} />
      ))}
      <td className="py-1.5 px-1 mono text-zinc-400 text-center">{duel.judge_spread != null ? fmtScore(duel.judge_spread) : "—"}</td>
      <td className="py-1.5 pr-2 mono text-[10px]">
        <div className="text-rose-200">{fmtScore(duel.score_challenger)}</div>
        <div className="text-emerald-200/90">{fmtScore(duel.score_king)}</div>
      </td>
      <td
        className={`py-1.5 pr-2 mono ${
          won ? "text-rose-300" : marginBelowBar ? "text-amber-300" : "text-emerald-300"
        }`}
        title={
          req != null
            ? `Win bar ${fmtScore(req)}${marginBelowBar ? " — challenger led but below bar" : ""}`
            : undefined
        }
      >
        {fmtMargin(duel.win_margin)}
        {req != null && (
          <span className="block text-[8px] text-zinc-600">bar {fmtScore(req)}</span>
        )}
      </td>
      <td className="py-1.5">
        <span
          className={`inline-block px-1.5 py-0.5 rounded text-[9px] border ${
            duel.coronated
              ? "text-amber-200 border-amber-500/40 bg-amber-500/15"
              : won
                ? "text-rose-200 border-rose-500/30 bg-rose-500/10"
                : "text-emerald-200 border-emerald-500/30 bg-emerald-500/10"
          }`}
        >
          {duel.coronated ? "crowned" : won ? "challenger" : "defended"}
        </span>
        {duel.panel_pattern && !duel.unanimous_panel && (
          <span className="block text-[8px] text-zinc-600 mt-0.5">{duel.panel_pattern.replace(/_/g, " ")}</span>
        )}
        {(duel.scored_sample_count != null || duel.judge_errors != null) && (
          <span className="block text-[8px] text-zinc-600 mt-0.5">
            {duel.scored_sample_count != null ? `${duel.scored_sample_count} samples` : ""}
            {duel.judge_errors ? ` · ${duel.judge_errors} judge err` : ""}
          </span>
        )}
        {hasScoring && (
          <button
            type="button"
            onClick={onToggleScoring}
            className={`block text-[8px] mt-0.5 hover:underline ${
              scoringExpanded ? "text-amber-300" : "text-sky-400"
            }`}
          >
            {scoringExpanded ? "hide scoring gaps" : "scoring gaps"}
          </button>
        )}
      </td>
    </tr>
    {scoringExpanded && hasScoring && (
      <tr className="border-b border-zinc-800/50 bg-zinc-900/30">
        <td colSpan={colSpan} className="p-0 max-w-0 w-full">
          <div className="min-w-0 max-w-full overflow-hidden border-l-2 border-amber-500/25 px-2 py-0.5">
            <AlbedoScoringGapsPanel evalRunId={duel.eval_run_id} />
          </div>
        </td>
      </tr>
    )}
    </Fragment>
  );
}

export default function AlbedoDuelPanel() {
  const { subnet, view } = useSubnet();
  const pageVisible = usePageVisibility();
  const panelActive = view === "duels" && pageVisible;
  const [data, setData] = useState<AlbedoAnalysisOverview | null>(null);
  const [queueData, setQueueData] = useState<AlbedoEvalQueueOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("duels");
  const [scoringDuelId, setScoringDuelId] = useState<string | null>(null);

  const queuePollActive = panelActive && (section === "overview" || section === "dq");

  const refresh = useCallback(async (forceRefresh = false) => {
    try {
      const overview = await api.getAlbedoAnalysis(subnet, forceRefresh);
      setData(overview);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load duel analysis");
    } finally {
      setLoading(false);
    }
  }, [subnet]);

  const refreshQueue = useCallback(async (forceRefresh = false) => {
    try {
      setQueueData(await api.getAlbedoEvalQueue(subnet, forceRefresh));
    } catch {
      /* non-critical — overview still works */
    }
  }, [subnet]);

  useEffect(() => {
    if (!panelActive) return;
    void refresh(false);
    const id = setInterval(() => void refresh(true), POLL_MS);
    return () => clearInterval(id);
  }, [panelActive, refresh]);

  useEffect(() => {
    if (!queuePollActive) return;
    void refreshQueue(false);
    const id = setInterval(() => void refreshQueue(true), QUEUE_POLL_MS);
    return () => clearInterval(id);
  }, [queuePollActive, refreshQueue]);

  const judgeOrder = useMemo(() => {
    const fromChain = (data?.judge_models ?? []).map(judgeShortFromModel).filter(Boolean);
    if (fromChain.length > 0) return fromChain;
    const seen = new Set<string>();
    for (const duel of data?.recent_duels ?? []) {
      for (const v of duel.judge_votes ?? []) {
        if (v.short_name) seen.add(v.short_name);
      }
    }
    return seen.size > 0 ? [...seen] : JUDGE_COLUMNS;
  }, [data]);

  const duelColSpan = 7 + judgeOrder.length;

  const multiSlotHolders = useMemo(
    () => (data?.reign_slot_holders ?? []).filter((h) => h.slots_held > 1),
    [data]
  );

  if (loading && !data) {
    return <div className="panel p-4 text-[10px] text-zinc-500">Loading duel analysis…</div>;
  }
  if (error && !data) {
    return <div className="panel p-4 text-[10px] text-rose-300">Duel analysis unavailable: {error}</div>;
  }
  if (!data) return null;

  const king = data.current_king;

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <div>
              <h2 className="text-[12px] font-semibold text-zinc-100">Albedo duel analysis</h2>
              <p className="text-[10px] text-zinc-500 mt-0.5">
                {data.total_duels} duels · {data.coronations} coronations · updated {fmtTime(data.updated_at)}
                {data.miner_lookup_coverage_pct != null && (
                  <span className="text-zinc-600"> · repo map {fmtPct(data.miner_lookup_coverage_pct)}</span>
                )}
              </p>
            </div>
            <SectionTabs section={section} onChange={setSection} />
          </div>
          {king && (
            <div className="rounded-lg border border-amber-500/35 bg-amber-500/10 px-3 py-2 min-w-[200px]">
              <p className="text-[9px] uppercase tracking-wide text-amber-400/90">Current king</p>
              <p className="text-[11px] font-semibold text-amber-50 mt-0.5">
                v{king.king_version} · {shortRepo(king.model_name, 30)}
              </p>
              <p className="text-[9px] text-zinc-500 mt-1">
                uid {king.uid} · {fmtPct(king.weight_bps / 100)} weight
              </p>
            </div>
          )}
        </div>

      </section>

      {section === "overview" && (
        <>
          {queueData && <AlbedoEvalQueueOverviewPanel data={queueData} />}

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {[
              { label: "Challenger wins", value: String(data.challenger_wins), accent: "text-rose-300" },
              { label: "King defenses", value: String(data.king_wins), accent: "text-emerald-300" },
              { label: "Challenger win %", value: fmtPct(data.challenger_win_pct) },
              { label: "Avg margin", value: fmtMargin(data.avg_win_margin) },
              {
                label: "Win bar",
                value: data.required_win_margin != null ? fmtScore(data.required_win_margin) : "—",
                sub:
                  data.binary_scoring_duels != null && data.binary_scoring_duels > 0
                    ? `${data.binary_scoring_duels} binary duels`
                    : undefined,
              },
              { label: "Avg ch / k score", value: `${fmtScore(data.avg_challenger_score)} / ${fmtScore(data.avg_king_score)}` },
              {
                label: "Queue",
                value: String(queueData?.queue_length ?? data.queue_length),
              },
            ].map((kpi) => (
              <div key={kpi.label} className="panel px-2.5 py-2">
                <p className="text-[9px] uppercase tracking-wide text-zinc-500">{kpi.label}</p>
                <p className={`text-[14px] font-semibold mt-0.5 ${kpi.accent ?? "text-zinc-100"}`}>{kpi.value}</p>
              </div>
            ))}
          </div>

          <RepoCrownAnalysisPanel analysis={data.repo_crown_analysis} compact />
        </>
      )}

      {section === "dq" && queueData && <AlbedoEvalFailsPanel data={queueData} />}
      {section === "dq" && !queueData && (
        <div className="panel p-4 text-[10px] text-zinc-500">Loading DQ data…</div>
      )}

      {section === "kings" && (
        <>
          <AlbedoKingReignDatasetPanel kingHistory={data.king_history ?? []} />

          <section className="panel px-3 py-2.5">
            <div className="flex flex-wrap items-end justify-between gap-2 mb-3">
              <div>
                <h3 className="text-[11px] font-semibold text-zinc-200">Latest 5 kings — reward slots</h3>
                <p className="text-[9px] text-zinc-600 mt-0.5">
                  Active reign, slot tenure, defenses, and weight share (20% per slot)
                </p>
              </div>
              {multiSlotHolders.length > 0 && (
                <div className="text-[9px] text-sky-300 border border-sky-500/30 rounded px-2 py-1 bg-sky-500/10">
                  Multi-slot: {multiSlotHolders.map((h) => `${shortRepo(h.label, 16)} (${h.slots_held})`).join(", ")}
                </div>
              )}
            </div>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {(data.king_tenures ?? []).map((t) => (
                <KingTenureCard key={t.king_version} tenure={t} />
              ))}
            </div>
          </section>

          <section className="panel px-3 py-2">
            <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Weight slot occupancy</h3>
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 pr-2">Miner / model</th>
                  <th className="text-right py-1 px-1">Slots</th>
                  <th className="text-right py-1 px-1">Weight</th>
                  <th className="text-left py-1 pl-2">Versions in chain</th>
                </tr>
              </thead>
              <tbody>
                {(data.reign_slot_holders ?? []).map((h) => (
                  <tr key={h.key} className="border-b border-zinc-800/50">
                    <td className="py-1 pr-2 text-zinc-300">
                      {shortRepo(h.label, 32)}
                      <span className="text-zinc-600 ml-1">uid {h.uid}</span>
                    </td>
                    <td className={`text-right py-1 px-1 mono ${h.slots_held > 1 ? "text-sky-300" : "text-zinc-400"}`}>
                      {h.slots_held}
                    </td>
                    <td className="text-right py-1 px-1 mono text-amber-300">{fmtPct(h.weight_pct)}</td>
                    <td className="py-1 pl-2 mono text-zinc-500">
                      {h.king_versions.map((v) => `v${v}`).join(", ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <RepoCrownAnalysisPanel analysis={data.repo_crown_analysis} />

          <section className="panel px-3 py-2">
            <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Coronation history (repo / coldkey)</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-1 pr-2">Ver</th>
                    <th className="text-left py-1 pr-2">When</th>
                    <th className="text-left py-1 pr-2">Miner</th>
                    <th className="text-left py-1 pr-2">Defeated</th>
                    <th className="text-left py-1 pr-2">Margin</th>
                  </tr>
                </thead>
                <tbody>
                  {data.king_history.map((entry) => (
                    <tr key={entry.eval_run_id} className="border-b border-zinc-800/50">
                      <td className="py-1 pr-2 mono text-amber-300">v{entry.king_version}</td>
                      <td className="py-1 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(entry.finished_at)}</td>
                      <td className="py-1 pr-2 truncate max-w-[160px]" title={entry.repo ?? entry.model_name}>
                        <EntityNameCell repo={entry.repo ?? entry.model_name} coldkey={entry.coldkey} />
                      </td>
                      <td className="py-1 pr-2 text-zinc-500">
                        {entry.defeated_model_name ? `v${entry.defeated_king_version}` : "—"}
                      </td>
                      <td className="py-1 pr-2 mono text-emerald-300">{fmtMargin(entry.win_margin)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      {section === "analysis" && <AlbedoSampleScoreAnalysisPanel />}

      {section === "duels" && (
        <section className="panel px-3 py-2">
          <AlbedoDatasetBuilderPanel />
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge duel scores</h3>
          <p className="text-[9px] text-zinc-600 mb-2">
            Finished duels only ({(data.recent_duels ?? []).length} shown, {data.total_duels} total).
            In-progress evals appear in the live duel banner above. Each judge cell: red = picks
            challenger, green = picks king. Click scoring gaps for dual-zero / dual-one rubric questions.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px] min-w-[920px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 pr-2">When</th>
                  <th className="text-left py-1 pr-2">Challenger repo</th>
                  <th className="text-left py-1 pr-2">King</th>
                  {judgeOrder.map((name) => (
                    <th key={name} className="text-center py-1 px-1 border-l border-zinc-800/50 text-zinc-400 min-w-[68px]">
                      <div>{judgeShortHeader(name)}</div>
                      <div className="text-[8px] font-normal text-zinc-600">pick / Δ</div>
                    </th>
                  ))}
                  <th className="text-center py-1 px-1 text-zinc-600">σ spread</th>
                  <th className="text-left py-1 pr-2">Aggregate</th>
                  <th className="text-left py-1 pr-2">Margin</th>
                  <th className="text-left py-1 pr-2">Result</th>
                </tr>
              </thead>
              <tbody>
                {(data.recent_duels ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={duelColSpan} className="py-6 text-center text-[10px] text-zinc-500">
                      No finished duel results in the dashboard feed.
                      {data.current_eval
                        ? " A duel may be in progress — check the live banner above."
                        : " Check API connectivity or Hippius dashboard.json."}
                    </td>
                  </tr>
                ) : (
                (data.recent_duels ?? []).map((duel) => (
                  <DuelRow
                    key={duel.eval_run_id}
                    duel={duel}
                    judgeOrder={judgeOrder}
                    colSpan={duelColSpan}
                    scoringExpanded={scoringDuelId === duel.eval_run_id}
                    onToggleScoring={() =>
                      setScoringDuelId((prev) => (prev === duel.eval_run_id ? null : duel.eval_run_id))
                    }
                  />
                ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
