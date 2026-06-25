/** SN97 Albedo UI theme. */

import { inferAlbedoModelFamily } from "@/lib/modelFamily";
import { getSubnetProfile } from "@/lib/subnets";

export const ALBEDO_PIPE_TYPES = new Set(["v6", "v7"]);

export type SlotFilterKey =
  | "all"
  | "committed"
  | "v6"
  | "qwen36_35b"
  | "qwen3_4b"
  | "timelock_encrypted"
  | "json"
  | "unpublished"
  | "other"
  | "none";

export interface SubnetTheme {
  accent: "amber";
  commitLabel: string;
  modelHost: "hippius";
  pill: string;
  textAccent: string;
  textAccentSoft: string;
  feedItemBg: string;
  rowFlash: string;
  rowFlashSubtle: string;
  uidChipCommitted: string;
  kpiAccent: string;
  slotDefaultFilter: SlotFilterKey;
  slotPrimaryType: "v6";
  slotSummaryPrimaryLabel: string;
}

export interface SlotFilterDef {
  key: SlotFilterKey;
  label: string;
  color: string;
  hint?: string;
}

const SLOT_FILTERS: SlotFilterDef[] = [
  { key: "all", label: "all 256", color: "text-zinc-300 border-zinc-600" },
  { key: "qwen36_35b", label: "Qwen3.6-35B", color: "text-sky-300 border-sky-500/40 bg-sky-500/10", hint: "albedo-qwen3.6-35b-* repos" },
  { key: "qwen3_4b", label: "Qwen3-4B", color: "text-amber-300 border-amber-500/40 bg-amber-500/10", hint: "legacy albedo-qwen3-4b-* repos" },
  { key: "v6", label: "published", color: "text-lime-400 border-lime-500/40 bg-lime-500/10", hint: "any on-chain pipe publish" },
  { key: "unpublished", label: "unpublished", color: "text-rose-300 border-rose-500/40 bg-rose-500/10", hint: "registered, no pipe publish" },
  { key: "timelock_encrypted", label: "encrypted", color: "text-violet-300 border-violet-500/40 bg-violet-500/10", hint: "TimelockEncrypted" },
  { key: "none", label: "no commit", color: "text-zinc-500 border-zinc-700 bg-zinc-800/30" },
];

export function isAlbedoPipeType(type: string): boolean {
  return ALBEDO_PIPE_TYPES.has(type);
}

export function isPublishedPipeType(type: string, _netuid?: number): boolean {
  return isAlbedoPipeType(type);
}

export function getSubnetTheme(_netuid?: number): SubnetTheme {
  const profile = getSubnetProfile();
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
    slotDefaultFilter: "qwen36_35b",
    slotPrimaryType: "v6",
    slotSummaryPrimaryLabel: "published",
  };
}

export function getSlotFilters(_netuid?: number): SlotFilterDef[] {
  return SLOT_FILTERS;
}

export function slotGridColor(_netuid: number, type: string): string {
  if (type === "v6" || type === "v7") return "bg-lime-500";
  if (type === "timelock_encrypted" || type === "binary") return "bg-violet-500";
  if (type === "none") return "bg-zinc-700";
  return "bg-rose-500";
}

export function slotTypeStyle(_netuid: number, type: string): string {
  if (type === "v6" || type === "v7") {
    return "text-lime-400 border-lime-500/30 bg-lime-500/10";
  }
  if (type === "timelock_encrypted" || type === "binary") {
    return "text-violet-300 border-violet-500/30 bg-violet-500/10";
  }
  if (type === "none") {
    return "text-zinc-500 border-zinc-700 bg-zinc-800/20";
  }
  return "text-rose-300 border-rose-500/30 bg-rose-500/10";
}

export function slotTypeLabel(
  _netuid: number,
  type: string,
  detail?: string | null,
  modelFamily?: string | null
): string {
  if (type === "timelock_encrypted" || type === "binary") return "encrypted";
  if (type === "none") return "—";
  if (!isAlbedoPipeType(type)) return "unpublished";
  const family = modelFamily ?? inferAlbedoModelFamily(detail);
  if (family === "qwen3.6-35b") return "Qwen3.6-35B";
  if (family === "qwen3-4b") return "Qwen3-4B";
  return "pipe";
}

export function slotGridColorForAlbedo(
  commitmentType: string,
  detail: string | null | undefined,
  modelFamily?: string | null
): string {
  if (commitmentType === "none") return "bg-zinc-700";
  if (commitmentType === "timelock_encrypted" || commitmentType === "binary") return "bg-violet-500";
  if (isAlbedoPipeType(commitmentType)) {
    const family = modelFamily ?? inferAlbedoModelFamily(detail);
    if (family === "qwen3.6-35b") return "bg-sky-500";
    if (family === "qwen3-4b") return "bg-amber-500";
    return "bg-lime-500";
  }
  return "bg-rose-500";
}
