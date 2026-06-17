"use client";

import { DASHBOARD_SUBNETS, getSubnetProfile } from "@/lib/subnets";
import { useSubnet } from "@/lib/useSubnet";

const ACCENT_ACTIVE: Record<string, string> = {
  amber: "border-amber-500/50 bg-amber-500/15 text-amber-200",
  violet: "border-violet-500/50 bg-violet-500/15 text-violet-200",
  emerald: "border-emerald-500/50 bg-emerald-500/15 text-emerald-200",
};

const ACCENT_IDLE: Record<string, string> = {
  amber: "border-zinc-800 text-zinc-500 hover:border-amber-500/30 hover:text-amber-300/80",
  violet: "border-zinc-800 text-zinc-500 hover:border-violet-500/30 hover:text-violet-300/80",
  emerald: "border-zinc-800 text-zinc-500 hover:border-emerald-500/30 hover:text-emerald-300/80",
};

export default function SubnetTabs() {
  const { subnet, setSubnet, otherPresets } = useSubnet();
  const isOther = !DASHBOARD_SUBNETS.includes(subnet as (typeof DASHBOARD_SUBNETS)[number]);

  return (
    <div className="flex items-center gap-1.5 flex-wrap justify-end">
      <div
        className="inline-flex rounded-md border border-zinc-800 bg-zinc-900/60 p-0.5"
        role="tablist"
        aria-label="Subnet"
      >
        {DASHBOARD_SUBNETS.map((n) => {
          const p = getSubnetProfile(n);
          const active = subnet === n;
          const accent = p.accent;
          return (
            <button
              key={n}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setSubnet(n)}
              className={`px-2.5 py-1 rounded text-[10px] font-medium border transition-colors ${
                active ? ACCENT_ACTIVE[accent] : ACCENT_IDLE[accent]
              }`}
            >
              <span className="mono">SN{n}</span>
              <span className="ml-1 opacity-80">{p.shortName}</span>
            </button>
          );
        })}
      </div>

      <label className="inline-flex items-center gap-1 text-[10px] text-zinc-600">
        <select
          value={isOther ? subnet : ""}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (v) setSubnet(v);
          }}
          className="text-[10px] bg-zinc-900 border border-zinc-800 rounded px-1 py-0.5 text-zinc-400 mono"
          aria-label="Other subnets"
        >
          <option value="" disabled={!isOther}>
            {isOther ? `SN${subnet}` : "more…"}
          </option>
          {otherPresets.map((n) => (
            <option key={n} value={n}>
              SN{n}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
