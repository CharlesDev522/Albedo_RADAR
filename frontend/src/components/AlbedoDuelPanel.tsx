"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  hippiusModelUrl,
  shortAddr,
  shortRepo,
  type AlbedoAnalysisOverview,
  type AlbedoCrownLeaderboardRow,
  type AlbedoDuelJudgeVote,
  type AlbedoDuelSummary,
  type AlbedoJudgeDetail,
  type AlbedoKingTenure,
  type AlbedoWinRateRow,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const POLL_MS = 30_000;
type Section = "overview" | "judges" | "kings" | "duels";

const JUDGE_COLORS: Record<string, string> = {
  "glm-5.1": "border-cyan-500/40 bg-cyan-500/10 text-cyan-200",
  "qwen3.5-397b-a17b": "border-violet-500/40 bg-violet-500/10 text-violet-200",
  "deepseek-v3.2": "border-amber-500/40 bg-amber-500/10 text-amber-200",
};

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

function judgeStyle(shortName: string): string {
  return JUDGE_COLORS[shortName] ?? "border-zinc-700 bg-zinc-800/50 text-zinc-300";
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
    { id: "judges", label: "Judges" },
    { id: "kings", label: "Kings & rewards" },
    { id: "duels", label: "Duel feed" },
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

function JudgeCard({ judge }: { judge: AlbedoJudgeDetail }) {
  return (
    <article className={`rounded-lg border p-3 ${judgeStyle(judge.short_name)}`}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <h4 className="text-[12px] font-semibold">{judge.short_name}</h4>
          <p className="text-[9px] opacity-70 mt-0.5 truncate" title={judge.judge}>
            {judge.judge}
          </p>
        </div>
        <span className="text-[10px] mono opacity-80">{judge.duels} duels</span>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-3 text-[10px]">
        <Stat label="Avg challenger" value={fmtScore(judge.avg_challenger_score)} />
        <Stat label="Avg king" value={fmtScore(judge.avg_king_score)} />
        <Stat label="Picks challenger" value={fmtPct(judge.pick_challenger_pct)} />
        <Stat label="Agrees w/ verdict" value={fmtPct(judge.agree_verdict_pct)} />
        <Stat label="Split-panel align" value={fmtPct(judge.split_majority_align_pct)} />
        <Stat label="Solo dissent wins" value={fmtPct(judge.solo_dissent_win_pct)} />
        <Stat label="Extreme calls" value={fmtPct(judge.extreme_call_pct)} />
        <Stat label="Score σ" value={judge.score_std != null ? judge.score_std.toFixed(3) : "—"} />
      </div>

      <div className="flex flex-wrap gap-1.5 mt-3 text-[9px]">
        <span className="rounded px-1.5 py-0.5 bg-black/20">
          overturns {judge.overturn_duels}
        </span>
        <span className="rounded px-1.5 py-0.5 bg-black/20">
          3–0 ch {judge.unanimous_challenger_duels}
        </span>
        <span className="rounded px-1.5 py-0.5 bg-black/20">
          0–3 k {judge.unanimous_king_duels}
        </span>
        <span className="rounded px-1.5 py-0.5 bg-black/20">
          split {judge.split_duels}
        </span>
      </div>
    </article>
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

function ConsensusBar({
  rows,
}: {
  rows: { label: string; pct: number; duels: number; challenger_wins: number }[];
}) {
  const max = Math.max(...rows.map((r) => r.pct), 1);
  return (
    <div className="space-y-2">
      {rows.map((row) => (
        <div key={row.label} className="text-[10px]">
          <div className="flex justify-between text-zinc-400 mb-0.5">
            <span>{row.label}</span>
            <span className="mono">
              {row.duels} · ch {row.challenger_wins}/{row.duels}
            </span>
          </div>
          <div className="h-2 rounded bg-zinc-800 overflow-hidden">
            <div
              className="h-full rounded bg-sky-500/70"
              style={{ width: `${(row.pct / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function WinRateTable({ rows, showCoronations = false }: { rows: AlbedoWinRateRow[]; showCoronations?: boolean }) {
  if (!rows.length) return <p className="text-[10px] text-zinc-500">No data yet.</p>;
  return (
    <table className="w-full text-[10px]">
      <thead>
        <tr className="text-zinc-500 border-b border-zinc-800">
          <th className="text-left py-1 pr-2 font-medium">Entity</th>
          <th className="text-right py-1 px-1 font-medium">Duels</th>
          <th className="text-right py-1 px-1 font-medium">Win%</th>
          <th className="text-right py-1 px-1 font-medium">Margin</th>
          {showCoronations && <th className="text-right py-1 pl-1 font-medium">👑</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key} className="border-b border-zinc-800/50">
            <td className="py-1 pr-2 text-zinc-300 truncate max-w-[160px]" title={row.label}>
              {row.label}
            </td>
            <td className="text-right py-1 px-1 mono text-zinc-500">{row.duels}</td>
            <td className="text-right py-1 px-1 mono text-emerald-300">{fmtPct(row.win_pct)}</td>
            <td className="text-right py-1 px-1 mono text-zinc-500">{fmtMargin(row.avg_margin)}</td>
            {showCoronations && (
              <td className="text-right py-1 pl-1 mono text-amber-300">{row.coronations || "—"}</td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CrownLeaderboard({
  title,
  hint,
  rows,
  showColdkey = false,
}: {
  title: string;
  hint: string;
  rows: AlbedoCrownLeaderboardRow[];
  showColdkey?: boolean;
}) {
  if (!rows.length) {
    return (
      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200">{title}</h3>
        <p className="text-[10px] text-zinc-500 mt-2">No crown data yet.</p>
      </section>
    );
  }
  return (
    <section className="panel px-3 py-2">
      <h3 className="text-[11px] font-semibold text-zinc-200">{title}</h3>
      <p className="text-[9px] text-zinc-600 mt-0.5 mb-2">{hint}</p>
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left py-1 pr-2">{showColdkey ? "Coldkey" : "Repo"}</th>
            <th className="text-right py-1 px-1">👑</th>
            <th className="text-right py-1 px-1">Active</th>
            <th className="text-right py-1 px-1">Slot reward</th>
            <th className="text-right py-1 pl-1">Weight</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 12).map((row) => (
            <tr key={row.key} className="border-b border-zinc-800/50 align-top">
              <td className="py-1.5 pr-2">
                <p className="text-zinc-200 truncate max-w-[200px]" title={row.label}>
                  {showColdkey ? shortAddr(row.label, 6) : shortRepo(row.label, 34)}
                </p>
                {row.crown_events[0] && (
                  <p className="text-[9px] text-zinc-600 mt-0.5">
                    last v{row.crown_events[0].king_version} · {fmtTime(row.crown_events[0].crowned_at)}
                  </p>
                )}
              </td>
              <td className="text-right py-1.5 px-1 mono text-amber-300">{row.coronations}</td>
              <td className="text-right py-1.5 px-1 mono text-zinc-400">{fmtHours(row.total_active_hours)}</td>
              <td className="text-right py-1.5 px-1 mono text-emerald-300">{fmtHours(row.total_slot_hours)}</td>
              <td className="text-right py-1.5 pl-1 mono text-zinc-500">
                {row.current_weight_pct > 0 ? fmtPct(row.current_weight_pct) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function JudgeScoreCell({ vote }: { vote: AlbedoDuelJudgeVote | undefined }) {
  if (!vote) return <td className="py-1.5 px-1 text-center text-zinc-700">—</td>;
  const agree = vote.agrees_with_verdict;
  return (
    <td
      className={`py-1.5 px-1 text-center mono text-[10px] border-l border-zinc-800/50 ${
        agree ? "text-emerald-300 bg-emerald-500/5" : "text-rose-300 bg-rose-500/5"
      }`}
      title={`${vote.judge}\nch ${fmtScore(vote.challenger_score)} · k ${fmtScore(vote.king_score)}\n${agree ? "matches verdict" : "dissents"}`}
    >
      <div>{fmtScore(vote.challenger_score)}</div>
      <div className="text-[8px] opacity-70">{vote.pick_challenger ? "ch" : "k"}</div>
    </td>
  );
}

function judgeVoteMap(duel: AlbedoDuelSummary): Record<string, AlbedoDuelJudgeVote> {
  const map: Record<string, AlbedoDuelJudgeVote> = {};
  for (const v of duel.judge_votes ?? []) {
    map[v.short_name] = v;
  }
  return map;
}

const JUDGE_COLUMNS = ["glm-5.1", "qwen3.5-397b-a17b", "deepseek-v3.2"];

function DuelRow({ duel, judgeOrder }: { duel: AlbedoDuelSummary; judgeOrder: string[] }) {
  const won = duel.challenger_won;
  const votes = judgeVoteMap(duel);
  return (
    <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
      <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(duel.finished_at)}</td>
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
      <td className="py-1.5 pr-2 mono text-zinc-300">{fmtScore(duel.score_challenger)}</td>
      <td className={`py-1.5 pr-2 mono ${won ? "text-emerald-300" : "text-rose-300"}`}>{fmtMargin(duel.win_margin)}</td>
      <td className="py-1.5">
        <span
          className={`inline-block px-1.5 py-0.5 rounded text-[9px] border ${
            duel.coronated
              ? "text-amber-200 border-amber-500/40 bg-amber-500/15"
              : won
                ? "text-emerald-200 border-emerald-500/30 bg-emerald-500/10"
                : "text-zinc-400 border-zinc-700"
          }`}
        >
          {duel.coronated ? "crowned" : won ? "challenger" : "defended"}
        </span>
        {duel.panel_pattern && !duel.unanimous_panel && (
          <span className="block text-[8px] text-zinc-600 mt-0.5">{duel.panel_pattern.replace(/_/g, " ")}</span>
        )}
      </td>
    </tr>
  );
}

export default function AlbedoDuelPanel() {
  const { subnet } = useSubnet();
  const [data, setData] = useState<AlbedoAnalysisOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [section, setSection] = useState<Section>("overview");

  const refresh = useCallback(async () => {
    try {
      const overview = await api.getAlbedoAnalysis(subnet);
      setData(overview);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load duel analysis");
    } finally {
      setLoading(false);
    }
  }, [subnet]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  const judgeOrder = useMemo(() => {
    const fromApi = (data?.judge_details ?? []).map((j) => j.short_name);
    return fromApi.length ? fromApi : JUDGE_COLUMNS;
  }, [data]);

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

        {data.current_eval && (
          <div className="mt-2.5 rounded border border-sky-500/25 bg-sky-500/5 px-2.5 py-1.5 text-[10px] text-zinc-400">
            <span className="text-sky-300 font-medium">Live eval</span> {data.current_eval.state} ·{" "}
            {shortRepo(`${data.current_eval.namespace}/${data.current_eval.model_name}`, 28)} · uid{" "}
            {data.current_eval.uid}
          </div>
        )}
      </section>

      {section === "overview" && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {[
              { label: "Challenger wins", value: String(data.challenger_wins), accent: "text-emerald-300" },
              { label: "King defenses", value: String(data.king_wins), accent: "text-rose-300" },
              { label: "Challenger win %", value: fmtPct(data.challenger_win_pct) },
              { label: "Avg margin", value: fmtMargin(data.avg_win_margin) },
              { label: "Avg ch / k score", value: `${fmtScore(data.avg_challenger_score)} / ${fmtScore(data.avg_king_score)}` },
              { label: "Queue", value: String(data.queue_length) },
            ].map((kpi) => (
              <div key={kpi.label} className="panel px-2.5 py-2">
                <p className="text-[9px] uppercase tracking-wide text-zinc-500">{kpi.label}</p>
                <p className={`text-[14px] font-semibold mt-0.5 ${kpi.accent ?? "text-zinc-100"}`}>{kpi.value}</p>
              </div>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-3">
            <CrownLeaderboard
              title="Most crowns by repo"
              hint="Coronations and reward hours (active king + slot tenure) merged from on-chain commits"
              rows={data.crowns_by_repo ?? []}
            />
            <CrownLeaderboard
              title="Most crowns by coldkey"
              hint="Same reward time rollup grouped by owner coldkey"
              rows={data.crowns_by_coldkey ?? []}
              showColdkey
            />
          </div>

          <div className="grid lg:grid-cols-2 gap-3">
            <section className="panel px-3 py-2">
              <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Judge reliability snapshot</h3>
              <div className="grid sm:grid-cols-3 gap-2">
                {(data.judge_details ?? []).map((j) => (
                  <div key={j.judge} className={`rounded border px-2 py-1.5 text-[10px] ${judgeStyle(j.short_name)}`}>
                    <p className="font-medium">{j.short_name}</p>
                    <p className="mono mt-1">{fmtPct(j.agree_verdict_pct)} align</p>
                    <p className="mono text-[9px] opacity-80">{j.overturn_duels} overturns</p>
                  </div>
                ))}
              </div>
            </section>
            <section className="panel px-3 py-2">
              <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Top repos (challenger duels)</h3>
              <WinRateTable rows={(data.challenger_by_repo ?? []).slice(0, 8)} showCoronations />
            </section>
          </div>
        </>
      )}

      {section === "judges" && (
        <>
          <section className="panel px-3 py-2.5">
            <h3 className="text-[11px] font-semibold text-zinc-200">Judge ensemble detail</h3>
            <p className="text-[9px] text-zinc-600 mt-0.5 mb-3">
              GLM · Qwen · DeepSeek — per-judge challenger score, pick rate, and verdict alignment
            </p>
            <div className="grid md:grid-cols-3 gap-3">
              {(data.judge_details ?? []).map((j) => (
                <JudgeCard key={j.judge} judge={j} />
              ))}
            </div>
          </section>

          <div className="grid lg:grid-cols-2 gap-3">
            <section className="panel px-3 py-2">
              <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Panel consensus patterns</h3>
              <p className="text-[9px] text-zinc-600 mb-2">How often judges agree before final verdict</p>
              <ConsensusBar
                rows={(data.judge_consensus ?? []).map((c) => ({
                  label: c.label,
                  pct: c.pct,
                  duels: c.duels,
                  challenger_wins: c.challenger_wins,
                }))}
              />
            </section>
            <section className="panel px-3 py-2">
              <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Scoring metrics (challenger avg)</h3>
              <div className="space-y-1.5">
                {(data.metric_aggregates ?? []).map((m) => (
                  <div key={m.metric} className="flex items-center gap-2 text-[10px]">
                    <span className="w-20 text-zinc-400 capitalize">{m.metric}</span>
                    <div className="flex-1 h-2 rounded bg-zinc-800 overflow-hidden">
                      <div
                        className="h-full rounded bg-violet-500/60"
                        style={{ width: `${m.avg_challenger_score * 100}%` }}
                      />
                    </div>
                    <span className="w-10 text-right mono text-zinc-300">{fmtScore(m.avg_challenger_score)}</span>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      )}

      {section === "kings" && (
        <>
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

          <div className="grid lg:grid-cols-2 gap-3">
            <CrownLeaderboard
              title="Crown leaders by repo"
              hint="Full history — slot reward hours ≈ time earning weight"
              rows={data.crowns_by_repo ?? []}
            />
            <CrownLeaderboard
              title="Crown leaders by coldkey"
              hint="Owner-level crown count and cumulative reward time"
              rows={data.crowns_by_coldkey ?? []}
              showColdkey
            />
          </div>

          <section className="panel px-3 py-2">
            <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Coronation history (repo / coldkey)</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-1 pr-2">Ver</th>
                    <th className="text-left py-1 pr-2">When</th>
                    <th className="text-left py-1 pr-2">Repo</th>
                    <th className="text-left py-1 pr-2">Coldkey</th>
                    <th className="text-left py-1 pr-2">Defeated</th>
                    <th className="text-left py-1 pr-2">Margin</th>
                  </tr>
                </thead>
                <tbody>
                  {data.king_history.map((entry) => (
                    <tr key={entry.eval_run_id} className="border-b border-zinc-800/50">
                      <td className="py-1 pr-2 mono text-amber-300">v{entry.king_version}</td>
                      <td className="py-1 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(entry.finished_at)}</td>
                      <td className="py-1 pr-2 text-zinc-300 truncate max-w-[140px]" title={entry.repo ?? ""}>
                        {shortRepo(entry.repo ?? entry.model_name, 28)}
                      </td>
                      <td className="py-1 pr-2 mono text-zinc-500">{entry.coldkey ? shortAddr(entry.coldkey, 5) : "—"}</td>
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

      {section === "duels" && (
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-1">Judge duel scores</h3>
          <p className="text-[9px] text-zinc-600 mb-2">
            Each cell = challenger score from that judge · green = agrees with final verdict · spread = max−min judge score
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px] min-w-[720px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 pr-2">When</th>
                  <th className="text-left py-1 pr-2">Challenger repo</th>
                  <th className="text-left py-1 pr-2">King</th>
                  {judgeOrder.map((name) => (
                    <th key={name} className={`text-center py-1 px-1 border-l border-zinc-800/50 ${judgeStyle(name).split(" ")[2]}`}>
                      {name.split("-")[0]}
                    </th>
                  ))}
                  <th className="text-center py-1 px-1 text-zinc-600">σ spread</th>
                  <th className="text-left py-1 pr-2">Final</th>
                  <th className="text-left py-1 pr-2">Margin</th>
                  <th className="text-left py-1 pr-2">Result</th>
                </tr>
              </thead>
              <tbody>
                {data.recent_duels.map((duel) => (
                  <DuelRow key={duel.eval_run_id} duel={duel} judgeOrder={judgeOrder} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
