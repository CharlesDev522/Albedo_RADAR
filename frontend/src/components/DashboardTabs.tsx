"use client";

import { DASHBOARD_TABS } from "@/lib/subnets";
import { useSubnet } from "@/lib/useSubnet";

export default function DashboardTabs() {
  const { view, setView } = useSubnet();

  return (
    <div
      className="inline-flex rounded-md border border-zinc-800 bg-zinc-900/60 p-0.5"
      role="tablist"
      aria-label="Dashboard"
    >
      {DASHBOARD_TABS.map((tab) => {
        const active = view === tab.view;
        return (
          <button
            key={tab.view}
            type="button"
            role="tab"
            aria-selected={active}
            title={tab.hint}
            onClick={() => setView(tab.view)}
            className={`px-2.5 py-1 rounded text-[10px] font-medium border transition-colors ${
              active
                ? tab.view === "clusters"
                  ? "border-violet-500/50 bg-violet-500/15 text-violet-200"
                  : "border-amber-500/50 bg-amber-500/15 text-amber-200"
                : "border-transparent text-zinc-500 hover:border-zinc-700 hover:text-zinc-300"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
