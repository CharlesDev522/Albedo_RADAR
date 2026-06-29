import { DashboardSyncProvider } from "@/lib/DashboardSyncContext";
import DashboardShell from "@/components/DashboardShell";
import {
  api,
  DEFAULT_SUBNET,
  type Commitment,
  type CommitmentStats,
  type Registry,
  type SlotStatusData,
} from "@/lib/api";

export const dynamic = "force-dynamic";

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

export default async function Page() {
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
      <DashboardShell />
    </DashboardSyncProvider>
  );
}
