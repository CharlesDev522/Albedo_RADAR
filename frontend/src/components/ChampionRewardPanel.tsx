"use client";

import { shortAddr } from "@/lib/api";
import { useDashboardSync } from "@/lib/DashboardSyncContext";
import { getSubnetProfile } from "@/lib/subnets";
import { useSubnet } from "@/lib/useSubnet";

function fmtAlpha(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "—";
  if (n >= 100) return `${n.toFixed(1)} α`;
  if (n >= 1) return `${n.toFixed(2)} α`;
  return `${n.toFixed(4)} α`;
}

function fmtTao(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "—";
  if (n >= 100) return `${n.toFixed(1)} τ`;
  if (n >= 10) return `${n.toFixed(2)} τ`;
  if (n >= 0.01) return `${n.toFixed(4)} τ`;
  return `${n.toFixed(6)} τ`;
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n) || n <= 0) return "—";
  if (n >= 1000) return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtIncentive(n: number | null | undefined): string {
  if (n == null || n <= 0) return "—";
  if (n >= 0.999) return "100%";
  return `${(n * 100).toFixed(1)}%`;
}

export default function ChampionRewardPanel() {
  const { subnet } = useSubnet();
  const profile = getSubnetProfile(subnet);
  const { incentiveOverview, loading } = useDashboardSync();

  if (!profile.features.incentiveColumn) return null;

  const champion = incentiveOverview?.champion;
  const source = champion?.calculation_source ?? "metagraph";
  const epochs = champion?.epochs_per_day ?? 20;

  return (
    <section className="panel px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">Champion daily reward</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5 max-w-2xl">
            SN{subnet} top incentive miner · daily estimate matches TaoStats (
            {source === "taostats" ? "daily_reward from API" : `emission × ${epochs} epochs/day`})
          </p>
        </div>
        {champion && (
          <div className="text-right text-[10px] text-zinc-500">
            <p>
              uid <span className="mono text-zinc-300">{champion.uid ?? "—"}</span>
              {champion.hotkey && (
                <>
                  {" "}
                  · <span className="mono text-zinc-400">{shortAddr(champion.hotkey, 6)}</span>
                </>
              )}
            </p>
            <p className="text-[9px] text-zinc-600 mt-0.5">
              incentive {fmtIncentive(champion.incentive)}
              {champion.commit_repo ? ` · ${champion.commit_repo.split("/").pop()}` : ""}
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-2">
        <RewardKpi
          label="daily τ"
          value={loading && !champion ? "…" : fmtTao(champion?.daily_tao_equivalent)}
          accent="text-amber-300"
          hint={
            champion?.alpha_price_tao != null
              ? `${fmtAlpha(champion.daily_alpha)} × ${champion.alpha_price_tao.toFixed(4)} τ/α`
              : "α price × daily α"
          }
        />
        <RewardKpi
          label="daily α"
          value={loading && !champion ? "…" : fmtAlpha(champion?.daily_alpha)}
          accent="text-violet-300"
          hint={source === "taostats" ? "TaoStats daily_reward" : `epoch α × ${epochs}`}
        />
        <RewardKpi
          label="daily USD"
          value={loading && !champion ? "…" : fmtUsd(champion?.daily_usd)}
          accent="text-emerald-300"
          hint="daily τ × TAO/USD"
        />
        <RewardKpi
          label="per epoch"
          value={loading && !champion ? "…" : fmtAlpha(champion?.emission_per_epoch_alpha)}
          accent="text-sky-300"
          hint="α per tempo (~360 blocks)"
        />
      </div>

      {!loading && !champion && (
        <p className="text-[10px] text-zinc-500 mt-2">
          No incentivized champion yet — waiting for metagraph incentive data.
        </p>
      )}
    </section>
  );
}

function RewardKpi({
  label,
  value,
  accent,
  hint,
}: {
  label: string;
  value: string;
  accent: string;
  hint?: string;
}) {
  return (
    <div className="rounded border border-zinc-800/80 bg-zinc-950/40 px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wider text-zinc-600">{label}</p>
      <p className={`text-[14px] font-medium tabular-nums mono ${accent}`}>{value}</p>
      {hint && <p className="text-[8px] text-zinc-600 mt-0.5">{hint}</p>}
    </div>
  );
}
