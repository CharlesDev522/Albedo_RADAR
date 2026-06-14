import { api, formatNumber, truncateAddress } from "@/lib/api";

export const dynamic = "force-dynamic";

async function safeFetch<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

export default async function Dashboard() {
  const subnet = 1;

  const [stats, miners, topEmission, topStake, events, clusters] = await Promise.all([
    safeFetch(() => api.getSubnetStats(subnet), {
      subnet,
      block: 0,
      neuron_count: 0,
      active_miners: 0,
      active_validators: 0,
      total_stake: 0,
      total_emission: 0,
      last_updated: new Date().toISOString(),
    }),
    safeFetch(() => api.getMiners(subnet), { miners: [], total: 0 }),
    safeFetch(() => api.getLeaderboard("emission", subnet), { category: "emission", subnet, entries: [], updated_at: "" }),
    safeFetch(() => api.getLeaderboard("stake", subnet), { category: "stake", subnet, entries: [], updated_at: "" }),
    safeFetch(() => api.getEvents(subnet), { events: [] }),
    safeFetch(() => api.getClusters(subnet), []),
  ]);

  const apiConnected = stats.neuron_count > 0 || miners.total > 0;

  return (
    <div className="space-y-6">
      {!apiConnected && (
        <div className="card border-bittensor-warning/30 bg-bittensor-warning/5">
          <p className="text-bittensor-warning text-sm">
            Waiting for collector data. Start the stack with <code className="text-white">docker compose up</code> and
            allow the metagraph poller to sync.
          </p>
        </div>
      )}

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Neurons" value={stats.neuron_count.toString()} sub={`Block ${stats.block.toLocaleString()}`} />
        <StatCard label="Miners" value={stats.active_miners.toString()} sub={`${stats.active_validators} validators`} />
        <StatCard label="Total Stake" value={formatNumber(stats.total_stake, 2)} sub="TAO equivalent" />
        <StatCard label="Total Emission" value={formatNumber(stats.total_emission, 6)} sub="Current epoch" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Miner Registry */}
        <div className="lg:col-span-2 card">
          <h2 className="text-lg font-semibold mb-4">Miner Registry</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-bittensor-border">
                  <th className="text-left py-2 pr-4">Rank</th>
                  <th className="text-left py-2 pr-4">UID</th>
                  <th className="text-left py-2 pr-4">Hotkey</th>
                  <th className="text-right py-2 pr-4">Stake</th>
                  <th className="text-right py-2">Emission</th>
                </tr>
              </thead>
              <tbody>
                {miners.miners.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-gray-500">
                      No miners indexed yet
                    </td>
                  </tr>
                ) : (
                  miners.miners.slice(0, 15).map((m) => (
                    <tr key={m.id} className="border-b border-bittensor-border/50 hover:bg-white/5">
                      <td className="py-2 pr-4 text-gray-400">#{m.rank_position ?? "—"}</td>
                      <td className="py-2 pr-4 font-mono">{m.uid}</td>
                      <td className="py-2 pr-4 font-mono text-bittensor-accent">{truncateAddress(m.hotkey)}</td>
                      <td className="py-2 pr-4 text-right">{formatNumber(m.current_stake, 2)}</td>
                      <td className="py-2 text-right">{formatNumber(m.current_emission, 6)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Event Feed */}
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Live Events</h2>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {events.events.length === 0 ? (
              <p className="text-gray-500 text-sm">No events yet</p>
            ) : (
              events.events.map((e) => (
                <div key={e.id} className="border-b border-bittensor-border/50 pb-2">
                  <div className="flex items-center justify-between">
                    <span className="badge-event">{e.event_type}</span>
                    <span className="text-xs text-gray-500">{new Date(e.timestamp).toLocaleString()}</span>
                  </div>
                  {e.data.uid !== undefined && (
                    <p className="text-sm mt-1 text-gray-400">UID {String(e.data.uid)}</p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Leaderboards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <LeaderboardCard title="Top Emission" entries={topEmission.entries} />
        <LeaderboardCard title="Top Stake" entries={topStake.entries} />
      </div>

      {/* Wallet Clusters */}
      {clusters.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold mb-4">Wallet Clusters</h2>
          <p className="text-sm text-gray-500 mb-3">Coldkeys operating multiple miners</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {clusters.slice(0, 6).map((c) => (
              <div key={c.coldkey} className="bg-bittensor-dark rounded p-3 border border-bittensor-border">
                <p className="font-mono text-sm text-bittensor-accent">{truncateAddress(c.coldkey, 8)}</p>
                <p className="text-xs text-gray-500 mt-1">{c.miner_count} miners · {formatNumber(c.total_stake, 2)} stake</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card">
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      <p className="text-xs text-gray-600 mt-1">{sub}</p>
    </div>
  );
}

function LeaderboardCard({ title, entries }: { title: string; entries: Array<{ rank: number; uid: number; hotkey: string; value: number }> }) {
  return (
    <div className="card">
      <h2 className="text-lg font-semibold mb-4">{title}</h2>
      {entries.length === 0 ? (
        <p className="text-gray-500 text-sm">No data</p>
      ) : (
        <div className="space-y-2">
          {entries.map((e) => (
            <div key={e.rank} className="flex items-center justify-between py-1">
              <div className="flex items-center gap-3">
                <span className="text-gray-500 w-6">#{e.rank}</span>
                <span className="font-mono text-sm">UID {e.uid}</span>
                <span className="text-xs text-gray-500">{truncateAddress(e.hotkey)}</span>
              </div>
              <span className="font-mono text-bittensor-accent">{formatNumber(e.value, 4)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
