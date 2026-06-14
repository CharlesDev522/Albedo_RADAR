import { api, DEFAULT_SUBNET, shortAddr, shortHash, shortRepo } from "@/lib/api";

export const dynamic = "force-dynamic";

async function safe<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await fn();
  } catch {
    return fallback;
  }
}

function fmtBlock(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default async function Dashboard() {
  const subnet = DEFAULT_SUBNET;

  const [stats, commits, registry] = await Promise.all([
    safe(() => api.getStats(subnet), {
      subnet,
      total_neurons: 0,
      committed_miners: 0,
      uncommitted_miners: 0,
      coverage_pct: 0,
      latest_commit_block: null,
      last_scan_at: new Date().toISOString(),
    }),
    safe(() => api.getCommitments(subnet), { commitments: [], total: 0 }),
    safe(() => api.getRegistry(subnet), {
      subnet,
      miners: [],
      total: 0,
      v5_count: 0,
      uncommitted_count: 0,
    }),
  ]);

  const v5Miners = registry.miners.filter((m) => m.has_v5);
  const waiting = registry.miners.filter((m) => !m.has_v5);
  const synced = stats.total_neurons > 0 || commits.total > 0;

  return (
    <div className="space-y-3">
      {!synced && (
        <div className="panel px-3 py-2 border-amber-500/20 bg-amber-500/5 text-[11px] text-amber-300">
          Collector syncing — ensure <code className="mono text-amber-100">docker compose logs collector</code> shows no errors.
        </div>
      )}

      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        <Kpi label="miners" value={String(stats.total_neurons)} />
        <Kpi label="v5 committed" value={String(stats.committed_miners)} accent />
        <Kpi label="no v5" value={String(stats.uncommitted_miners)} warn={stats.uncommitted_miners > 0} />
        <Kpi label="coverage" value={`${stats.coverage_pct}%`} />
        <Kpi label="latest block" value={fmtBlock(stats.latest_commit_block)} mono />
        <Kpi label="last scan" value={fmtTime(stats.last_scan_at)} small />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        {/* v5 commits table */}
        <section className="panel xl:col-span-8">
          <div className="panel-head">
            <div>
              <h2 className="text-[12px] font-semibold text-zinc-100">v5 commits</h2>
              <p className="text-[10px] text-zinc-500 mt-0.5">active + revealed · format v5|repo|sha256:digest</p>
            </div>
            <span className="pill-v5">{commits.total} on-chain</span>
          </div>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead>
                <tr>
                  <th>uid</th>
                  <th>hotkey</th>
                  <th>coldkey</th>
                  <th>reg</th>
                  <th>commit</th>
                  <th>src</th>
                  <th>model</th>
                  <th>hash</th>
                </tr>
              </thead>
              <tbody>
                {commits.commitments.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center text-zinc-500 py-8 text-[11px]">
                      no v5 commits indexed yet — scanner reads CommitmentOf + RevealedCommitments
                    </td>
                  </tr>
                ) : (
                  commits.commitments.map((c) => (
                    <tr key={c.id}>
                      <td className="mono font-medium text-zinc-200">{c.uid ?? "—"}</td>
                      <td className="mono text-emerald-400/90" title={c.hotkey}>
                        {shortAddr(c.hotkey, 6)}
                      </td>
                      <td className="mono text-zinc-500" title={c.coldkey ?? ""}>
                        {c.coldkey ? shortAddr(c.coldkey, 4) : "—"}
                      </td>
                      <td className="mono text-zinc-500 tabular-nums">{fmtBlock(c.registered_at_block)}</td>
                      <td className="mono text-zinc-300 tabular-nums">{fmtBlock(c.commit_block)}</td>
                      <td>
                        <span className={c.commit_source === "revealed" ? "pill-v5" : "pill-active"}>
                          {c.commit_source}
                        </span>
                      </td>
                      <td className="max-w-[180px]">
                        <a
                          href={`https://huggingface.co/${c.repo}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sky-400/90 hover:text-sky-300 hover:underline truncate block"
                          title={c.repo}
                        >
                          {shortRepo(c.repo)}
                        </a>
                      </td>
                      <td className="mono text-[10px] text-zinc-500" title={c.digest}>
                        {shortHash(c.digest)}…
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* side: v5 miners compact */}
        <aside className="xl:col-span-4 space-y-3">
          <section className="panel">
            <div className="panel-head">
              <h2 className="text-[12px] font-semibold text-zinc-100">v5 miners</h2>
              <span className="text-[10px] text-zinc-500">{v5Miners.length}</span>
            </div>
            <div className="max-h-[280px] overflow-y-auto divide-y divide-zinc-800/50">
              {v5Miners.length === 0 ? (
                <p className="px-3 py-4 text-[10px] text-zinc-500">none yet</p>
              ) : (
                v5Miners.map((m) => (
                  <div key={m.uid} className="px-3 py-2 hover:bg-zinc-800/20">
                    <div className="flex items-center justify-between gap-2">
                      <span className="mono text-[11px] text-zinc-200">
                        uid <span className="text-emerald-400">{m.uid}</span>
                      </span>
                      <span className="text-[10px] text-zinc-500 mono">blk {fmtBlock(m.commit_block)}</span>
                    </div>
                    <p className="mono text-[10px] text-zinc-500 mt-0.5" title={m.hotkey}>
                      {shortAddr(m.hotkey, 8)}
                    </p>
                    {m.repo && (
                      <p className="text-[10px] text-zinc-600 mt-0.5 truncate" title={m.repo}>
                        {shortRepo(m.repo, 32)}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </section>

          {waiting.length > 0 && (
            <section className="panel border-amber-500/15">
              <div className="panel-head">
                <h2 className="text-[12px] font-semibold text-amber-400/90">awaiting v5</h2>
                <span className="text-[10px] text-zinc-500">{waiting.length}</span>
              </div>
              <div className="px-3 py-2 flex flex-wrap gap-1 max-h-24 overflow-y-auto">
                {waiting.slice(0, 80).map((m) => (
                  <span key={m.uid} className="pill-none mono">
                    {m.uid}
                  </span>
                ))}
                {waiting.length > 80 && (
                  <span className="text-[10px] text-zinc-600">+{waiting.length - 80}</span>
                )}
              </div>
            </section>
          )}
        </aside>
      </div>

      {/* full registry */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2 className="text-[12px] font-semibold text-zinc-100">miner registry</h2>
            <p className="text-[10px] text-zinc-500">all active miners · commitment status</p>
          </div>
          <span className="text-[10px] text-zinc-500">{registry.total} neurons</span>
        </div>
        <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
          <table className="tbl">
            <thead className="sticky top-0 z-10">
              <tr>
                <th>uid</th>
                <th>status</th>
                <th>hotkey</th>
                <th>coldkey</th>
                <th>registered</th>
                <th>commit blk</th>
                <th>model</th>
              </tr>
            </thead>
            <tbody>
              {registry.miners.map((m) => (
                <tr key={m.uid} className={m.has_v5 ? "" : "opacity-60"}>
                  <td className="mono text-zinc-200">{m.uid}</td>
                  <td>
                    {m.has_v5 ? (
                      <span className="pill-v5">v5</span>
                    ) : (
                      <span className="pill-none">—</span>
                    )}
                  </td>
                  <td className="mono text-zinc-400" title={m.hotkey}>
                    {shortAddr(m.hotkey, 6)}
                  </td>
                  <td className="mono text-zinc-500" title={m.coldkey}>
                    {shortAddr(m.coldkey, 4)}
                  </td>
                  <td className="mono text-zinc-500 tabular-nums">{fmtBlock(m.registered_at_block)}</td>
                  <td className="mono text-zinc-400 tabular-nums">{fmtBlock(m.commit_block)}</td>
                  <td className="text-[10px] text-zinc-500 truncate max-w-[200px]" title={m.repo ?? ""}>
                    {m.repo ? shortRepo(m.repo) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Kpi({
  label,
  value,
  accent,
  warn,
  mono: isMono,
  small,
}: {
  label: string;
  value: string;
  accent?: boolean;
  warn?: boolean;
  mono?: boolean;
  small?: boolean;
}) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p
        className={`${small ? "text-[11px] font-normal text-zinc-400" : "stat-value"} ${
          isMono ? "mono" : ""
        } ${accent ? "text-emerald-400" : ""} ${warn ? "text-amber-400" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}
