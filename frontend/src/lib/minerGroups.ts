import type { Commitment, Registry, RegistryMiner, SlotStatusEntry } from "@/lib/api";

export type GroupView = "coldkey" | "owner";

export interface MinerRow {
  uid: number;
  hotkey: string;
  coldkey: string;
  hasCommit: boolean;
  version: string | null;
  repo: string | null;
  digest: string | null;
  commitBlock: number | null;
  commitmentType: string | null;
  isPublished: boolean | null;
}

export interface MinerGroup {
  key: string;
  label: string;
  kind: GroupView;
  miners: MinerRow[];
  committedCount: number;
  coldkeyCount: number;
  ownerCounts: Record<string, number>;
}

export function repoOwner(repo: string | null | undefined): string | null {
  if (!repo) return null;
  const clean = repo.replace(/^\/+|\/+$/g, "");
  const [owner] = clean.split("/");
  return owner && owner.length > 0 ? owner : null;
}

export function buildMinerRows(
  registry: Registry | null,
  commits: Commitment[],
  slotsByUid?: Map<number, SlotStatusEntry>
): MinerRow[] {
  const commitByUid = new Map(
    commits.filter((c) => c.uid != null).map((c) => [c.uid as number, c])
  );
  const miners: RegistryMiner[] = registry?.miners ?? [];
  return miners.map((m) => {
    const c = commitByUid.get(m.uid);
    const slot = slotsByUid?.get(m.uid);
    return {
      uid: m.uid,
      hotkey: m.hotkey,
      coldkey: m.coldkey,
      hasCommit: m.has_v6,
      version: m.version ?? c?.version ?? null,
      repo: m.repo ?? c?.repo ?? null,
      digest: c?.digest ?? m.model_uri?.split("@")[1] ?? null,
      commitBlock: m.commit_block ?? c?.commit_block ?? null,
      commitmentType: slot?.commitment_type ?? null,
      isPublished: slot?.is_published ?? null,
    };
  });
}

function ownerCountsFor(miners: MinerRow[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const m of miners) {
    const owner = repoOwner(m.repo);
    if (!owner) continue;
    counts[owner] = (counts[owner] ?? 0) + 1;
  }
  return counts;
}

function coldkeysFor(miners: MinerRow[]): Set<string> {
  return new Set(miners.map((m) => m.coldkey));
}

function sortGroups(groups: MinerGroup[]): MinerGroup[] {
  return [...groups].sort((a, b) => {
    if (b.miners.length !== a.miners.length) return b.miners.length - a.miners.length;
    if (b.committedCount !== a.committedCount) return b.committedCount - a.committedCount;
    return a.label.localeCompare(b.label);
  });
}

export function groupByColdkey(rows: MinerRow[], multiOnly: boolean): MinerGroup[] {
  const map = new Map<string, MinerRow[]>();
  for (const row of rows) {
    const key = row.coldkey || "unknown";
    const list = map.get(key) ?? [];
    list.push(row);
    map.set(key, list);
  }

  const groups: MinerGroup[] = [];
  for (const [key, miners] of map) {
    if (multiOnly && miners.length < 2) continue;
    const sorted = [...miners].sort((a, b) => a.uid - b.uid);
    groups.push({
      key,
      label: key,
      kind: "coldkey",
      miners: sorted,
      committedCount: sorted.filter((m) => m.hasCommit).length,
      coldkeyCount: 1,
      ownerCounts: ownerCountsFor(sorted),
    });
  }
  return sortGroups(groups);
}

export function groupByOwner(rows: MinerRow[], multiOnly: boolean): MinerGroup[] {
  const map = new Map<string, MinerRow[]>();
  for (const row of rows) {
    const owner = repoOwner(row.repo);
    if (!owner) continue;
    const list = map.get(owner) ?? [];
    list.push(row);
    map.set(owner, list);
  }

  const groups: MinerGroup[] = [];
  for (const [owner, miners] of map) {
    if (multiOnly && miners.length < 2) continue;
    const sorted = [...miners].sort((a, b) => a.uid - b.uid);
    groups.push({
      key: owner,
      label: owner,
      kind: "owner",
      miners: sorted,
      committedCount: sorted.filter((m) => m.hasCommit).length,
      coldkeyCount: coldkeysFor(sorted).size,
      ownerCounts: { [owner]: sorted.length },
    });
  }
  return sortGroups(groups);
}

export function clusterSummary(rows: MinerRow[]) {
  const coldkeyGroups = groupByColdkey(rows, true);
  const ownerGroups = groupByOwner(rows, true);
  const multiColdkeys = coldkeyGroups.length;
  const multiOwners = ownerGroups.length;
  const largestColdkey = coldkeyGroups[0]?.miners.length ?? 0;
  const largestOwner = ownerGroups[0]?.miners.length ?? 0;
  return {
    multiColdkeys,
    multiOwners,
    largestColdkey,
    largestOwner,
    totalMiners: rows.length,
    v6Miners: rows.filter((r) => r.hasCommit).length,
  };
}

const OWNER_PALETTE = [
  { border: "border-lime-500/40", bg: "bg-lime-500/10", text: "text-lime-300", dot: "bg-lime-400" },
  { border: "border-sky-500/40", bg: "bg-sky-500/10", text: "text-sky-300", dot: "bg-sky-400" },
  { border: "border-violet-500/40", bg: "bg-violet-500/10", text: "text-violet-300", dot: "bg-violet-400" },
  { border: "border-amber-500/40", bg: "bg-amber-500/10", text: "text-amber-300", dot: "bg-amber-400" },
  { border: "border-rose-500/40", bg: "bg-rose-500/10", text: "text-rose-300", dot: "bg-rose-400" },
  { border: "border-emerald-500/40", bg: "bg-emerald-500/10", text: "text-emerald-300", dot: "bg-emerald-400" },
  { border: "border-orange-500/40", bg: "bg-orange-500/10", text: "text-orange-300", dot: "bg-orange-400" },
  { border: "border-cyan-500/40", bg: "bg-cyan-500/10", text: "text-cyan-300", dot: "bg-cyan-400" },
] as const;

export function ownerPalette(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return OWNER_PALETTE[h % OWNER_PALETTE.length];
}
