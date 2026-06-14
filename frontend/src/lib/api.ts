const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const DEFAULT_SUBNET = 97;

export interface Commitment {
  id: number;
  subnet: number;
  uid: number | null;
  hotkey: string;
  coldkey: string | null;
  registered_at_block: number | null;
  commit_block: number;
  block_hash: string | null;
  reveal_string: string;
  version: string;
  repo: string;
  digest: string;
  model_uri: string;
  payload_hash: string;
  commit_payload: Record<string, unknown>;
  first_seen: string;
  last_updated: string;
}

export interface CommitmentList {
  commitments: Commitment[];
  total: number;
  subnet: number;
  committed_count: number;
  uncommitted_uids: number[];
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

export interface Event {
  id: number;
  event_type: string;
  subnet: number;
  block: number | null;
  data: Record<string, unknown>;
  timestamp: string;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 15 } });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  getCommitments: (subnet = DEFAULT_SUBNET) =>
    fetchApi<CommitmentList>(`/commitments?subnet=${subnet}&limit=200&sort=commit_block`),
  getCommitmentStats: (subnet = DEFAULT_SUBNET) =>
    fetchApi<CommitmentStats>(`/commitments/stats?subnet=${subnet}`),
  getCommitmentEvents: (subnet = DEFAULT_SUBNET) =>
    fetchApi<{ events: Event[] }>(`/events?subnet=${subnet}&limit=30`),
};

export function truncateAddress(addr: string, chars = 6): string {
  if (addr.length <= chars * 2 + 3) return addr;
  return `${addr.slice(0, chars)}...${addr.slice(-chars)}`;
}

export function truncateRepo(repo: string, max = 40): string {
  if (repo.length <= max) return repo;
  const parts = repo.split("/");
  if (parts.length >= 2) {
    return `${parts[0]}/${parts[1]?.slice(0, 20)}…`;
  }
  return repo.slice(0, max) + "…";
}

export { DEFAULT_SUBNET };
