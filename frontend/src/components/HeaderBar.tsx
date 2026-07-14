"use client";

import DashboardTabs from "@/components/DashboardTabs";
import MarketTicker from "@/components/MarketTicker";
import { DASHBOARD_TABS, getSubnetProfile } from "@/lib/subnets";
import { useSubnet } from "@/lib/useSubnet";

export default function HeaderBar() {
  const { subnet, view } = useSubnet();
  const profile = getSubnetProfile(subnet);
  const activeTab = DASHBOARD_TABS.find((t) => t.view === view);
  const subtitle =
    view === "clusters" ? (activeTab?.hint ?? "Miner clusters") : profile.tagline;

  return (
    <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-[1400px] mx-auto px-3 py-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
            <span className="text-emerald-400 font-mono text-[10px] font-medium">MW</span>
          </div>
          <div className="min-w-0">
            <h1 className="text-[13px] font-semibold text-zinc-100 tracking-tight">MinerWatch</h1>
            <p className="text-[10px] text-zinc-500 truncate">
              SN{subnet} · {profile.name} · {subtitle}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 flex-wrap justify-end">
          <MarketTicker />
          <DashboardTabs />
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/5 text-emerald-400 text-[10px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            live
          </span>
        </div>
      </div>
    </header>
  );
}
