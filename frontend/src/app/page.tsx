import { api, DEFAULT_SUBNET, truncateAddress, truncateRepo } from "@/lib/api";

export const dynamic = "force-dynamic";

async function safeFetch<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

export default async function Dashboard() {
  const subnet = DEFAULT_SUBNET;

  const [stats, data, events] = await Promise.all([
    safeFetch(() => api.getCommitmentStats(subnet), {
      subnet,
      total_neurons: 0,
      committed_miners: 0,
      uncommitted_miners: 0,
      coverage_pct: 0,
      latest_commit_block: null,
      last_scan_at: new Date().toISOString(),
    }),
    safeFetch(() => api.getCommitments(subnet), {
      commitments: [],
      total: 0,
      subnet,
      committed_count: 0,
      uncommitted_uids: [],
    }),
    safeFetch(() => api.getCommitmentEvents(subnet), { events: [] }),
  ]);

  const commitmentEvents = events.events.filter(
    (e) => e.event_type === "commitment_revealed" || e.event_type === "commitment_updated"
  );

  const hasData = data.total > 0 || stats.total_neurons > 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Subnet {subnet} — v5 Commitment Tracker</h2>
          <p className="text-sm text-gray-500 mt-1">
            Latest on-chain model commits · format <code className="text-bittensor-accent">v5|repo|sha256:digest</code>
          </p>
        </div>
        <span className="badge-active">v5 only</span>
      </div>

      {!hasData && (
        <div className="card border-bittensor-warning/30 bg-bittensor-warning/5">
          <p className="text-bittensor-warning text-sm">
            Waiting for commitment data. Run <code className="text-white">docker compose up</code> and let the
            collector scan subnet {subnet}.
          </p>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Total Miners" value={stats.total_neurons.toString()} />
        <StatCard label="Committed (v5)" value={stats.committed_miners.toString()} accent />
        <StatCard label="Uncommitted" value={stats.uncommitted_miners.toString()} warn={stats.uncommitted_miners > 0} />
        <StatCard label="Coverage" value={`${stats.coverage_pct}%`} />
        <StatCard
          label="Latest Block"
          value={stats.latest_commit_block?.toLocaleString() ?? "—"}
          sub={stats.last_scan_at ? `scanned ${new Date(stats.last_scan_at).toLocaleTimeString()}` : ""}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Main commitment table */}
        <div className="lg:col-span-3 card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Latest v5 Commits</h2>
            <span className="text-sm text-gray-500">{data.total} miners</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b border-bittensor-border">
                  <th className="text-left py-2 pr-3">UID</th>
                  <th className="text-left py-2 pr-3">Hotkey</th>
                  <th className="text-left py-2 pr-3">Coldkey</th>
                  <th className="text-left py-2 pr-3">Reg Block</th>
                  <th className="text-left py-2 pr-3">Commit Block</th>
                  <th className="text-left py-2 pr-3">Model Repo</th>
                  <th className="text-left py-2">Digest</th>
                </tr>
              </thead>
              <tbody>
                {data.commitments.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-10 text-center text-gray-500">
                      No v5 commitments indexed yet
                    </td>
                  </tr>
                ) : (
                  data.commitments.map((c) => (
                    <tr key={c.id} className="border-b border-bittensor-border/40 hover:bg-white/5">
                      <td className="py-2.5 pr-3 font-mono font-medium">{c.uid ?? "—"}</td>
                      <td className="py-2.5 pr-3 font-mono text-bittensor-accent" title={c.hotkey}>
                        {truncateAddress(c.hotkey, 8)}
                      </td>
                      <td className="py-2.5 pr-3 font-mono text-gray-400" title={c.coldkey ?? ""}>
                        {c.coldkey ? truncateAddress(c.coldkey, 6) : "—"}
                      </td>
                      <td className="py-2.5 pr-3 text-gray-400">
                        {c.registered_at_block?.toLocaleString() ?? "—"}
                      </td>
                      <td className="py-2.5 pr-3 font-mono">{c.commit_block.toLocaleString()}</td>
                      <td className="py-2.5 pr-3 max-w-[200px] truncate" title={c.repo}>
                        <a
                          href={`https://huggingface.co/${c.repo}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:underline"
                        >
                          {truncateRepo(c.repo)}
                        </a>
                      </td>
                      <td className="py-2.5 font-mono text-xs text-gray-500" title={c.digest}>
                        {c.digest.replace("sha256:", "").slice(0, 12)}…
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Side panel */}
        <div className="space-y-4">
          {/* Recent commitment events */}
          <div className="card">
            <h2 className="text-lg font-semibold mb-3">Recent Commits</h2>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {commitmentEvents.length === 0 ? (
                <p className="text-gray-500 text-sm">No commit events yet</p>
              ) : (
                commitmentEvents.slice(0, 15).map((e) => (
                  <div key={e.id} className="border-b border-bittensor-border/40 pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="badge-event text-xs">{e.event_type.replace("commitment_", "")}</span>
                      <span className="text-xs text-gray-500">
                        {new Date(e.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <p className="text-xs mt-1 text-gray-400 font-mono">
                      UID {String(e.data.uid ?? "?")} · block {String(e.data.commit_block ?? e.block ?? "?")}
                    </p>
                    {"model_uri" in e.data && e.data.model_uri != null && (
                      <p className="text-xs mt-0.5 text-gray-500 truncate" title={String(e.data.model_uri)}>
                        {truncateRepo(String(e.data.model_uri), 30)}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Uncommitted UIDs */}
          {data.uncommitted_uids.length > 0 && (
            <div className="card border-bittensor-warning/20">
              <h2 className="text-sm font-semibold text-bittensor-warning mb-2">
                Uncommitted ({data.uncommitted_uids.length})
              </h2>
              <p className="text-xs text-gray-500 mb-2">Registered miners without a v5 commit</p>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                {data.uncommitted_uids.map((uid) => (
                  <span key={uid} className="badge bg-yellow-900/30 text-yellow-500 font-mono">
                    {uid}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
  warn,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
  warn?: boolean;
}) {
  return (
    <div className="card">
      <p className="text-sm text-gray-500">{label}</p>
      <p
        className={`text-2xl font-bold mt-1 ${
          accent ? "text-bittensor-accent" : warn ? "text-bittensor-warning" : ""
        }`}
      >
        {value}
      </p>
      {sub && <p className="text-xs text-gray-600 mt-1">{sub}</p>}
    </div>
  );
}
