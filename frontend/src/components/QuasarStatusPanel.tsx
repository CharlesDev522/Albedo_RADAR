"use client";

import { shortAddr, shortRepo } from "@/lib/api";
import { useDashboardSync } from "@/lib/DashboardSyncContext";
import { useSubnet } from "@/lib/useSubnet";

const QUASAR_DASHBOARD = "https://sn24.quasarcopilot.com";

function fmtTime(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function hfModelUrl(repo: string, revision?: string | null) {
  const clean = repo.replace(/^\/+|\/+$/g, "");
  if (revision) return `https://huggingface.co/${clean}/tree/${revision}`;
  return `https://huggingface.co/${clean}`;
}

export default function QuasarStatusPanel() {
  const { subnet } = useSubnet();
  const { quasarStatus } = useDashboardSync();
  const king = quasarStatus?.king;
  const phase = quasarStatus?.eval_phase;
  const chainKing = quasarStatus?.consensus_king;
  const counts = quasarStatus?.submission_counts ?? {};
  const totalSubs = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2 className="text-[12px] font-semibold text-zinc-100">Quasar status · SN{subnet}</h2>
          <p className="text-[10px] text-zinc-500">
            Validator eval state ·{" "}
            <a
              href={QUASAR_DASHBOARD}
              target="_blank"
              rel="noopener noreferrer"
              className="text-violet-400/90 hover:underline"
            >
              official dashboard
            </a>
          </p>
        </div>
        {phase?.label && <span className="pill-violet text-[9px]">{phase.label}</span>}
      </div>

      <div className="p-3 grid grid-cols-1 lg:grid-cols-12 gap-3">
        <div className="lg:col-span-5 border border-violet-500/15 rounded-lg bg-violet-500/5 p-3">
          <p className="text-[10px] uppercase tracking-widest text-violet-400/80 mb-2">eval king</p>
          {king ? (
            <>
              <p className="text-[16px] font-semibold text-violet-100">
                uid {king.uid ?? "—"}
                {king.reign_number != null && (
                  <span className="text-[11px] font-normal text-zinc-500 ml-2">
                    reign #{king.reign_number}
                  </span>
                )}
              </p>
              {king.hf_repo && (
                <a
                  href={hfModelUrl(king.hf_repo, king.king_revision)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-sky-400/90 hover:underline block mt-1 truncate"
                >
                  {shortRepo(king.hf_repo)}
                </a>
              )}
              {king.king_revision && (
                <p className="mono text-[10px] text-zinc-500 mt-1 truncate" title={king.king_revision}>
                  rev {king.king_revision.slice(0, 12)}…
                </p>
              )}
              {king.crowned_at && (
                <p className="text-[10px] text-zinc-600 mt-2">crowned {fmtTime(king.crowned_at)}</p>
              )}
            </>
          ) : (
            <p className="text-[10px] text-zinc-500">Loading from Quasar API…</p>
          )}
        </div>

        <div className="lg:col-span-7 grid grid-cols-2 sm:grid-cols-3 gap-2">
          <MiniStat
            label="state king uid"
            value={String(phase?.state_king_uid ?? quasarStatus?.state_king_uid ?? "—")}
            accent
          />
          <MiniStat label="chain king uid" value={String(phase?.chain_king_uid ?? chainKing?.uid ?? "—")} />
          <MiniStat
            label="weight reveal"
            value={phase?.weight_reveal_pending ? "pending" : "synced"}
            warn={!!phase?.weight_reveal_pending}
          />
          <MiniStat label="phase" value={phase?.phase ?? "—"} />
          <MiniStat label="queue" value={String(quasarStatus?.queue_len ?? 0)} />
          <MiniStat label="submissions" value={String(totalSubs || "—")} />
          <MiniStat label="valid" value={String(counts.valid ?? counts.king ?? "—")} accent />
          <MiniStat label="disqualified" value={String(counts.disqualified ?? "—")} warn={(counts.disqualified ?? 0) > 0} />
          <MiniStat label="current eval" value={quasarStatus?.current_eval ?? "—"} small />
        </div>
      </div>

      {phase?.detail && (
        <div className="px-3 pb-3 text-[10px] text-zinc-500 border-t border-zinc-800/50 pt-2 mx-3">
          {phase.detail}
        </div>
      )}

      {quasarStatus?.policy && (
        <div className="px-3 pb-3 text-[10px] text-zinc-600 flex flex-wrap gap-3">
          {quasarStatus.policy.max_kl_threshold != null && (
            <span>max KL {String(quasarStatus.policy.max_kl_threshold)}</span>
          )}
          {quasarStatus.policy.crown_quality_floor != null && (
            <span>crown quality floor {String(quasarStatus.policy.crown_quality_floor)}</span>
          )}
        </div>
      )}
    </section>
  );
}

function MiniStat({
  label,
  value,
  accent,
  warn,
  small,
}: {
  label: string;
  value: string;
  accent?: boolean;
  warn?: boolean;
  small?: boolean;
}) {
  return (
    <div className="stat">
      <p className="stat-label">{label}</p>
      <p
        className={`${small ? "text-[10px] font-normal text-zinc-500" : "stat-value"} ${
          accent ? "text-violet-400" : ""
        } ${warn ? "text-amber-400" : ""}`}
      >
        {value}
      </p>
    </div>
  );
}
