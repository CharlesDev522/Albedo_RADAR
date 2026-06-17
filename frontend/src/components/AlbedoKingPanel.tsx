"use client";

import { hippiusModelUrl, shortAddr, shortRepo } from "@/lib/api";
import { useDashboardSync } from "@/lib/DashboardSyncContext";
import { useSubnet } from "@/lib/useSubnet";

const ALBEDO_DASHBOARD = "https://us-east-1.hippius.com/albedo/index.html";

function pct(n: number): string {
  if (n <= 0) return "0";
  if (n >= 0.999) return "100%";
  return `${(n * 100).toFixed(2)}%`;
}

export default function AlbedoKingPanel() {
  const { subnet } = useSubnet();
  const { albedoStatus, incentiveOverview } = useDashboardSync();
  const king = albedoStatus?.king;
  const topIncentive = incentiveOverview?.miners.find((m) => m.receiving_incentive);

  return (
    <section className="panel p-3 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">Albedo king · SN{subnet}</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Winner-take-all subnet — duel king gets validator weight 1.0 → metagraph incentive
          </p>
        </div>
        <a
          href={ALBEDO_DASHBOARD}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[10px] text-amber-400/90 hover:text-amber-300 border border-amber-500/30 rounded px-2 py-0.5"
        >
          official dashboard ↗
        </a>
      </div>

      {king ? (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 p-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="pill-king text-[9px]">👑 reign #{king.reign_number ?? "—"}</span>
            <span className="text-[11px] font-medium text-amber-100">
              uid {king.uid ?? "—"} · {shortAddr(king.hotkey)}
            </span>
            {king.weight_share != null && (
              <span className="text-[10px] text-amber-300/80">
                weight share {pct(king.weight_share)}
              </span>
            )}
          </div>
          {king.model_repo && (
            <a
              href={hippiusModelUrl(king.model_repo)}
              target="_blank"
              rel="noopener noreferrer"
              className="block mt-1 text-[10px] text-amber-200/90 hover:underline truncate"
              title={king.model_repo}
            >
              {shortRepo(king.model_repo)}
            </a>
          )}
          {king.crowned_at && (
            <p className="text-[9px] text-zinc-500 mt-1">crowned {new Date(king.crowned_at).toLocaleString()}</p>
          )}
        </div>
      ) : (
        <p className="text-[10px] text-zinc-500">Loading king from Hippius dashboard…</p>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2 text-[10px]">
        <MiniStat label="queue" value={String(albedoStatus?.queue_len ?? "—")} />
        <MiniStat label="evals accepted" value={String(albedoStatus?.stats.accepted ?? "—")} accent />
        <MiniStat label="rejected" value={String(albedoStatus?.stats.rejected ?? "—")} />
        <MiniStat label="failed" value={String(albedoStatus?.stats.failed ?? "—")} />
        <MiniStat
          label="receiving incentive"
          value={String(incentiveOverview?.incentivized_count ?? "—")}
          accent
        />
        <MiniStat
          label="top incentive"
          value={topIncentive ? pct(topIncentive.incentive) : "—"}
          accent
        />
      </div>

      {incentiveOverview && incentiveOverview.miners.length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Top incentive (metagraph)</h3>
          <div className="overflow-x-auto">
            <table className="tbl w-full">
              <thead>
                <tr>
                  <th>uid</th>
                  <th>incentive</th>
                  <th>emission</th>
                  <th>king</th>
                  <th>commit</th>
                </tr>
              </thead>
              <tbody>
                {incentiveOverview.miners.slice(0, 8).map((m) => (
                  <tr key={m.uid} className={m.is_king ? "bg-amber-500/5" : ""}>
                    <td className="mono">{m.uid}</td>
                    <td className={m.receiving_incentive ? "text-lime-400" : "text-zinc-500"}>
                      {pct(m.incentive)}
                    </td>
                    <td className="text-zinc-400">{m.emission.toFixed(4)}</td>
                    <td>{m.is_king ? <span className="pill-king">king</span> : "—"}</td>
                    <td className="truncate max-w-[140px]">
                      {m.commit_repo ? shortRepo(m.commit_repo) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {albedoStatus && albedoStatus.recent_history.length > 0 && (
        <div>
          <h3 className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Recent duels</h3>
          <ul className="space-y-1 max-h-32 overflow-y-auto text-[10px]">
            {albedoStatus.recent_history.slice(0, 6).map((h, i) => (
              <li key={`${h.eval_id}-${i}`} className="flex flex-wrap gap-x-2 text-zinc-400">
                <span className="mono text-zinc-500">{h.eval_id ?? h.type}</span>
                {h.uid != null && <span>uid {h.uid}</span>}
                {h.type === "verdict" && (
                  <span className={h.accepted ? "text-lime-400" : "text-zinc-500"}>
                    {h.accepted ? "crowned" : h.winner === "king" ? "king held" : "no crown"}
                  </span>
                )}
                {h.type === "failure" && (
                  <span className="text-rose-400/80 truncate">{h.code ?? "failed"}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
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
      <p className={`text-[12px] font-semibold ${accent ? "text-lime-400" : "text-zinc-200"}`}>
        {value}
      </p>
    </div>
  );
}
