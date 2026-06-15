"use client";

import SubnetSelector from "@/components/SubnetSelector";
import { useSubnet } from "@/lib/useSubnet";

export default function HeaderBar() {
  const { subnet } = useSubnet();

  return (
    <header className="border-b border-zinc-800/80 bg-zinc-950/90 backdrop-blur sticky top-0 z-50">
      <div className="max-w-[1400px] mx-auto px-3 py-2 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-6 h-6 rounded-md bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center shrink-0">
            <span className="text-emerald-400 font-mono text-[10px] font-medium">MW</span>
          </div>
          <div className="min-w-0">
            <h1 className="text-[13px] font-semibold text-zinc-100 tracking-tight">MinerWatch</h1>
            <p className="text-[10px] text-zinc-500 truncate">SN{subnet} · v5/v6 commitments</p>
          </div>
        </div>
        <div className="flex items-center gap-3 text-[10px] text-zinc-500 shrink-0">
          <SubnetSelector />
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border border-emerald-500/20 bg-emerald-500/5 text-emerald-400">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            live
          </span>
        </div>
      </div>
    </header>
  );
}
