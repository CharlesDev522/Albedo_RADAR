"use client";

import { useEffect, useState } from "react";
import { api, type MarketOverview } from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

function fmtUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 1000) return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtTao(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  if (n >= 10) return `${n.toFixed(2)} τ`;
  return `${n.toFixed(4)} τ`;
}

export default function MarketTicker() {
  const { subnet } = useSubnet();
  const [market, setMarket] = useState<MarketOverview | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const data = await api.getMarketOverview(subnet);
        if (!cancelled) {
          setMarket(data);
          setError(false);
        }
      } catch {
        if (!cancelled) setError(true);
      }
    };

    void load();
    const interval = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [subnet]);

  if (error && !market) return null;

  return (
    <div
      className="hidden lg:flex items-center gap-2 text-[10px] text-zinc-500 border border-zinc-800/80 rounded-md px-2 py-1 bg-zinc-900/50"
      title={
        market?.tao_price_source
          ? `TAO price via ${market.tao_price_source} · reg burn from chain`
          : "Market overview"
      }
    >
      <TickerStat label="TAO" value={fmtUsd(market?.tao_price_usd)} accent="text-emerald-300" />
      <span className="text-zinc-700">·</span>
      <TickerStat
        label={`SN${subnet} reg`}
        value={fmtTao(market?.registration_burn_tao)}
        sub={market?.registration_burn_usd != null ? fmtUsd(market.registration_burn_usd) : undefined}
        accent="text-amber-300"
      />
      {market?.alpha_price_tao != null && (
        <>
          <span className="text-zinc-700">·</span>
          <TickerStat label="α" value={fmtTao(market.alpha_price_tao)} accent="text-violet-300" />
        </>
      )}
    </div>
  );
}

function TickerStat({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent: string;
}) {
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
      <span className="uppercase tracking-wide text-zinc-600">{label}</span>
      <span className={`mono font-medium ${accent}`}>{value}</span>
      {sub && <span className="mono text-zinc-600">{sub}</span>}
    </span>
  );
}
