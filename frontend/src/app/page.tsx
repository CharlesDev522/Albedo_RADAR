import LiveDashboard from "@/components/LiveDashboard";
import SlotStatusBoard from "@/components/SlotStatusBoard";
import {
  api,
  DEFAULT_SUBNET,
  type Commitment,
  type CommitmentStats,
  type Registry,
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

  const [stats, commits, registry] = await Promise.all([
    safe(() => api.getStats(subnet), null),
    safe(() => api.getCommitments(subnet), { commitments: [] as Commitment[], total: 0 }),
    safe(() => api.getRegistry(subnet), null),
  ]);

  return (
    <div className="space-y-3">
      <SlotStatusBoard />
      <LiveDashboard
        initialStats={stats}
        initialCommits={commits.commitments}
        initialRegistry={registry}
      />
    </div>
  );
}
