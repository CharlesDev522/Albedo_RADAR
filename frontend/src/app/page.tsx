import { Suspense } from "react";
import AlbedoDuelPanel from "@/components/AlbedoDuelPanel";
import LiveDashboard from "@/components/LiveDashboard";
import ChampionRewardPanel from "@/components/ChampionRewardPanel";
import MinerGroupsPanel from "@/components/MinerGroupsPanel";
import RepoActivityPanel from "@/components/RepoActivityPanel";
import SlotStatusBoard from "@/components/SlotStatusBoard";
import { DashboardSyncProvider } from "@/lib/DashboardSyncContext";
import {
  api,
  DEFAULT_SUBNET,
  type Commitment,
  type CommitmentStats,
  type Registry,
  type SlotStatusData,
} from "@/lib/api";
import type { DashboardView } from "@/lib/subnets";

export const dynamic = "force-dynamic";

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

function parseView(raw: string | undefined): DashboardView {
  if (raw === "clusters") return "clusters";
  if (raw === "activity") return "activity";
  if (raw === "duels") return "duels";
  return "dashboard";
}

export default async function Page({
  searchParams,
}: {
  searchParams?: Promise<{ view?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const view = parseView(params.view);
  const subnet = DEFAULT_SUBNET;

  const [stats, commits, registry, slotData, syncStatus] = await Promise.all([
    safe(() => api.getStats(subnet), null),
    safe(() => api.getCommitments(subnet), { commitments: [] as Commitment[], total: 0 }),
    safe(() => api.getRegistry(subnet), null),
    safe(() => api.getSlotStatus(subnet, "all", "uid_asc", false), null as SlotStatusData | null),
    safe(() => api.getSyncStatus(subnet, false), null),
  ]);

  return (
    <DashboardSyncProvider
      key={subnet}
      initialStats={stats}
      initialCommits={commits.commitments}
      initialRegistry={registry}
      initialSlotData={slotData}
      initialSyncStatus={syncStatus}
    >
      <div className="space-y-3" key={`dashboard-${view}`}>
        {view === "clusters" ? (
          <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading clusters…</div>}>
            <MinerGroupsPanel />
          </Suspense>
        ) : view === "activity" ? (
          <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading repo activity…</div>}>
            <RepoActivityPanel />
          </Suspense>
        ) : view === "duels" ? (
          <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading duel analysis…</div>}>
            <AlbedoDuelPanel />
          </Suspense>
        ) : (
          <>
            <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading champion reward…</div>}>
              <ChampionRewardPanel />
            </Suspense>
            <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading slots…</div>}>
              <SlotStatusBoard />
            </Suspense>
            <Suspense fallback={null}>
              <LiveDashboard />
            </Suspense>
          </>
        )}
      </div>
    </DashboardSyncProvider>
  );
}
