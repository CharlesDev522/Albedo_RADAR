"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api,
  DEFAULT_SUBNET,
  shortAddr,
  shortHash,
  type EncryptedCommitment,
  type EncryptedCommitmentStats,
} from "@/lib/api";

const POLL_MS = 5000;

export default function EncryptedCommitsPanel() {
  const subnet = DEFAULT_SUBNET;
  const [stats, setStats] = useState<EncryptedCommitmentStats | null>(null);
  const [commits, setCommits] = useState<EncryptedCommitment[]>([]);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        api.getEncryptedStats(subnet),
        api.getEncryptedCommitments(subnet),
      ]);
      setStats(s);
      setCommits(c.commitments);
      setLastRefresh(new Date());
    } catch {
      /* panel is supplementary — fail silently */
    }
  }, [subnet]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">encrypted commits</h2>
          <p className="text-[10px] text-zinc-500 mt-0.5">
            TimelockEncrypted on chain — pending reveal (not readable as v5 yet)
          </p>
        </div>
        <span className="pill-v5 bg-violet-500/10 border-violet-500/30 text-violet-300">
          {stats?.pending_encrypted ?? commits.length} pending
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 px-3 py-2 border-b border-zinc-800/80">
        <MiniStat label="pending" value={String(stats?.pending_encrypted ?? "—")} accent />
        <MiniStat label="revealed (hist)" value={String(stats?.revealed_total ?? "—")} />
        <MiniStat label="commit blk" value={fmt(stats?.latest_commit_block)} mono />
        <MiniStat label="reveal round" value={fmt(stats?.latest_reveal_round)} mono />
      </div>

      <div className="overflow-x-auto">
        <table className="tbl">
          <thead>
            <tr>
              <th>uid</th>
              <th>hotkey</th>
              <th>commit blk</th>
              <th>reveal round</th>
              <th>deposit</th>
              <th>cipher hash</th>
              <th>status</th>
            </tr>
          </thead>
          <tbody>
            {commits.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center text-zinc-500 py-6 text-[10px]">
                  no TimelockEncrypted miners on subnet {subnet} right now
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
                      {c.status}
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
          refreshed {Math.round((Date.now() - lastRefresh.getTime()) / 1000)}s ago · when revealed, moves to v5 table above
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
