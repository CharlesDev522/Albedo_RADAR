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
  version?: string;
  repo: string;
  digest: string;
  model_uri: string;
  model_family?: string | null;
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
  has_v6: boolean;
  version: string | null;
  commit_block: number | null;
  repo: string | null;
  model_uri: string | null;
  model_family?: string | null;
  commit_source: string | null;
  last_updated: string | null;
  incentive?: number | null;
  emission?: number | null;
  rank_position?: number | null;
  receiving_incentive?: boolean | null;
}

export interface SyncStatus {
  subnet: number;
  onchain_v6_count: number | null;
  db_v6_count: number;
  in_sync: boolean | null;
  onchain_uids: number[];
  db_uids: number[];
  missing_in_db: number[];
  stale_in_db?: number[];
  repos: string[];
  mode?: "db" | "live";
  last_db_update?: string | null;
}

export interface Registry {
  subnet: number;
  miners: RegistryMiner[];
  total: number;
  v6_count: number;
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

export interface EncryptedSyncStatus {
  subnet: number;
  onchain_encrypted_count: number;
  db_encrypted_count: number;
  in_sync: boolean;
  onchain_uids: number[];
  db_uids: number[];
  missing_in_db: number[];
  note: string;
}

export interface SlotStatusEntry {
  uid: number;
  hotkey: string;
  coldkey: string | null;
  registered_at_block: number | null;
  commitment_type: string;
  commit_block: number | null;
  deposit: number | null;
  reveal_round: number | null;
  detail: string | null;
  last_updated: string | null;
  is_published?: boolean;
  model_family?: string | null;
}

export interface SlotStatusSummary {
  subnet: number;
  total_slots: number;
  v6: number;
  v7?: number;
  json: number;
  timelock_encrypted: number;
  binary?: number;
  other: number;
  unknown: number;
  none: number;
  committed: number;
  unpublished?: number;
  qwen36_35b?: number;
  qwen3_4b?: number;
  last_scan_at: string | null;
}

export interface SlotStatusData {
  subnet: number;
  slots: SlotStatusEntry[];
  summary: SlotStatusSummary;
  filter: string | null;
  sort: string | null;
  source: string;
}

export interface QuasarKing {
  uid: number | null;
  hf_repo: string | null;
  king_revision: string | null;
  reign_number: number | null;
  crowned_at: string | null;
  weights_block: number | null;
}

export interface QuasarChainKing {
  uid: number | null;
  hf_repo: string | null;
  revision: string | null;
  support_fraction: number | null;
  block: number | null;
}

export interface QuasarEvalPhase {
  active: boolean;
  phase: string | null;
  label: string | null;
  detail: string | null;
  state_king_uid: number | null;
  chain_king_uid: number | null;
  winner_uid: number | null;
  weight_reveal_pending: boolean;
  current_block: number | null;
}

export interface QuasarStatus {
  subnet: number;
  source_url: string;
  dashboard_url: string;
  king: QuasarKing | null;
  consensus_king: QuasarChainKing | null;
  state_king_uid: number | null;
  eval_phase: QuasarEvalPhase | null;
  current_eval: string | null;
  queue_len: number;
  submission_counts: Record<string, number>;
  policy: Record<string, unknown> | null;
}

export interface MinerIncentiveEntry {
  uid: number;
  hotkey: string;
  coldkey?: string | null;
  incentive: number;
  emission: number;
  rank_position: number | null;
  is_validator: boolean;
  receiving_incentive: boolean;
  commit_repo?: string | null;
}

export interface IncentiveOverview {
  subnet: number;
  metagraph_block: number | null;
  incentivized_count: number;
  top_incentive: number;
  miners: MinerIncentiveEntry[];
  note: string;
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
      `/commitments?subnet=${subnet}&limit=200&sort=commit_block`
    ),
  getRegistry: (subnet = DEFAULT_SUBNET) =>
    fetchApi<Registry>(`/commitments/registry?subnet=${subnet}`),
  getSyncStatus: (subnet = DEFAULT_SUBNET, live = false) =>
    fetchApi<SyncStatus>(`/commitments/sync-status?subnet=${subnet}${live ? "&live=true" : ""}`),
  getEncryptedCommitments: (subnet = DEFAULT_SUBNET) =>
    fetchApi<{ commitments: EncryptedCommitment[]; total: number; pending_count: number }>(
      `/encrypted-commitments?subnet=${subnet}&status=pending&limit=200`
    ),
  getEncryptedStats: (subnet = DEFAULT_SUBNET) =>
    fetchApi<EncryptedCommitmentStats>(`/encrypted-commitments/stats?subnet=${subnet}`),
  getEncryptedSyncStatus: (subnet = DEFAULT_SUBNET) =>
    fetchApi<EncryptedSyncStatus>(`/encrypted-commitments/sync-status?subnet=${subnet}`),
  getSlotStatus: (subnet = DEFAULT_SUBNET, filter = "all", sort = "uid_asc", live = false) =>
    fetchApi<SlotStatusData>(
      `/slot-status?subnet=${subnet}&filter=${filter}&sort=${sort}${live ? "&live=true" : ""}`
    ),
  getRecent: (subnet = DEFAULT_SUBNET) =>
    fetchApi<{ commits: Commitment[] }>(`/live/recent?subnet=${subnet}`),
  getQuasarStatus: (subnet = 24) =>
    fetchApi<QuasarStatus>(`/quasar/status?subnet=${subnet}`),
  getIncentiveOverview: (subnet = DEFAULT_SUBNET, limit = 30, live = false) =>
    fetchApi<IncentiveOverview>(
      `/incentives?subnet=${subnet}&limit=${limit}${live ? "&live=true" : ""}`
    ),
};

export function hippiusModelUrl(repo: string, branch = "main"): string {
  const clean = repo.replace(/^\/+|\/+$/g, "");
  return `https://hub.hippius.com/models/${clean}/${branch}`;
}

export function hfModelUrl(repo: string, digest?: string): string {
  const clean = repo.replace(/^\/+|\/+$/g, "");
  if (digest?.startsWith("revision:")) {
    return `https://huggingface.co/${clean}/tree/${digest.slice("revision:".length)}`;
  }
  if (digest) return `https://huggingface.co/${clean}/tree/${digest}`;
  return `https://huggingface.co/${clean}`;
}

export function modelCommitUrl(
  repo: string,
  digest: string,
  host: "hippius" | "huggingface" = "hippius"
): string {
  if (host === "huggingface") return hfModelUrl(repo, digest);
  return hippiusModelUrl(repo);
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
