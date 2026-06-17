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
}

export interface SlotStatusSummary {
  subnet: number;
  total_slots: number;
  v6: number;
  json: number;
  timelock_encrypted: number;
  binary?: number;
  other: number;
  unknown: number;
  none: number;
  committed: number;
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

export interface ReignMember {
  king_version: number | null;
  title: string | null;
  uid: number | null;
  hotkey: string | null;
  coldkey?: string | null;
  model_uri?: string | null;
  model_repo?: string | null;
  hf_account?: string | null;
  weight_pct?: number | null;
  score_challenger?: number | null;
  score_king?: number | null;
}

export interface AlbedoPipelineState {
  updated_at: string | null;
  validate: { running: number; queued: number };
  pre_eval: { running: number; queued: number };
  eval: { running: number; queued: number };
  total_in_flight: number;
}

export interface DuelRun {
  eval_run_id: string | null;
  uid: number | null;
  hotkey: string | null;
  model_repo: string | null;
  hf_account: string | null;
  king_version: number | null;
  challenger_won: boolean;
  coronated: boolean;
  badge: string;
  score_challenger: number | null;
  score_king: number | null;
  win_margin: number | null;
  finished_at: string | null;
  defeated_king_hf: string | null;
}

export interface FailRun {
  eval_run_id: string | null;
  uid: number | null;
  hf_account: string | null;
  fault_code: string | null;
  finished_at: string | null;
}

export interface AlbedoStatus {
  subnet: number;
  updated_at: string | null;
  schema_version: number;
  source_url: string;
  dashboard_url: string;
  current_king: ReignMember | null;
  reign_chain: ReignMember[];
  crownings: DuelRun[];
  recent_duels: DuelRun[];
  recent_fails: FailRun[];
  pipeline: AlbedoPipelineState | null;
  stats: Record<string, number>;
  queue_len: number;
  current_eval: string | null;
}

export interface HfAccountStats {
  hf_account: string;
  coldkeys: string[];
  hotkey_count: number;
  challenges: number;
  duel_wins: number;
  duel_losses: number;
  crowns: number;
  dethrones_caused: number;
  times_dethroned: number;
  reign_versions: number[];
  win_rate: number;
  crown_rate: number;
  dethrone_rate: number;
  avg_win_margin: number | null;
}

export interface HfAnalytics {
  subnet: number;
  updated_at: string | null;
  summary: {
    total_eval_runs: number;
    total_crownings: number;
    unique_hf_accounts: number;
    top_crown_holder: string | null;
    crown_share_top: number;
  };
  accounts: HfAccountStats[];
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
  is_king: boolean;
  king_model_repo?: string | null;
  commit_repo?: string | null;
}

export interface IncentiveOverview {
  subnet: number;
  metagraph_block: number | null;
  king: ReignMember | null;
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
      `/commitments?subnet=${subnet}&limit=200&sort=last_updated`
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
  getAlbedoStatus: (subnet = DEFAULT_SUBNET) =>
    fetchApi<AlbedoStatus>(`/albedo/status?subnet=${subnet}`),
  getAlbedoAnalytics: (subnet = DEFAULT_SUBNET, limit = 40) =>
    fetchApi<HfAnalytics>(`/albedo/analytics?subnet=${subnet}&limit=${limit}`),
  getIncentiveOverview: (subnet = DEFAULT_SUBNET, limit = 30, live = false) =>
    fetchApi<IncentiveOverview>(
      `/albedo/incentives?subnet=${subnet}&limit=${limit}${live ? "&live=true" : ""}`
    ),
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
