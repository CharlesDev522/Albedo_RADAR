"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  DEFAULT_SUBNET,
  shortAddr,
  shortHash,
  type EncryptedCommitment,
  type EncryptedCommitmentStats,
  type EncryptedSyncStatus,
} from "@/lib/api";

const POLL_MS = 5000;

export default function EncryptedCommitsPanel() {
  const subnet = DEFAULT_SUBNET;
  const [stats, setStats] = useState<EncryptedCommitmentStats | null>(null);
  const [sync, setSync] = useState<EncryptedSyncStatus | null>(null);
  const [commits, setCommits] = useState<EncryptedCommitment[]>([]);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, c, syncStatus] = await Promise.all([
        api.getEncryptedStats(subnet),
        api.getEncryptedCommitments(subnet),
        api.getEncryptedSyncStatus(subnet),
      ]);
      setStats(s);
      setCommits(c.commitments);
      setSync(syncStatus);
      setLastRefresh(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "API error");
    }
  }, [subnet]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const onchain = sync?.onchain_encrypted_count ?? null;

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">TimelockEncrypted commits</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            Ciphertext on chain — <strong className="text-zinc-400">not v6 plaintext</strong>, cannot read model/repo until reveal
          </p>
        </div>
        <span className="inline-flex px-2 py-0.5 rounded-full border border-violet-500/30 bg-violet-500/10 text-violet-300 text-[10px]">
          {onchain != null ? `chain ${onchain}` : "…"} · db {stats?.pending_encrypted ?? commits.length}
        </span>
      </div>

      {error && (
        <div className="px-3 py-2 border-b border-rose-500/20 bg-rose-500/5 text-[10px] text-rose-300">
          {error}
        </div>
      )}

      {sync && !sync.in_sync && sync.onchain_encrypted_count > 0 && (
        <div className="px-3 py-2 border-b border-amber-500/20 bg-amber-500/5 text-[10px] text-amber-300">
          Chain has {sync.onchain_encrypted_count} encrypted (uids {sync.onchain_uids.join(", ") || "—"}) but DB has{" "}
          {sync.db_encrypted_count} — restart collector if this persists.
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-3 py-2 border-b border-zinc-800/80">
        <MiniStat label="on-chain" value={String(onchain ?? "—")} accent />
        <MiniStat label="in database" value={String(stats?.pending_encrypted ?? "—")} />
        <MiniStat label="commit blk" value={fmt(stats?.latest_commit_block)} mono />
        <MiniStat label="reveal round" value={fmt(stats?.latest_reveal_round)} mono />
      </div>

      <div className="scroll-pane overflow-x-auto">
        <table className="tbl">
          <thead>
            <tr>
              <th>uid</th>
              <th>hotkey</th>
              <th>commit blk</th>
              <th>reveal round</th>
              <th>deposit</th>
              <th>cipher hash</th>
              <th>kind</th>
            </tr>
          </thead>
          <tbody>
            {commits.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center text-zinc-500 py-6 text-[10px] leading-relaxed">
                  {onchain === 0 ? (
                    <>
                      no TimelockEncrypted miners on subnet {subnet} on chain right now
                      <br />
                      <span className="text-zinc-600">
                        (v6 table above only shows revealed plaintext — encrypted miners appear here after{" "}
                        <code className="mono">set_reveal_commitment</code>)
                      </span>
                    </>
                  ) : (
                    <>collector syncing {onchain} encrypted commit(s) from chain…</>
                  )}
                </td>
              </tr>
            ) : (
              commits.map((c) => (
                <tr key={c.id} className="bg-violet-500/5">
                  <td className="mono font-medium text-zinc-200">{c.uid ?? "—"}</td>
                  <td className="mono text-violet-300/90" title={c.hotkey}>
                    {shortAddr(c.hotkey, 6)}
                  </td>
                  <td className="mono text-zinc-300 tabular-nums">{c.commit_block.toLocaleString()}</td>
                  <td className="mono text-zinc-300 tabular-nums">{c.reveal_round.toLocaleString()}</td>
                  <td className="mono text-zinc-500 tabular-nums">{c.deposit.toLocaleString()}</td>
                  <td className="mono text-[10px] text-zinc-500" title={c.encrypted_hash}>
                    {shortHash(c.encrypted_hash)}…
                  </td>
                  <td>
                    <span className="inline-flex px-1.5 py-0.5 rounded border border-violet-500/30 text-violet-300 text-[9px]">
                      TimelockEncrypted
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {lastRefresh && (
        <div className="px-3 py-2 border-t border-zinc-800/80 text-[10px] text-zinc-600">
          refreshed {Math.round((Date.now() - lastRefresh.getTime()) / 1000)}s ago · after drand reveal, plaintext may appear in v6 table
        </div>
      )}
    </section>
  );
}

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString();
}

function MiniStat({
  label,
  value,
  accent,
  mono,
}: {
  label: string;
  value: string;
  accent?: boolean;
  mono?: boolean;
}) {
  return (
    <div className="stat py-1">
      <p className="stat-label">{label}</p>
      <p className={`stat-value text-[12px] ${mono ? "mono" : ""} ${accent ? "text-violet-300" : ""}`}>
        {value}
      </p>
    </div>
  );
}
