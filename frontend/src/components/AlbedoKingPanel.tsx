"use client";

import { hippiusModelUrl, shortAddr, shortRepo } from "@/lib/api";
import { useDashboardSync } from "@/lib/DashboardSyncContext";
import { useSubnet } from "@/lib/useSubnet";

const ALBEDO_DASHBOARD = "https://us-east-1.hippius.com/albedo/index.html";

function pct(n: number | null | undefined, digits = 1): string {
  if (n == null || n <= 0) return "—";
  if (n >= 0.999) return "100%";
  return `${(n * 100).toFixed(digits)}%`;
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

function duelBadge(badge: string): string {
  if (badge === "crowned") return "pill-king";
  if (badge === "won") return "pill-v6";
  return "pill-none";
}

export default function AlbedoKingPanel() {
  const { subnet } = useSubnet();
  const { albedoStatus, incentiveOverview } = useDashboardSync();
  const king = albedoStatus?.current_king;
  const topIncentive = incentiveOverview?.miners.find((m) => m.receiving_incentive);

  return (
    <section className="panel overflow-hidden">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">Albedo king · SN{subnet}</h2>
          <p className="text-[10px] text-zinc-500">
            Live from Hippius <code className="mono">data/dashboard.json</code>
            {albedoStatus?.updated_at && (
              <> · {fmtTime(albedoStatus.updated_at)}</>
            )}
          </p>
        </div>
        <a
          href={ALBEDO_DASHBOARD}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] text-amber-400/90 hover:text-amber-300 border border-amber-500/30 rounded px-2 py-0.5"
        >
          official ↗
        </a>
      </div>

      <div className="p-3 space-y-3">
        {king ? (
          <div className="rounded-lg border border-amber-500/35 bg-gradient-to-br from-amber-500/10 to-zinc-900/40 p-3">
            <div className="text-[10px] uppercase tracking-widest text-amber-400/80 mb-1">
              reigning champion
            </div>
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-[18px] font-bold text-amber-100 tracking-tight">
                {king.title ?? `v${king.king_version}`}
              </span>
              <span className="text-[11px] text-zinc-400">
                uid {king.uid ?? "—"} · {king.hf_account ?? "—"}
              </span>
            </div>
            {king.model_repo && (
              <a
                href={hippiusModelUrl(king.model_repo)}
                target="_blank"
                rel="noopener noreferrer"
                className="block mt-1 text-[11px] text-amber-200/90 hover:underline truncate"
              >
                {shortRepo(king.model_repo)}
              </a>
            )}
            <div className="mt-2 flex flex-wrap gap-3 text-[10px] text-zinc-500">
              <span className="mono">{shortAddr(king.hotkey ?? "", 8)}</span>
              {king.weight_pct != null && <span>weight {king.weight_pct}%</span>}
              {king.score_challenger != null && (
                <span>
                  last duel {pct(king.score_challenger)} vs {pct(king.score_king)}
                </span>
              )}
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-zinc-500">Loading king from Hippius…</p>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
          <MiniStat label="evaluated" value={String(albedoStatus?.stats?.evaluated ?? "—")} accent />
          <MiniStat label="queue" value={String(albedoStatus?.queue_len ?? "—")} />
          <MiniStat
            label="pipeline"
            value={String(albedoStatus?.pipeline?.total_in_flight ?? 0)}
          />
          <MiniStat label="duels" value={String(albedoStatus?.recent_duels.length ?? "—")} />
          <MiniStat label="crownings" value={String(albedoStatus?.crownings.length ?? "—")} accent />
          <MiniStat
            label="incentivized"
            value={String(incentiveOverview?.incentivized_count ?? "—")}
            accent
          />
          <MiniStat
            label="top incentive"
            value={topIncentive ? pct(topIncentive.incentive) : "—"}
            accent
          />
        </div>

        {albedoStatus && albedoStatus.reign_chain.length > 0 && (
          <div>
            <h3 className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">
              reign chain · weight holders
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
              {albedoStatus.reign_chain.map((m) => {
                const isCurrent = m.king_version === king?.king_version;
                return (
                  <div
                    key={`${m.king_version}-${m.uid}`}
                    className={`rounded border p-2 ${
                      isCurrent
                        ? "border-amber-500/40 bg-amber-500/10"
                        : "border-zinc-800 bg-zinc-900/30"
                    }`}
                  >
                    <div className="text-[10px] font-semibold text-zinc-200">
                      {m.title ?? `v${m.king_version}`}
                    </div>
                    <div className="text-[9px] text-zinc-500 truncate mt-0.5">
                      {m.hf_account ?? shortRepo(m.model_repo ?? "")}
                    </div>
                    <div className="text-[9px] text-zinc-600 mt-1">uid {m.uid ?? "—"}</div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {albedoStatus && albedoStatus.recent_duels.length > 0 && (
          <div>
            <h3 className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
              recent duels
            </h3>
            <div className="overflow-x-auto max-h-[220px] overflow-y-auto rounded border border-zinc-800/80">
              <table className="tbl w-full">
                <thead className="sticky top-0 z-10 bg-zinc-950">
                  <tr>
                    <th>eval</th>
                    <th>uid</th>
                    <th>hf</th>
                    <th>score</th>
                    <th>margin</th>
                    <th>result</th>
                    <th>dethroned</th>
                    <th>time</th>
                  </tr>
                </thead>
                <tbody>
                  {albedoStatus.recent_duels.slice(0, 15).map((d) => (
                    <tr
                      key={d.eval_run_id ?? `${d.uid}-${d.finished_at}`}
                      className={d.coronated ? "bg-amber-500/5" : ""}
                    >
                      <td className="mono text-[9px] text-zinc-500 max-w-[72px] truncate">
                        {d.eval_run_id?.slice(0, 8) ?? "—"}
                      </td>
                      <td className="mono">{d.uid ?? "—"}</td>
                      <td className="truncate max-w-[80px]">{d.hf_account ?? "—"}</td>
                      <td className="mono text-[9px]">
                        {pct(d.score_challenger, 0)} / {pct(d.score_king, 0)}
                      </td>
                      <td className="mono text-[9px]">{pct(d.win_margin, 1)}</td>
                      <td>
                        <span className={duelBadge(d.badge)}>{d.badge}</span>
                      </td>
                      <td className="text-[9px] text-rose-300/70">
                        {d.defeated_king_hf ?? "—"}
                      </td>
                      <td className="text-[9px] text-zinc-500 whitespace-nowrap">
                        {fmtTime(d.finished_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function MiniStat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wide text-zinc-600">{label}</p>
      <p className={`text-[12px] font-semibold tabular-nums ${accent ? "text-lime-400" : "text-zinc-200"}`}>
        {value}
      </p>
    </div>
  );
}
