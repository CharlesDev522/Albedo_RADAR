"use client";

import { useSubnet } from "@/lib/useSubnet";

export default function SubnetSelector({ className = "" }: { className?: string }) {
  const { subnet, setSubnet, presets } = useSubnet();
  const isPreset = presets.includes(subnet as (typeof presets)[number]);

  return (
    <label className={`inline-flex items-center gap-1 text-[10px] text-zinc-500 ${className}`}>
      subnet
      <select
        value={isPreset ? subnet : "custom"}
        onChange={(e) => {
          const v = e.target.value;
          if (v !== "custom") setSubnet(Number(v));
        }}
        className="text-[10px] bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 text-zinc-300 mono"
      >
        {presets.map((n) => (
          <option key={n} value={n}>
            SN{n}
          </option>
        ))}
        <option value="custom">custom</option>
      </select>
      {!isPreset && (
        <input
          type="number"
          min={0}
          max={65535}
          value={subnet}
          onChange={(e) => setSubnet(Number(e.target.value) || 0)}
          className="w-12 text-[10px] bg-zinc-900 border border-zinc-700 rounded px-1 py-0.5 text-zinc-300 mono"
        />
      )}
    </label>
  );
}
