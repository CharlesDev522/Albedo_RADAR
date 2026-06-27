"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  hippiusModelUrl,
  shortAddr,
  shortRepo,
  type AlbedoAnalysisOverview,
  type AlbedoDuelSummary,
  type AlbedoKingCoronation,
  type AlbedoWinRateRow,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const POLL_MS = 30_000;

function fmtPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function fmtScore(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return (n * 100).toFixed(1) + "%";
}

function fmtMargin(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const pct = n * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
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
  const repo = modelUri.split("@")[0];
  return hippiusModelUrl(repo);
}

function Kpi({
  label,
  value,
  hint,
  accent = "text-zinc-200",
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/50 px-2.5 py-2">
      <p className="text-[9px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`text-[15px] font-semibold mt-0.5 ${accent}`}>{value}</p>
      {hint && <p className="text-[9px] text-zinc-600 mt-0.5">{hint}</p>}
    </div>
  );
}

function HorizontalBarChart({
  rows,
  maxBars = 10,
  color = "bg-emerald-500/70",
}: {
  rows: { label: string; value: number }[];
  maxBars?: number;
  color?: string;
}) {
  const top = rows.slice(0, maxBars);
  const max = Math.max(...top.map((r) => r.value), 1);
  return (
    <div className="space-y-1.5">
      {top.map((row) => (
        <div key={row.label} className="flex items-center gap-2 text-[10px]">
          <span className="w-28 truncate text-zinc-400" title={row.label}>
            {row.label}
          </span>
          <div className="flex-1 h-3 rounded bg-zinc-800/80 overflow-hidden">
            <div
              className={`h-full rounded ${color}`}
              style={{ width: `${(row.value / max) * 100}%` }}
            />
          </div>
          <span className="w-10 text-right mono text-zinc-300">{fmtPct(row.value)}</span>
        </div>
      ))}
    </div>
  );
}

function HistogramChart({
  buckets,
}: {
  buckets: { label: string; count: number }[];
}) {
  const max = Math.max(...buckets.map((b) => b.count), 1);
  const w = 320;
  const h = 80;
  const barW = w / buckets.length - 4;
  return (
    <svg viewBox={`0 0 ${w} ${h + 24}`} className="w-full max-w-md h-auto">
      {buckets.map((b, i) => {
        const barH = (b.count / max) * h;
        const x = i * (barW + 4) + 2;
        const y = h - barH;
        return (
          <g key={b.label}>
            <rect
              x={x}
              y={y}
              width={barW}
              height={barH}
              rx={2}
              className="fill-violet-500/60"
            />
            <text
              x={x + barW / 2}
              y={h + 12}
              textAnchor="middle"
              className="fill-zinc-500 text-[7px]"
            >
              {b.label.replace(" to ", "–").replace("%", "")}
            </text>
            {b.count > 0 && (
              <text
                x={x + barW / 2}
                y={y - 2}
                textAnchor="middle"
                className="fill-zinc-400 text-[8px]"
              >
                {b.count}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function TimelineChart({
  points,
}: {
  points: { date: string; duels: number; challenger_win_pct: number }[];
}) {
  if (points.length < 2) {
    return <p className="text-[10px] text-zinc-500">Not enough timeline data yet.</p>;
  }
  const w = 360;
  const h = 72;
  const pad = 8;
  const xs = points.map((_, i) => pad + (i / (points.length - 1)) * (w - pad * 2));
  const ys = points.map((p) => h - pad - (p.challenger_win_pct / 100) * (h - pad * 2));
  const path = xs.map((x, i) => `${i === 0 ? "M" : "L"}${x},${ys[i]}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-lg h-auto">
      <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} className="stroke-zinc-700" strokeWidth={1} />
      <line x1={pad} y1={pad} x2={pad} y2={h - pad} className="stroke-zinc-700" strokeWidth={1} />
      <path d={path} fill="none" className="stroke-sky-400" strokeWidth={2} />
      {xs.map((x, i) => (
        <circle key={points[i].date} cx={x} cy={ys[i]} r={2.5} className="fill-sky-300" />
      ))}
      <text x={pad} y={pad + 4} className="fill-zinc-500 text-[8px]">
        challenger win %
      </text>
    </svg>
  );
}

function WinRateTable({ rows, showCoronations = false }: { rows: AlbedoWinRateRow[]; showCoronations?: boolean }) {
  if (!rows.length) {
    return <p className="text-[10px] text-zinc-500">No data yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[10px]">
        <thead>
          <tr className="text-zinc-500 border-b border-zinc-800">
            <th className="text-left py-1 pr-2 font-medium">Entity</th>
            <th className="text-right py-1 px-1 font-medium">Duels</th>
            <th className="text-right py-1 px-1 font-medium">Wins</th>
            <th className="text-right py-1 px-1 font-medium">Win%</th>
            <th className="text-right py-1 px-1 font-medium">Avg margin</th>
            {showCoronations && <th className="text-right py-1 pl-1 font-medium">Crowns</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-zinc-800/60 hover:bg-zinc-800/30">
              <td className="py-1 pr-2 text-zinc-300 truncate max-w-[180px]" title={row.label}>
                {row.label}
              </td>
              <td className="text-right py-1 px-1 mono text-zinc-400">{row.duels}</td>
              <td className="text-right py-1 px-1 mono text-zinc-400">{row.wins}</td>
              <td className="text-right py-1 px-1 mono text-emerald-300">{fmtPct(row.win_pct)}</td>
              <td className="text-right py-1 px-1 mono text-zinc-400">{fmtMargin(row.avg_margin)}</td>
              {showCoronations && (
                <td className="text-right py-1 pl-1 mono text-amber-300">{row.coronations || "—"}</td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DuelRow({ duel }: { duel: AlbedoDuelSummary }) {
  const won = duel.challenger_won;
  return (
    <tr className="border-b border-zinc-800/60 hover:bg-zinc-800/30">
      <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(duel.finished_at)}</td>
      <td className="py-1.5 pr-2">
        <a
          href={modelLink(duel.model_uri)}
          target="_blank"
          rel="noreferrer"
          className="text-sky-300 hover:underline truncate block max-w-[160px]"
          title={duel.model_uri}
        >
          {shortRepo(`${duel.namespace}/${duel.model_name}`, 32)}
        </a>
        <span className="text-[9px] text-zinc-600 mono">uid {duel.uid}</span>
      </td>
      <td className="py-1.5 pr-2 text-zinc-500 truncate max-w-[120px]" title={duel.king_model_name ?? ""}>
        vs {duel.king_model_name ? shortRepo(duel.king_model_name, 18) : "—"}
      </td>
      <td className="py-1.5 pr-2 mono text-zinc-300">{fmtScore(duel.score_challenger)}</td>
      <td className="py-1.5 pr-2 mono text-zinc-300">{fmtScore(duel.score_king)}</td>
      <td className={`py-1.5 pr-2 mono ${won ? "text-emerald-300" : "text-rose-300"}`}>
        {fmtMargin(duel.win_margin)}
      </td>
      <td className="py-1.5">
        <span
          className={`inline-block px-1.5 py-0.5 rounded text-[9px] border ${
            duel.coronated
              ? "text-amber-200 border-amber-500/40 bg-amber-500/15"
              : won
                ? "text-emerald-200 border-emerald-500/30 bg-emerald-500/10"
                : "text-zinc-400 border-zinc-700 bg-zinc-800/50"
          }`}
        >
          {duel.coronated ? "👑 crowned" : won ? "challenger" : "king held"}
        </span>
      </td>
    </tr>
  );
}

function KingHistoryRow({ entry }: { entry: AlbedoKingCoronation }) {
  return (
    <tr className="border-b border-zinc-800/60 hover:bg-zinc-800/30">
      <td className="py-1.5 pr-2 mono text-amber-300">v{entry.king_version}</td>
      <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(entry.finished_at)}</td>
      <td className="py-1.5 pr-2">
        <a
          href={modelLink(entry.model_uri)}
          target="_blank"
          rel="noreferrer"
          className="text-sky-300 hover:underline"
          title={entry.model_uri}
        >
          {shortRepo(`${entry.namespace}/${entry.model_name}`, 28)}
        </a>
      </td>
      <td className="py-1.5 pr-2 mono text-zinc-400">uid {entry.uid}</td>
      <td className="py-1.5 pr-2 text-zinc-500 truncate max-w-[120px]">
        {entry.defeated_model_name ? `beat ${shortRepo(entry.defeated_model_name, 16)}` : "—"}
      </td>
      <td className="py-1.5 pr-2 mono text-emerald-300">{fmtMargin(entry.win_margin)}</td>
    </tr>
  );
}

export default function AlbedoDuelPanel() {
  const { subnet } = useSubnet();
  const [data, setData] = useState<AlbedoAnalysisOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  const namespaceChart = useMemo(
    () =>
      (data?.challenger_by_namespace ?? []).map((r) => ({
        label: r.label,
        value: r.win_pct,
      })),
    [data]
  );

  const kingDefenseChart = useMemo(
    () =>
      (data?.king_defense_by_model ?? []).map((r) => ({
        label: r.label,
        value: r.win_pct,
      })),
    [data]
  );

  const judgeChart = useMemo(
    () =>
      (data?.judge_aggregates ?? []).map((j) => ({
        label: j.judge.split("/").pop() ?? j.judge,
        value: j.avg_challenger_score * 100,
      })),
    [data]
  );

  const metricChart = useMemo(
    () =>
      (data?.metric_aggregates ?? []).map((m) => ({
        label: m.metric,
        value: m.avg_challenger_score * 100,
      })),
    [data]
  );

  if (loading && !data) {
    return <div className="panel p-4 text-[10px] text-zinc-500">Loading duel analysis…</div>;
  }

  if (error && !data) {
    return (
      <div className="panel p-4 text-[10px] text-rose-300">
        Duel analysis unavailable: {error}
      </div>
    );
  }

  if (!data) return null;

  const king = data.current_king;

  return (
    <div className="space-y-3">
      <section className="panel px-3 py-2">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[12px] font-semibold text-zinc-100">Albedo duel analysis</h2>
            <p className="text-[10px] text-zinc-500 mt-0.5 max-w-3xl">
              Live king-of-the-hill data from{" "}
              <a
                href="https://us-east-1.hippius.com/albedo/index.html"
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline"
              >
                Hippius Albedo dashboard
              </a>
              {" · "}
              {data.total_duels} evaluated duels · updated {fmtTime(data.updated_at)}
            </p>
          </div>
          {king && (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-right">
              <p className="text-[9px] uppercase tracking-wide text-amber-400/80">Current king</p>
              <p className="text-[11px] font-semibold text-amber-100 mt-0.5">
                v{king.king_version} · {shortRepo(`${king.namespace}/${king.model_name}`, 36)}
              </p>
              <p className="text-[9px] text-zinc-500 mt-0.5">
                uid {king.uid} · {shortAddr(king.hotkey, 5)} · {king.weight_bps / 100}% weight
              </p>
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 mt-3">
          <Kpi label="Challenger wins" value={String(data.challenger_wins)} accent="text-emerald-300" />
          <Kpi label="King defenses" value={String(data.king_wins)} accent="text-rose-300" />
          <Kpi label="Challenger win %" value={fmtPct(data.challenger_win_pct)} />
          <Kpi label="Coronations" value={String(data.coronations)} accent="text-amber-300" />
          <Kpi label="Avg margin" value={fmtMargin(data.avg_win_margin)} />
          <Kpi
            label="Avg scores"
            value={`${fmtScore(data.avg_challenger_score)} / ${fmtScore(data.avg_king_score)}`}
            hint="challenger / king"
          />
        </div>

        {data.current_eval && (
          <div className="mt-2 rounded border border-sky-500/25 bg-sky-500/5 px-2.5 py-2 text-[10px]">
            <span className="text-sky-300 font-medium">Live eval</span>
            <span className="text-zinc-500 ml-2">{data.current_eval.state}</span>
            <span className="text-zinc-400 ml-2">
              {shortRepo(`${data.current_eval.namespace}/${data.current_eval.model_name}`, 32)} · uid{" "}
              {data.current_eval.uid}
            </span>
            {data.current_eval.sample_count != null && (
              <span className="text-zinc-600 ml-2">
                samples {data.current_eval.generated_sample_count ?? 0}/{data.current_eval.sample_count}
              </span>
            )}
          </div>
        )}
      </section>

      <div className="grid lg:grid-cols-2 gap-3">
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200">Challenger win % by namespace</h3>
          <p className="text-[9px] text-zinc-600 mb-2">Top orgs with ≥2 duels</p>
          <HorizontalBarChart rows={namespaceChart} color="bg-emerald-500/70" />
        </section>

        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200">King defense rate by model</h3>
          <p className="text-[9px] text-zinc-600 mb-2">How often each reigning model held the crown</p>
          <HorizontalBarChart rows={kingDefenseChart} color="bg-rose-500/60" />
        </section>

        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200">Judge scoring (challenger avg)</h3>
          <HorizontalBarChart rows={judgeChart} color="bg-sky-500/60" maxBars={6} />
        </section>

        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200">Metric breakdown (challenger avg)</h3>
          <HorizontalBarChart rows={metricChart} color="bg-violet-500/60" maxBars={8} />
        </section>
      </div>

      <div className="grid lg:grid-cols-2 gap-3">
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200">Win margin distribution</h3>
          <HistogramChart buckets={data.margin_histogram} />
        </section>

        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200">Daily challenger win rate</h3>
          <TimelineChart points={data.timeline} />
        </section>
      </div>

      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">King history (coronations)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">Version</th>
                <th className="text-left py-1 pr-2">When</th>
                <th className="text-left py-1 pr-2">New king</th>
                <th className="text-left py-1 pr-2">UID</th>
                <th className="text-left py-1 pr-2">Defeated</th>
                <th className="text-left py-1 pr-2">Margin</th>
              </tr>
            </thead>
            <tbody>
              {data.king_history.map((entry) => (
                <KingHistoryRow key={entry.eval_run_id} entry={entry} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200 mb-1">Reign chain (weight slots)</h3>
        <p className="text-[9px] text-zinc-600 mb-2">Current 5-slot king lineage from dashboard reign</p>
        <div className="flex flex-wrap gap-2">
          {data.reign.map((m) => (
            <div
              key={m.king_version}
              className="rounded border border-zinc-800 bg-zinc-900/50 px-2 py-1.5 text-[10px] min-w-[140px]"
            >
              <p className="text-amber-300 font-medium">v{m.king_version}</p>
              <p className="text-zinc-300 truncate" title={m.model_name}>
                {shortRepo(m.model_name, 22)}
              </p>
              <p className="text-[9px] text-zinc-600">uid {m.uid} · {m.weight_bps / 100}%</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid lg:grid-cols-2 gap-3">
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Top challengers by hotkey</h3>
          <WinRateTable rows={data.challenger_by_hotkey} showCoronations />
        </section>
        <section className="panel px-3 py-2">
          <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Top namespaces</h3>
          <WinRateTable rows={data.challenger_by_namespace} showCoronations />
        </section>
      </div>

      <section className="panel px-3 py-2">
        <h3 className="text-[11px] font-semibold text-zinc-200 mb-2">Recent duels</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-[10px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">When</th>
                <th className="text-left py-1 pr-2">Challenger</th>
                <th className="text-left py-1 pr-2">King</th>
                <th className="text-left py-1 pr-2">Ch score</th>
                <th className="text-left py-1 pr-2">K score</th>
                <th className="text-left py-1 pr-2">Margin</th>
                <th className="text-left py-1 pr-2">Result</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_duels.map((duel) => (
                <DuelRow key={duel.eval_run_id} duel={duel} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
