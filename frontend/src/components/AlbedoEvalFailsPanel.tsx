"use client";

import { useMemo, useState } from "react";
import { EntityNameCell } from "@/lib/entityLabels";
import { hippiusModelUrl, shortAddr, type AlbedoEvalFail, type AlbedoEvalQueueOverview } from "@/lib/api";

type FaultFilter = "all" | "MINER_FAULT" | "INFRA_FAULT";

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function faultBadge(faultClass: string | null | undefined): string {
  if (faultClass === "MINER_FAULT") {
    return "text-amber-200 border-amber-500/40 bg-amber-500/10";
  }
  if (faultClass === "INFRA_FAULT") {
    return "text-violet-200 border-violet-500/40 bg-violet-500/10";
  }
  return "text-zinc-400 border-zinc-700 bg-zinc-800/50";
}

function FailRow({ row }: { row: AlbedoEvalFail }) {
  const url = row.model_uri ? hippiusModelUrl(row.model_uri.split("@")[0]) : null;

  return (
    <tr className="border-b border-zinc-800/50 hover:bg-zinc-800/20 align-top">
      <td className="py-1.5 pr-2 text-zinc-500 whitespace-nowrap">{fmtTime(row.updated_at)}</td>
      <td className="py-1.5 pr-2">
        {url ? (
          <a href={url} target="_blank" rel="noreferrer" className="text-sky-300 hover:underline block truncate max-w-[180px]">
            <EntityNameCell repo={row.repo ?? undefined} coldkey={row.coldkey} />
          </a>
        ) : (
          <span className="block truncate max-w-[180px]">
            <EntityNameCell repo={row.repo ?? undefined} coldkey={row.coldkey} />
          </span>
        )}
        <span className="text-[9px] text-zinc-600">uid {row.uid ?? "—"}</span>
      </td>
      <td className="py-1.5 pr-2 mono text-zinc-500">{shortAddr(row.hotkey ?? "", 4)}</td>
      <td className="py-1.5 pr-2">
        <span className={`inline-block px-1.5 py-0.5 rounded text-[9px] border ${faultBadge(row.fault_class)}`}>
          {row.fault_class?.replace("_", " ") ?? "unknown"}
        </span>
        {row.fault_code && (
          <span className="block text-[9px] mono text-zinc-600 mt-0.5">{row.fault_code}</span>
        )}
      </td>
      <td className="py-1.5 pr-2 text-zinc-500">{row.state ?? "—"}</td>
      <td className="py-1.5 text-zinc-400 max-w-[220px]">
        <p className="truncate" title={row.fault_message ?? undefined}>
          {row.fault_message ?? "—"}
        </p>
        {row.submission_id && (
          <p className="text-[8px] mono text-zinc-600 mt-0.5 truncate" title={row.submission_id}>
            {row.submission_id}
          </p>
        )}
      </td>
    </tr>
  );
}

export default function AlbedoEvalFailsPanel({ data }: { data: AlbedoEvalQueueOverview }) {
  const [filter, setFilter] = useState<FaultFilter>("all");

  const filtered = useMemo(() => {
    if (filter === "all") return data.fails;
    return data.fails.filter((r) => r.fault_class === filter);
  }, [data.fails, filter]);

  const counts = data.fail_counts_by_class ?? {};

  return (
    <section className="panel px-3 py-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2 mb-3">
        <div>
          <h3 className="text-[11px] font-semibold text-zinc-200">Disqualifications & failures</h3>
          <p className="text-[9px] text-zinc-600 mt-0.5">
            Terminal invalid states from Hippius dashboard · updated {fmtTime(data.updated_at)}
          </p>
        </div>
        <div className="inline-flex rounded-md border border-zinc-800 bg-zinc-900/60 p-0.5">
          {(
            [
              { id: "all" as const, label: `All (${data.fail_count})` },
              { id: "MINER_FAULT" as const, label: `Miner (${counts.MINER_FAULT ?? 0})` },
              { id: "INFRA_FAULT" as const, label: `Infra (${counts.INFRA_FAULT ?? 0})` },
            ] as const
          ).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setFilter(tab.id)}
              className={`px-2 py-1 rounded text-[10px] font-medium border transition-colors ${
                filter === tab.id
                  ? "border-rose-500/40 bg-rose-500/15 text-rose-200"
                  : "border-transparent text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="text-[10px] text-zinc-500">
          {data.fail_count === 0 ? "No recent DQ events." : "No rows match this filter."}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[10px] min-w-[720px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-1 pr-2">When</th>
                <th className="text-left py-1 pr-2">Miner</th>
                <th className="text-left py-1 pr-2">Hotkey</th>
                <th className="text-left py-1 pr-2">Fault</th>
                <th className="text-left py-1 pr-2">State</th>
                <th className="text-left py-1">Message</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <FailRow key={row.submission_id ?? `${row.uid}-${row.updated_at}`} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
