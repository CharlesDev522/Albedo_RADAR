/** Server-side (SSR): Docker internal URL. Browser: same-origin proxy via next.config rewrites. */
function apiBase(): string {
  if (typeof window !== "undefined") {
    return "/api/v1";
  }
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000/api/v1"
  );
}

const DEFAULT_SUBNET = 97;

export interface Commitment {
  id: number;
  subnet: number;
  uid: number | null;
  hotkey: string;
  coldkey: string | null;
  registered_at_block: number | null;
  commit_block: number;
  reveal_string: string;
  repo: string;
  digest: string;
  model_uri: string;
  commit_source: string;
  first_seen: string;
  last_updated: string;
}

export interface CommitmentStats {
  subnet: number;
  total_neurons: number;
  committed_miners: number;
  uncommitted_miners: number;
  coverage_pct: number;
  latest_commit_block: number | null;
  last_scan_at: string;
}

export interface RegistryMiner {
  uid: number;
  hotkey: string;
  coldkey: string;
  registered_at_block: number | null;
  has_v5: boolean;
  commit_block: number | null;
  repo: string | null;
  model_uri: string | null;
  commit_source: string | null;
  last_updated: string | null;
}

export interface SyncStatus {
  subnet: number;
  onchain_v5_count: number;
  db_v5_count: number;
  in_sync: boolean;
  onchain_uids: number[];
  db_uids: number[];
  missing_in_db: number[];
  repos: string[];
}

export interface Registry {
  subnet: number;
  miners: RegistryMiner[];
  total: number;
  v5_count: number;
  uncommitted_count: number;
}

export interface EncryptedCommitment {
  id: number;
  subnet: number;
  uid: number | null;
  hotkey: string;
  coldkey: string | null;
  registered_at_block: number | null;
  commit_block: number;
  deposit: number;
  reveal_round: number;
  encrypted_hash: string;
  encrypted_preview: string;
  commitment_kind: string;
  status: string;
  first_seen: string;
  last_updated: string;
}

export interface EncryptedCommitmentStats {
  subnet: number;
  pending_encrypted: number;
  revealed_total: number;
  latest_commit_block: number | null;
  latest_reveal_round: number | null;
  last_scan_at: string;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  getStats: (subnet = DEFAULT_SUBNET) =>
    fetchApi<CommitmentStats>(`/commitments/stats?subnet=${subnet}`),
  getCommitments: (subnet = DEFAULT_SUBNET) =>
    fetchApi<{ commitments: Commitment[]; total: number }>(
      `/commitments?subnet=${subnet}&limit=200&sort=last_updated`
    ),
  getRegistry: (subnet = DEFAULT_SUBNET) =>
    fetchApi<Registry>(`/commitments/registry?subnet=${subnet}`),
  getSyncStatus: (subnet = DEFAULT_SUBNET) =>
    fetchApi<SyncStatus>(`/commitments/sync-status?subnet=${subnet}`),
  getEncryptedCommitments: (subnet = DEFAULT_SUBNET) =>
    fetchApi<{ commitments: EncryptedCommitment[]; total: number; pending_count: number }>(
      `/encrypted-commitments?subnet=${subnet}&status=pending&limit=200`
    ),
  getEncryptedStats: (subnet = DEFAULT_SUBNET) =>
    fetchApi<EncryptedCommitmentStats>(`/encrypted-commitments/stats?subnet=${subnet}`),
  getRecent: (subnet = DEFAULT_SUBNET) =>
    fetchApi<{ commits: Commitment[] }>(`/live/recent?subnet=${subnet}`),
};

export function hippiusModelUrl(repo: string, branch = "main"): string {
  const clean = repo.replace(/^\/+|\/+$/g, "");
  return `https://hub.hippius.com/models/${clean}/${branch}`;
}

export function shortAddr(addr: string, n = 5): string {
  if (!addr || addr.length <= n * 2 + 1) return addr;
  return `${addr.slice(0, n)}…${addr.slice(-n)}`;
}

export function shortRepo(repo: string, max = 28): string {
  if (!repo || repo.length <= max) return repo;
  const [org, name] = repo.split("/");
  if (name && name.length > 18) return `${org}/${name.slice(0, 16)}…`;
  return repo.slice(0, max) + "…";
}

export function shortHash(digest: string): string {
  return digest.replace("sha256:", "").slice(0, 10);
}

export { DEFAULT_SUBNET };
