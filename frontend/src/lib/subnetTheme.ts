/** Per-subnet UI theme — SN97 (Albedo/v6 only) vs SN24 (Quasar/JSON). */

import { getSubnetProfile } from "@/lib/subnets";

export type SlotFilterKey =
  | "all"
  | "committed"
  | "v6"
  | "timelock_encrypted"
  | "json"
  | "unpublished"
  | "other"
  | "none";

export interface SubnetTheme {
  accent: "amber" | "violet" | "emerald";
  commitLabel: string;
  modelHost: "hippius" | "huggingface";
  pill: string;
  textAccent: string;
  textAccentSoft: string;
  feedItemBg: string;
  rowFlash: string;
  rowFlashSubtle: string;
  uidChipCommitted: string;
  kpiAccent: string;
  slotDefaultFilter: SlotFilterKey;
  slotPrimaryType: "v6" | "json";
  slotSummaryPrimaryLabel: string;
}

export interface SlotFilterDef {
  key: SlotFilterKey;
  label: string;
  color: string;
  hint?: string;
}

const SN97_SLOT_FILTERS: SlotFilterDef[] = [
  { key: "all", label: "all 256", color: "text-zinc-300 border-zinc-600" },
  { key: "v6", label: "v6", color: "text-lime-400 border-lime-500/40 bg-lime-500/10", hint: "published v6 pipe" },
  { key: "unpublished", label: "unpublished", color: "text-rose-300 border-rose-500/40 bg-rose-500/10", hint: "registered, no v6" },
  { key: "timelock_encrypted", label: "encrypted", color: "text-violet-300 border-violet-500/40 bg-violet-500/10", hint: "TimelockEncrypted" },
  { key: "none", label: "no commit", color: "text-zinc-500 border-zinc-700 bg-zinc-800/30" },
];

const SN24_SLOT_FILTERS: SlotFilterDef[] = [
  { key: "all", label: "all 256", color: "text-zinc-300 border-zinc-600" },
  { key: "committed", label: "has commit", color: "text-zinc-200 border-zinc-500 bg-zinc-800/40", hint: "any on-chain commit" },
  { key: "json", label: "quasar", color: "text-violet-400 border-violet-500/40 bg-violet-500/10", hint: "JSON model commits" },
  { key: "v6", label: "v5/v6", color: "text-lime-400 border-lime-500/40 bg-lime-500/10", hint: "pipe-format commits (rare on SN24)" },
  { key: "timelock_encrypted", label: "encrypted", color: "text-violet-300 border-violet-500/40 bg-violet-500/10" },
  { key: "other", label: "other", color: "text-orange-300 border-orange-500/40 bg-orange-500/10" },
  { key: "none", label: "no commit", color: "text-zinc-500 border-zinc-700 bg-zinc-800/30" },
];

export function getSubnetTheme(netuid: number): SubnetTheme {
  const profile = getSubnetProfile(netuid);

  if (profile.netuid === 24) {
    return {
      accent: "violet",
      commitLabel: profile.features.commitLabel,
      modelHost: profile.features.modelHost,
      pill: "pill-violet",
      textAccent: "text-violet-400",
      textAccentSoft: "text-violet-300",
      feedItemBg: "bg-violet-500/5",
      rowFlash: "bg-violet-500/15 ring-1 ring-violet-500/40",
      rowFlashSubtle: "bg-violet-500/10",
      uidChipCommitted: "border-violet-500/40 bg-violet-500/15 text-violet-300",
      kpiAccent: "text-violet-400",
      slotDefaultFilter: "json",
      slotPrimaryType: "json",
      slotSummaryPrimaryLabel: "quasar",
    };
  }

  return {
    accent: "amber",
    commitLabel: profile.features.commitLabel,
    modelHost: profile.features.modelHost,
    pill: "pill-v6",
    textAccent: "text-lime-400",
    textAccentSoft: "text-lime-300",
    feedItemBg: "bg-lime-500/5",
    rowFlash: "bg-lime-500/15 ring-1 ring-lime-500/40",
    rowFlashSubtle: "bg-lime-500/10",
    uidChipCommitted: "border-lime-500/40 bg-lime-500/15 text-lime-300",
    kpiAccent: "text-lime-400",
    slotDefaultFilter: "v6",
    slotPrimaryType: "v6",
    slotSummaryPrimaryLabel: "v6",
  };
}

export function getSlotFilters(netuid: number): SlotFilterDef[] {
  return netuid === 24 ? SN24_SLOT_FILTERS : SN97_SLOT_FILTERS;
}

export function slotGridColor(netuid: number, type: string): string {
  if (netuid === 24) {
    const sn24: Record<string, string> = {
      json: "bg-violet-500",
      v6: "bg-lime-500",
      v5: "bg-lime-600",
      timelock_encrypted: "bg-violet-600",
      binary: "bg-violet-700",
      other: "bg-orange-500",
      unknown: "bg-rose-500",
      none: "bg-zinc-700",
    };
    return sn24[type] ?? "bg-zinc-700";
  }
  if (type === "v6") return "bg-lime-500";
  if (type === "timelock_encrypted" || type === "binary") return "bg-violet-500";
  if (type === "none") return "bg-zinc-700";
  return "bg-rose-500";
}

export function slotTypeStyle(netuid: number, type: string): string {
  if (netuid === 24 && type === "json") {
    return "text-violet-300 border-violet-500/30 bg-violet-500/10";
  }
  if (netuid !== 24 && type === "v6") {
    return "text-lime-400 border-lime-500/30 bg-lime-500/10";
  }
  if (type === "timelock_encrypted" || type === "binary") {
    return "text-violet-300 border-violet-500/30 bg-violet-500/10";
  }
  if (type === "none") {
    return "text-zinc-500 border-zinc-700 bg-zinc-800/20";
  }
  if (netuid !== 24) {
    return "text-rose-300 border-rose-500/30 bg-rose-500/10";
  }
  const base: Record<string, string> = {
    v6: "text-lime-400 border-lime-500/30 bg-lime-500/10",
    v5: "text-lime-400 border-lime-500/30 bg-lime-500/10",
    json: "text-amber-300 border-amber-500/30 bg-amber-500/10",
    other: "text-orange-300 border-orange-500/30 bg-orange-500/10",
    unknown: "text-rose-300 border-rose-500/30 bg-rose-500/10",
  };
  return base[type] ?? base.unknown;
}

export function slotTypeLabel(netuid: number, type: string): string {
  if (type === "timelock_encrypted" || type === "binary") return "encrypted";
  if (type === "none") return "—";
  if (netuid === 24 && type === "json") return "quasar";
  if (netuid !== 24 && type !== "v6") return "unpublished";
  return type;
}
