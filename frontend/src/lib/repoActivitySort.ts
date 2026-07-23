import type { RepoTrackEntry } from "@/lib/api";

export type RepoTrackSortKey =
  | "remote_newest"
  | "remote_oldest"
  | "uid"
  | "repo"
  | "sync_issues";

export const REPO_TRACK_SORT_OPTIONS: { key: RepoTrackSortKey; label: string }[] = [
  { key: "remote_newest", label: "remote update · newest" },
  { key: "remote_oldest", label: "remote update · oldest" },
  { key: "uid", label: "uid" },
  { key: "repo", label: "repo name" },
  { key: "sync_issues", label: "sync issues first" },
];

/** Hub manifest / remote push time — definite update timestamp. */
export function definiteRemoteTime(entry: RepoTrackEntry): string | null {
  return entry.last_hub_change_at ?? entry.hub_updated_at ?? null;
}

export function hasDefiniteRemoteTime(entry: RepoTrackEntry): boolean {
  return definiteRemoteTime(entry) != null;
}

function remoteMs(entry: RepoTrackEntry): number {
  const iso = definiteRemoteTime(entry);
  return iso ? new Date(iso).getTime() : 0;
}

function fallbackMs(entry: RepoTrackEntry): number {
  const iso =
    entry.last_checked_at ?? entry.last_updated ?? entry.first_tracked_at ?? null;
  return iso ? new Date(iso).getTime() : 0;
}

function syncRank(entry: RepoTrackEntry): number {
  if (entry.pending_hub_poll) return 2;
  if (entry.digest_in_sync === false) return 0;
  if (entry.digest_in_sync === true) return 3;
  return 1;
}

/** Definite remote times first, then uncertain rows. */
export function sortRepoTracks(
  entries: RepoTrackEntry[],
  sortKey: RepoTrackSortKey
): RepoTrackEntry[] {
  const rows = [...entries];

  switch (sortKey) {
    case "remote_oldest":
      return rows.sort((a, b) => {
        const aDef = hasDefiniteRemoteTime(a);
        const bDef = hasDefiniteRemoteTime(b);
        if (aDef !== bDef) return aDef ? -1 : 1;
        const aMs = aDef ? remoteMs(a) : fallbackMs(a);
        const bMs = bDef ? remoteMs(b) : fallbackMs(b);
        return aMs - bMs;
      });
    case "uid":
      return rows.sort((a, b) => {
        const aDef = hasDefiniteRemoteTime(a);
        const bDef = hasDefiniteRemoteTime(b);
        if (aDef !== bDef) return aDef ? -1 : 1;
        const au = a.uid ?? Number.MAX_SAFE_INTEGER;
        const bu = b.uid ?? Number.MAX_SAFE_INTEGER;
        return au - bu;
      });
    case "repo":
      return rows.sort((a, b) => {
        const aDef = hasDefiniteRemoteTime(a);
        const bDef = hasDefiniteRemoteTime(b);
        if (aDef !== bDef) return aDef ? -1 : 1;
        return a.repo.localeCompare(b.repo);
      });
    case "sync_issues":
      return rows.sort((a, b) => {
        const aDef = hasDefiniteRemoteTime(a);
        const bDef = hasDefiniteRemoteTime(b);
        if (aDef !== bDef) return aDef ? -1 : 1;
        const sr = syncRank(a) - syncRank(b);
        if (sr !== 0) return sr;
        return remoteMs(b) - remoteMs(a) || fallbackMs(b) - fallbackMs(a);
      });
    case "remote_newest":
    default:
      return rows.sort((a, b) => {
        const aDef = hasDefiniteRemoteTime(a);
        const bDef = hasDefiniteRemoteTime(b);
        if (aDef !== bDef) return aDef ? -1 : 1;
        const aMs = aDef ? remoteMs(a) : fallbackMs(a);
        const bMs = bDef ? remoteMs(b) : fallbackMs(b);
        return bMs - aMs;
      });
  }
}
