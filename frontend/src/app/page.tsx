import { Suspense } from "react";
import LiveDashboard from "@/components/LiveDashboard";
import AlbedoKingPanel from "@/components/AlbedoKingPanel";
import AlbedoAnalyticsPanel from "@/components/AlbedoAnalyticsPanel";
import MinerGroupsPanel from "@/components/MinerGroupsPanel";
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
import { getSubnetProfile } from "@/lib/subnets";

export const dynamic = "force-dynamic";

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

function parseSubnet(raw: string | undefined): number {
  if (!raw) return DEFAULT_SUBNET;
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n < 0 || n > 65535) return DEFAULT_SUBNET;
  return n;
}

export default async function Page({
  searchParams,
}: {
  searchParams?: Promise<{ subnet?: string }>;
}) {
  const params = (await searchParams) ?? {};
  const subnet = parseSubnet(params.subnet);
  const profile = getSubnetProfile(subnet);

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
      <div className="space-y-3">
        {profile.features.albedoKing && (
          <>
            <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading albedo…</div>}>
              <AlbedoKingPanel />
            </Suspense>
            <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading analytics…</div>}>
              <AlbedoAnalyticsPanel />
            </Suspense>
          </>
        )}
        <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading slots…</div>}>
          <SlotStatusBoard />
        </Suspense>
        <Suspense fallback={null}>
          <LiveDashboard />
        </Suspense>
        <Suspense fallback={<div className="panel p-4 text-[10px] text-zinc-500">loading clusters…</div>}>
          <MinerGroupsPanel />
        </Suspense>
      </div>
    </DashboardSyncProvider>
  );
}
