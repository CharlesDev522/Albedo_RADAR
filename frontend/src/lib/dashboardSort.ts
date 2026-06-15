import type { RegistryMiner } from "@/lib/api";

/** Sort keys for v5/v6 commits table and miner registry. */
export type DashboardSortKey =
  | "uid_asc"
  | "uid_desc"
  | "commit_asc"
  | "commit_desc"
  | "reg_asc"
  | "reg_desc"
  | "coldkey_asc"
  | "coldkey_desc"
  | "committed_first"
  | "uncommitted_first";

export type SortColumn = "uid" | "commit" | "reg" | "coldkey" | "status";

function numKey(n: number | null | undefined, asc: boolean): number {
  if (n == null) return asc ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  return n;
}

function coldkeyCmp(a: string | null | undefined, b: string | null | undefined, asc: boolean): number {
  const ka = a?.toLowerCase() ?? "";
  const kb = b?.toLowerCase() ?? "";
  if (!ka && !kb) return 0;
  if (!ka) return 1;
  if (!kb) return -1;
  const cmp = ka.localeCompare(kb);
  return asc ? cmp : -cmp;
}

function uidTie(a: number | null | undefined, b: number | null | undefined): number {
  return (a ?? 9999) - (b ?? 9999);
}

export function sortCommits<T extends {
  uid: number | null;
  commit_block: number;
  registered_at_block?: number | null;
  coldkey: string | null;
}>(rows: T[], sort: DashboardSortKey): T[] {
  const copy = [...rows];
  switch (sort) {
    case "uid_desc":
      return copy.sort((a, b) => (b.uid ?? -1) - (a.uid ?? -1));
    case "commit_asc":
      return copy.sort((a, b) => a.commit_block - b.commit_block || uidTie(a.uid, b.uid));
    case "commit_desc":
      return copy.sort((a, b) => b.commit_block - a.commit_block || uidTie(a.uid, b.uid));
    case "reg_asc":
      return copy.sort(
        (a, b) =>
          numKey(a.registered_at_block, true) - numKey(b.registered_at_block, true) || uidTie(a.uid, b.uid)
      );
    case "reg_desc":
      return copy.sort(
        (a, b) =>
          numKey(b.registered_at_block, false) - numKey(a.registered_at_block, false) || uidTie(a.uid, b.uid)
      );
    case "coldkey_asc":
      return copy.sort((a, b) => coldkeyCmp(a.coldkey, b.coldkey, true) || uidTie(a.uid, b.uid));
    case "coldkey_desc":
      return copy.sort((a, b) => coldkeyCmp(a.coldkey, b.coldkey, false) || uidTie(a.uid, b.uid));
    default:
      return copy.sort((a, b) => uidTie(a.uid, b.uid));
  }
}

export function sortRegistry(miners: RegistryMiner[], sort: DashboardSortKey): RegistryMiner[] {
  const copy = [...miners];
  switch (sort) {
    case "uid_desc":
      return copy.sort((a, b) => b.uid - a.uid);
    case "commit_asc":
      return copy.sort(
        (a, b) => numKey(a.commit_block, true) - numKey(b.commit_block, true) || a.uid - b.uid
      );
    case "commit_desc":
      return copy.sort(
        (a, b) => numKey(b.commit_block, false) - numKey(a.commit_block, false) || a.uid - b.uid
      );
    case "reg_asc":
      return copy.sort(
        (a, b) => numKey(a.registered_at_block, true) - numKey(b.registered_at_block, true) || a.uid - b.uid
      );
    case "reg_desc":
      return copy.sort(
        (a, b) => numKey(b.registered_at_block, false) - numKey(a.registered_at_block, false) || a.uid - b.uid
      );
    case "coldkey_asc":
      return copy.sort((a, b) => coldkeyCmp(a.coldkey, b.coldkey, true) || a.uid - b.uid);
    case "coldkey_desc":
      return copy.sort((a, b) => coldkeyCmp(a.coldkey, b.coldkey, false) || a.uid - b.uid);
    case "committed_first":
      return copy.sort(
        (a, b) =>
          Number(b.has_v5) - Number(a.has_v5) ||
          numKey(b.commit_block, false) - numKey(a.commit_block, false) ||
          a.uid - b.uid
      );
    case "uncommitted_first":
      return copy.sort(
        (a, b) =>
          Number(a.has_v5) - Number(b.has_v5) ||
          numKey(a.commit_block, true) - numKey(b.commit_block, true) ||
          a.uid - b.uid
      );
    default:
      return copy.sort((a, b) => a.uid - b.uid);
  }
}

export function toggleDashboardSort(current: DashboardSortKey, column: SortColumn): DashboardSortKey {
  if (column === "uid") return current === "uid_asc" ? "uid_desc" : "uid_asc";
  if (column === "commit") return current === "commit_desc" ? "commit_asc" : "commit_desc";
  if (column === "reg") return current === "reg_desc" ? "reg_asc" : "reg_desc";
  if (column === "coldkey") return current === "coldkey_asc" ? "coldkey_desc" : "coldkey_asc";
  if (column === "status") return current === "committed_first" ? "uncommitted_first" : "committed_first";
  return current;
}

export function dashboardColumnDir(sort: DashboardSortKey, column: SortColumn): "asc" | "desc" | null {
  if (column === "uid" && sort.startsWith("uid_")) return sort === "uid_asc" ? "asc" : "desc";
  if (column === "commit" && sort.startsWith("commit_")) return sort === "commit_asc" ? "asc" : "desc";
  if (column === "reg" && sort.startsWith("reg_")) return sort === "reg_asc" ? "asc" : "desc";
  if (column === "coldkey" && sort.startsWith("coldkey_")) return sort === "coldkey_asc" ? "asc" : "desc";
  if (column === "status" && (sort === "committed_first" || sort === "uncommitted_first")) {
    return sort === "committed_first" ? "desc" : "asc";
  }
  return null;
}

export function sortLabel(sort: DashboardSortKey): string {
  const labels: Record<DashboardSortKey, string> = {
    uid_asc: "uid ↑",
    uid_desc: "uid ↓",
    commit_asc: "commit ↑",
    commit_desc: "commit ↓",
    reg_asc: "registered ↑",
    reg_desc: "registered ↓",
    coldkey_asc: "coldkey ↑",
    coldkey_desc: "coldkey ↓",
    committed_first: "committed first",
    uncommitted_first: "uncommitted first",
  };
  return labels[sort];
}
