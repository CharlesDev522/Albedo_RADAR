"use client";

import { shortAddr } from "@/lib/api";
import { useDashboardSync } from "@/lib/DashboardSyncContext";

function pctRate(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function barWidth(n: number, max: number): string {
  if (max <= 0) return "0%";
  return `${Math.min(100, Math.round((n / max) * 100))}%`;
}

export default function AlbedoAnalyticsPanel() {
  const { albedoAnalytics } = useDashboardSync();
  const summary = albedoAnalytics?.summary;
  const accounts = albedoAnalytics?.accounts ?? [];
  const maxCrowns = Math.max(...accounts.map((a) => a.crowns), 1);

  if (!albedoAnalytics) {
    return (
      <section className="panel p-4 text-[10px] text-zinc-500">
        Loading HF account analytics…
      </section>
    );
  }

  return (
    <section className="panel overflow-hidden">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">HF account analytics</h2>
          <p className="text-[10px] text-zinc-500">
            Crowns & dethrones per Hippius namespace · {summary?.unique_hf_accounts ?? 0} accounts
          </p>
        </div>
        {summary?.top_crown_holder && (
          <span className="text-[10px] text-amber-300/80">
            top holder <strong>{summary.top_crown_holder}</strong> (
            {pctRate(summary.crown_share_top)} of crowns)
          </span>
        )}
      </div>

      <div className="p-3 space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Kpi label="duels" value={String(summary?.total_eval_runs ?? 0)} />
          <Kpi label="crownings" value={String(summary?.total_crownings ?? 0)} accent />
          <Kpi label="hf accounts" value={String(summary?.unique_hf_accounts ?? 0)} />
          <Kpi
            label="dominant"
            value={summary?.top_crown_holder ?? "—"}
            accent
          />
        </div>

        <div className="overflow-x-auto max-h-[420px] overflow-y-auto rounded border border-zinc-800/80">
          <table className="tbl w-full">
            <thead className="sticky top-0 z-10 bg-zinc-950">
              <tr>
                <th>hf account</th>
                <th>crowns</th>
                <th>dethrones</th>
                <th>dethroned</th>
                <th>duels</th>
                <th>win%</th>
                <th>crown%</th>
                <th>coldkeys</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center text-zinc-500 py-6">
                    no duel data yet
                  </td>
                </tr>
              ) : (
                accounts.map((a) => (
                  <tr key={a.hf_account} className={a.crowns > 0 ? "bg-amber-500/[0.03]" : ""}>
                    <td>
                      <div className="font-medium text-zinc-200">{a.hf_account}</div>
                      <div className="mt-1 h-1 rounded bg-zinc-800 overflow-hidden w-24">
                        <div
                          className="h-full bg-amber-500/60"
                          style={{ width: barWidth(a.crowns, maxCrowns) }}
                        />
                      </div>
                    </td>
                    <td className="text-amber-300 font-semibold tabular-nums">{a.crowns}</td>
                    <td className="text-lime-400/90 tabular-nums">{a.dethrones_caused}</td>
                    <td className="text-rose-300/80 tabular-nums">{a.times_dethroned}</td>
                    <td className="text-zinc-400 tabular-nums">{a.challenges}</td>
                    <td className="mono text-[10px]">{pctRate(a.win_rate)}</td>
                    <td className="mono text-[10px] text-amber-200/80">{pctRate(a.crown_rate)}</td>
                    <td className="text-[9px] text-zinc-500 max-w-[120px]">
                      {a.coldkeys.length > 0
                        ? a.coldkeys.map((c) => shortAddr(c, 4)).join(", ")
                        : `${a.hotkey_count} hk`}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <p className="text-[9px] text-zinc-600 leading-relaxed">
          <strong className="text-zinc-500">crowns</strong> = duel wins that passed margin + LCB gate.
          <strong className="text-zinc-500 ml-2">dethrones</strong> = crowns where this account beat the prior king.
          <strong className="text-zinc-500 ml-2">dethroned</strong> = times another account took their crown.
          Coldkeys are joined from on-chain registry when available.
        </p>
      </div>
    </section>
  );
}

function Kpi({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 px-2.5 py-2">
      <p className="text-[9px] uppercase tracking-wide text-zinc-600">{label}</p>
      <p
        className={`text-[13px] font-semibold truncate ${
          accent ? "text-amber-300" : "text-zinc-100"
        }`}
      >
        {value}
      </p>
    </div>
  );
}
