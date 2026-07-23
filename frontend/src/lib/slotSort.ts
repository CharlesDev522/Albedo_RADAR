import type { SlotStatusEntry } from "@/lib/api";

export type SlotSortKey =
  | "uid_asc"
  | "uid_desc"
  | "reg_asc"
  | "reg_desc"
  | "commit_asc"
  | "commit_desc"
  | "coldkey_asc"
  | "coldkey_desc"
  | "type";

const UID_SORTS: SlotSortKey[] = ["uid_asc", "uid_desc"];
const COMMIT_SORTS: SlotSortKey[] = ["commit_asc", "commit_desc"];
const COLDKEY_SORTS: SlotSortKey[] = ["coldkey_asc", "coldkey_desc"];

export function sortLabel(key: SlotSortKey): string {
  const map: Record<SlotSortKey, string> = {
    uid_asc: "uid ↑",
    uid_desc: "uid ↓",
    reg_asc: "registered ↑",
    reg_desc: "registered ↓",
    commit_asc: "commit blk ↑",
    commit_desc: "commit blk ↓",
    coldkey_asc: "coldkey ↑",
    coldkey_desc: "coldkey ↓",
    type: "type",
  };
  return map[key];
}

export function toggleColumnSort(current: SlotSortKey, column: "uid" | "commit" | "coldkey"): SlotSortKey {
  if (column === "uid") return current === "uid_asc" ? "uid_desc" : "uid_asc";
  if (column === "commit") return current === "commit_desc" ? "commit_asc" : "commit_desc";
  return current === "coldkey_asc" ? "coldkey_desc" : "coldkey_asc";
}

export function columnSortDirection(
  sort: SlotSortKey,
  column: "uid" | "commit" | "coldkey"
): "asc" | "desc" | null {
  if (column === "uid" && UID_SORTS.includes(sort)) return sort === "uid_asc" ? "asc" : "desc";
  if (column === "commit" && COMMIT_SORTS.includes(sort)) return sort === "commit_asc" ? "asc" : "desc";
  if (column === "coldkey" && COLDKEY_SORTS.includes(sort)) return sort === "coldkey_asc" ? "asc" : "desc";
  return null;
}

function regKey(s: SlotStatusEntry, asc: boolean): number {
  if (s.registered_at_block == null) return asc ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  return s.registered_at_block;
}

function commitKey(s: SlotStatusEntry, asc: boolean): number {
  if (s.commit_block == null) return asc ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  return s.commit_block;
}

function coldkeyCmp(a: SlotStatusEntry, b: SlotStatusEntry, asc: boolean): number {
  const ka = a.coldkey?.toLowerCase() ?? "";
  const kb = b.coldkey?.toLowerCase() ?? "";
  if (!ka && !kb) return 0;
  if (!ka) return 1;
  if (!kb) return -1;
  const cmp = ka.localeCompare(kb);
  return asc ? cmp : -cmp;
}

export function sortSlotEntries(slots: SlotStatusEntry[], sort: SlotSortKey): SlotStatusEntry[] {
  const copy = [...slots];
  switch (sort) {
    case "uid_desc":
      return copy.sort((a, b) => b.uid - a.uid);
    case "reg_asc":
      return copy.sort((a, b) => regKey(a, true) - regKey(b, true) || a.uid - b.uid);
    case "reg_desc":
      return copy.sort((a, b) => regKey(b, false) - regKey(a, false) || a.uid - b.uid);
    case "commit_asc":
      return copy.sort((a, b) => commitKey(a, true) - commitKey(b, true) || a.uid - b.uid);
    case "commit_desc":
      return copy.sort((a, b) => commitKey(b, false) - commitKey(a, false) || a.uid - b.uid);
    case "coldkey_asc":
      return copy.sort((a, b) => coldkeyCmp(a, b, true) || a.uid - b.uid);
    case "coldkey_desc":
      return copy.sort((a, b) => coldkeyCmp(a, b, false) || a.uid - b.uid);
    case "type":
      return copy.sort((a, b) => a.commitment_type.localeCompare(b.commitment_type) || a.uid - b.uid);
    default:
      return copy.sort((a, b) => a.uid - b.uid);
  }
}

export type CommitRowSortKey = "uid_asc" | "uid_desc" | "commit_asc" | "commit_desc" | "coldkey_asc" | "coldkey_desc";

export function sortCommitRows<T extends { uid: number | null; commit_block: number; coldkey: string | null }>(
  rows: T[],
  sort: CommitRowSortKey
): T[] {
  const copy = [...rows];
  const uid = (a: T, b: T) => (a.uid ?? 9999) - (b.uid ?? 9999);
  switch (sort) {
    case "uid_desc":
      return copy.sort((a, b) => (b.uid ?? -1) - (a.uid ?? -1));
    case "commit_asc":
      return copy.sort((a, b) => a.commit_block - b.commit_block || uid(a, b));
    case "commit_desc":
      return copy.sort((a, b) => b.commit_block - a.commit_block || uid(a, b));
    case "coldkey_asc":
      return copy.sort((a, b) => (a.coldkey ?? "").localeCompare(b.coldkey ?? "") || uid(a, b));
    case "coldkey_desc":
      return copy.sort((a, b) => (b.coldkey ?? "").localeCompare(a.coldkey ?? "") || uid(a, b));
    default:
      return copy.sort((a, b) => uid(a, b));
  }
}

export function toggleCommitSort(current: CommitRowSortKey, column: "uid" | "commit" | "coldkey"): CommitRowSortKey {
  if (column === "uid") return current === "uid_asc" ? "uid_desc" : "uid_asc";
  if (column === "commit") return current === "commit_desc" ? "commit_asc" : "commit_desc";
  return current === "coldkey_asc" ? "coldkey_desc" : "coldkey_asc";
}

export function commitColumnDir(sort: CommitRowSortKey, column: "uid" | "commit" | "coldkey"): "asc" | "desc" | null {
  if (column === "uid") return sort.startsWith("uid_") ? (sort === "uid_asc" ? "asc" : "desc") : null;
  if (column === "commit") return sort.startsWith("commit_") ? (sort === "commit_asc" ? "asc" : "desc") : null;
  if (column === "coldkey") return sort.startsWith("coldkey_") ? (sort === "coldkey_asc" ? "asc" : "desc") : null;
  return null;
}
