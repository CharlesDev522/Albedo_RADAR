"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { syncDashboardViewFromUrl } from "@/lib/dashboardView";
import { useSubnet } from "@/lib/useSubnet";
import type { DashboardView } from "@/lib/subnets";

const panelFallback = (label: string) => (
  <div className="panel p-4 text-[10px] text-zinc-500">loading {label}…</div>
);

const ChampionRewardPanel = dynamic(() => import("@/components/ChampionRewardPanel"), {
  loading: () => panelFallback("champion reward"),
});
const SlotStatusBoard = dynamic(() => import("@/components/SlotStatusBoard"), {
  loading: () => panelFallback("slots"),
});
const LiveDashboard = dynamic(() => import("@/components/LiveDashboard"), {
  loading: () => null,
});
const MinerGroupsPanel = dynamic(() => import("@/components/MinerGroupsPanel"), {
  loading: () => panelFallback("clusters"),
});
const RepoActivityPanel = dynamic(() => import("@/components/RepoActivityPanel"), {
  loading: () => panelFallback("repo activity"),
});
const AlbedoDuelPanel = dynamic(() => import("@/components/AlbedoDuelPanel"), {
  loading: () => panelFallback("duel analysis"),
});

function PanelSlot({
  active,
  visited,
  viewKey,
  children,
}: {
  active: boolean;
  visited: boolean;
  viewKey: DashboardView;
  children: React.ReactNode;
}) {
  if (!visited) return null;
  return (
    <div
      key={viewKey}
      className={active ? "space-y-3" : "hidden"}
      aria-hidden={!active}
      data-dashboard-view={viewKey}
    >
      {children}
    </div>
  );
}

export default function DashboardShell() {
  const { view } = useSubnet();
  const [mounted, setMounted] = useState(false);
  const [visited, setVisited] = useState<Set<DashboardView>>(() => new Set(["dashboard"]));

  useEffect(() => {
    syncDashboardViewFromUrl();
    setMounted(true);
  }, []);

  useEffect(() => {
    setVisited((prev) => {
      if (prev.has(view)) return prev;
      const next = new Set(prev);
      next.add(view);
      return next;
    });
  }, [view]);

  if (!mounted) {
    return <div className="panel p-4 text-[10px] text-zinc-500">loading dashboard…</div>;
  }

  return (
    <div className="space-y-3">
      <PanelSlot active={view === "clusters"} visited={visited.has("clusters")} viewKey="clusters">
        <MinerGroupsPanel />
      </PanelSlot>

      <PanelSlot active={view === "activity"} visited={visited.has("activity")} viewKey="activity">
        <RepoActivityPanel />
      </PanelSlot>

      <PanelSlot active={view === "duels"} visited={visited.has("duels")} viewKey="duels">
        <AlbedoDuelPanel />
      </PanelSlot>

      <PanelSlot active={view === "dashboard"} visited={visited.has("dashboard")} viewKey="dashboard">
        <ChampionRewardPanel />
        <SlotStatusBoard />
        <LiveDashboard />
      </PanelSlot>
    </div>
  );
}
