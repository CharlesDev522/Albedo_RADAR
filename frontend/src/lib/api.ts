/** Server-side (SSR): Docker internal URL. Browser: same-origin proxy via Next route handler. */
function apiBase(): string {
  if (typeof window !== "undefined") {
    return "/api/v1";
  }
  if (process.env.INTERNAL_API_PROXY) {
    return process.env.INTERNAL_API_PROXY.replace(/\/$/, "");
  }
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000/api/v1"
  ).replace(/\/$/, "");
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

export interface ChampionReward {
  uid: number | null;
  hotkey: string | null;
  coldkey?: string | null;
  incentive: number;
  emission_per_epoch_alpha: number;
  daily_alpha: number;
  daily_tao_equivalent: number | null;
  daily_usd: number | null;
  alpha_price_tao: number | null;
  commit_repo?: string | null;
  epochs_per_day: number;
  calculation_source: string;
  daily_reward_rao?: number | null;
  emission_raw?: number | null;
  note: string;
}

export interface IncentiveOverview {
  subnet: number;
  metagraph_block: number | null;
  incentivized_count: number;
  top_incentive: number;
  miners: MinerIncentiveEntry[];
  champion: ChampionReward | null;
  note: string;
}

export interface MarketOverview {
  subnet: number;
  tao_price_usd: number | null;
  tao_price_source: string | null;
  tao_price_updated_at: string | null;
  registration_burn_tao: number | null;
  registration_burn_usd: number | null;
  alpha_price_tao: number | null;
  chain_block: number | null;
  network: string;
  fetched_at: string;
}

export interface RepoActivityOverview {
  subnet: number;
  tracked_miners: number;
  unique_repos: number;
  tracked_repos: number;
  qwen36_35b_repos: number;
  qwen3_4b_repos: number;
  in_sync_count: number;
  mismatch_count: number;
  hub_updates_24h: number;
  on_chain_events_24h: number;
  last_poll_at: string | null;
  hippius_count: number;
  huggingface_count: number;
  pending_hub_poll: number;
  hub_watch_count?: number;
  slot_only_count?: number;
  chain_committed_count?: number;
}

export interface HippiusLatestResponse {
  total_indexed: number;
  repos: HippiusLatestRepo[];
}

export interface HippiusLatestRepo {
  repo: string;
  model_family?: string | null;
  digest: string;
  indexed_at?: string | null;
  file_count?: number | null;
  total_size_bytes?: number | null;
  hub_url: string;
}

export interface RepoTrackEntry {
  id: number;
  subnet: number;
  repo: string;
  repo_host: string;
  uid: number | null;
  hotkey: string | null;
  coldkey: string | null;
  model_family: string | null;
  chain_digest: string | null;
  hub_digest: string | null;
  hub_revision: string;
  hub_commit_message: string | null;
  hub_updated_at: string | null;
  file_count: number | null;
  total_bytes: number | null;
  digest_in_sync: boolean | null;
  last_checked_at: string | null;
  last_hub_change_at: string | null;
  first_tracked_at: string;
  last_updated: string;
  pending_hub_poll?: boolean;
  track_source?: string | null;
}

export interface RepoActivityEvent {
  id: number;
  subnet: number;
  event_type: string;
  repo: string;
  uid: number | null;
  hotkey: string | null;
  coldkey: string | null;
  model_family: string | null;
  chain_digest: string | null;
  hub_digest: string | null;
  previous_digest: string | null;
  revision: string | null;
  commit_block: number | null;
  commit_message: string | null;
  changed_files: { name: string; change: string; digest?: string; size?: number }[];
  detected_at: string;
  meta: Record<string, unknown>;
}

export interface AlbedoLiveDuelParticipant {
  uid?: number | null;
  hotkey?: string | null;
  repo?: string | null;
  model_name?: string | null;
  namespace?: string | null;
  model_uri?: string | null;
  king_version?: number | null;
}

export interface AlbedoLiveDuel {
  subnet: number;
  is_active: boolean;
  status: string;
  phase_label: string;
  eval_run_id?: string | null;
  submission_id?: string | null;
  pipeline_stage?: string | null;
  pipeline_detail?: string | null;
  challenger?: AlbedoLiveDuelParticipant | null;
  king?: AlbedoLiveDuelParticipant | null;
  progress_pct?: number | null;
  sample_count?: number | null;
  generated_sample_count?: number | null;
  started_at?: string | null;
  elapsed_seconds?: number | null;
  eval_queue_depth: number;
  pipeline_counts: Record<string, { running: number; queued: number }>;
  dashboard_url: string;
  updated_at?: string | null;
  note: string;
}

export interface AlbedoReignMember {
  king_version: number;
  model_uri: string;
  model_name: string;
  namespace: string;
  hotkey: string;
  uid: number;
  weight_bps: number;
  score_challenger?: number | null;
  score_king?: number | null;
  eval_run_id?: string | null;
}

export interface AlbedoCurrentEval {
  eval_run_id: string;
  state: string;
  model_uri: string;
  model_name: string;
  namespace: string;
  hotkey: string;
  uid: number;
  sample_count?: number | null;
  generated_sample_count?: number | null;
  started_at?: string | null;
}

export interface AlbedoDuelJudgeVote {
  judge: string;
  short_name: string;
  challenger_score: number;
  king_score: number;
  pick_challenger: boolean;
  agrees_with_verdict: boolean;
  margin_from_neutral: number;
}

export interface AlbedoDuelSummary {
  eval_run_id: string;
  finished_at: string;
  challenger_won: boolean;
  coronated: boolean;
  king_version?: number | null;
  score_challenger: number;
  score_king: number;
  win_margin: number;
  model_uri: string;
  model_name: string;
  namespace: string;
  repo?: string | null;
  coldkey?: string | null;
  hotkey: string;
  uid: number;
  king_model_uri?: string | null;
  king_model_name?: string | null;
  king_namespace?: string | null;
  king_repo?: string | null;
  king_coldkey?: string | null;
  king_uid?: number | null;
  king_hotkey?: string | null;
  king_version_defended?: number | null;
  valid_turns?: number | null;
  total_turns?: number | null;
  scoring_mode?: string | null;
  required_win_margin?: number | null;
  margin_cleared?: boolean | null;
  scored_sample_count?: number | null;
  judge_errors?: number | null;
  metric_breakdown?: Record<string, number>;
  category_breakdown?: Record<string, number>;
  artifacts?: Record<string, string>;
  judge_scores?: Record<string, number>;
  judge_votes?: AlbedoDuelJudgeVote[];
  judge_spread?: number | null;
  panel_pattern?: string | null;
  unanimous_panel?: boolean;
}

export interface AlbedoKingCoronation {
  king_version: number;
  model_uri: string;
  model_name: string;
  namespace: string;
  repo?: string | null;
  coldkey?: string | null;
  hotkey: string;
  uid: number;
  finished_at: string;
  eval_run_id: string;
  score_challenger: number;
  score_king: number;
  win_margin: number;
  defeated_king_version?: number | null;
  defeated_model_uri?: string | null;
  defeated_model_name?: string | null;
  defeated_namespace?: string | null;
  defeated_repo?: string | null;
  defeated_coldkey?: string | null;
}

export interface AlbedoWinRateRow {
  key: string;
  label: string;
  duels: number;
  wins: number;
  losses: number;
  win_pct: number;
  avg_margin?: number | null;
  coronations: number;
}

export interface AlbedoJudgeAggregate {
  judge: string;
  short_name: string;
  avg_challenger_score: number;
  duels: number;
}

export interface AlbedoJudgeDetail {
  judge: string;
  short_name: string;
  duels: number;
  avg_challenger_score: number;
  avg_king_score: number;
  score_std?: number | null;
  pick_challenger_pct: number;
  pick_king_pct: number;
  agree_verdict_pct: number;
  overturn_duels: number;
  split_majority_align_pct?: number | null;
  solo_dissent_win_pct?: number | null;
  extreme_call_pct?: number | null;
  avg_score_when_challenger_wins?: number | null;
  avg_score_when_king_wins?: number | null;
  unanimous_challenger_duels: number;
  unanimous_king_duels: number;
  split_duels: number;
}

export interface AlbedoJudgeConsensus {
  pattern: string;
  label: string;
  duels: number;
  pct: number;
  challenger_wins: number;
  king_wins: number;
}

export interface AlbedoJudgeSlice {
  judge: string;
  short_name: string;
  duels: number;
  avg_challenger_score: number;
  pick_challenger_pct: number;
  agree_verdict_pct: number;
}

export interface AlbedoEntityJudgeStats {
  key: string;
  label: string;
  repo?: string | null;
  coldkey?: string | null;
  hotkey?: string | null;
  uid?: number | null;
  miner_count: number;
  repos: string[];
  coldkeys?: string[];
  duels: number;
  wins: number;
  losses: number;
  win_pct: number;
  coronations: number;
  avg_margin?: number | null;
  avg_judge_spread?: number | null;
  unanimous_pct?: number | null;
  judges: AlbedoJudgeSlice[];
  recent_dq?: number;
  dq_rate_pct?: number | null;
  total_attempts?: number;
}

export interface AlbedoRepoSubmissionStats {
  key: string;
  label: string;
  repo: string;
  coldkeys: string[];
  eval_submissions: number;
  recent_dq: number;
  total_attempts: number;
  dq_rate_pct?: number | null;
}

export interface AlbedoJudgePairwise {
  judge_a: string;
  judge_b: string;
  short_name_a: string;
  short_name_b: string;
  duels: number;
  agree_pct: number;
  avg_score_delta?: number | null;
  score_correlation?: number | null;
}

export interface AlbedoJudgeOutcomeSlice {
  outcome: string;
  label: string;
  duels: number;
  judges: AlbedoJudgeSlice[];
}

export interface AlbedoJudgeSpreadSummary {
  avg_spread?: number | null;
  high_spread_duels: number;
  high_spread_pct: number;
  unanimous_duels: number;
  unanimous_pct: number;
  split_duels: number;
  split_pct: number;
}

export interface AlbedoJudgeAnalytics {
  total_submissions: number;
  judge_models: string[];
  by_repo: AlbedoEntityJudgeStats[];
  by_coldkey: AlbedoEntityJudgeStats[];
  pairwise: AlbedoJudgePairwise[];
  by_outcome: AlbedoJudgeOutcomeSlice[];
  spread_summary: AlbedoJudgeSpreadSummary;
}

export interface AlbedoMetricAggregate {
  metric: string;
  avg_challenger_score: number;
  duels: number;
}

export interface AlbedoMarginBucket {
  label: string;
  count: number;
}

export interface AlbedoTimelinePoint {
  date: string;
  duels: number;
  challenger_wins: number;
  king_wins: number;
  coronations: number;
  challenger_win_pct: number;
}

export interface AlbedoPipelineStage {
  stage: string;
  status?: string | null;
  detail?: string | null;
}

export interface AlbedoEvalParticipant {
  position?: number | null;
  uid?: number | null;
  hotkey?: string | null;
  repo?: string | null;
  model_uri?: string | null;
  model_name?: string | null;
  namespace?: string | null;
  state?: string | null;
  submission_id?: string | null;
  eval_run_id?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  commit_block?: number | null;
}

export interface AlbedoPipelineBucket {
  stage: string;
  label: string;
  running_count: number;
  queued_count: number;
  running: AlbedoEvalParticipant[];
  queued: AlbedoEvalParticipant[];
}

export interface AlbedoEvalFail {
  submission_id?: string | null;
  eval_run_id?: string | null;
  uid?: number | null;
  hotkey?: string | null;
  repo?: string | null;
  coldkey?: string | null;
  model_uri?: string | null;
  state?: string | null;
  fault_class?: string | null;
  fault_code?: string | null;
  fault_message?: string | null;
  updated_at?: string | null;
}

export interface AlbedoEvalQueueOverview {
  subnet: number;
  source_url: string;
  updated_at?: string | null;
  dashboard_updated_at?: string | null;
  state_updated_at?: string | null;
  current_eval?: AlbedoCurrentEval | null;
  queue: AlbedoEvalParticipant[];
  pipeline: AlbedoPipelineBucket[];
  fails: AlbedoEvalFail[];
  fail_counts_by_class: Record<string, number>;
  queue_length: number;
  fail_count: number;
  note: string;
}

export interface AlbedoReignSlotHolder {
  key: string;
  label: string;
  hotkey: string;
  uid: number;
  slots_held: number;
  weight_bps: number;
  weight_pct: number;
  king_versions: number[];
}

export interface AlbedoKingTenure {
  king_version: number;
  model_uri: string;
  model_name: string;
  namespace: string;
  repo?: string | null;
  coldkey?: string | null;
  hotkey: string;
  uid: number;
  reign_rank?: number | null;
  weight_bps: number;
  weight_pct: number;
  reign_slots: number;
  is_current_king: boolean;
  in_reign_chain: boolean;
  coronation_at?: string | null;
  active_until?: string | null;
  slot_until?: string | null;
  active_tenure_hours?: number | null;
  slot_tenure_hours?: number | null;
  defenses: number;
  attacks_faced: number;
  defense_pct?: number | null;
  coronation_margin?: number | null;
  defeated_king_version?: number | null;
}

export interface AlbedoCrownEvent {
  king_version: number;
  crowned_at: string;
  active_until?: string | null;
  slot_until?: string | null;
  active_hours?: number | null;
  slot_hours?: number | null;
  weight_bps?: number;
  estimated_alpha?: number | null;
  estimated_tao?: number | null;
  repo?: string | null;
  coldkey?: string | null;
  hotkey: string;
  uid: number;
  model_name: string;
  is_current_king: boolean;
}

export interface AlbedoRewardBasis {
  daily_subnet_alpha: number;
  alpha_price_tao?: number | null;
  tao_price_usd?: number | null;
  daily_subnet_tao?: number | null;
  daily_subnet_usd?: number | null;
  calculation_source: string;
  default_weight_bps: number;
  note: string;
}

export interface AlbedoCrownLeaderboardRow {
  key: string;
  label: string;
  group_type: string;
  coronations: number;
  total_active_hours: number;
  total_slot_hours: number;
  current_weight_pct: number;
  reign_slots: number;
  owner_count: number;
  multi_owner: boolean;
  coldkeys: string[];
  hotkeys: string[];
  uids: number[];
  repos?: string[];
  duel_count: number;
  challenger_wins: number;
  challenger_win_pct?: number | null;
  total_estimated_alpha?: number | null;
  total_estimated_tao?: number | null;
  ongoing_daily_alpha?: number | null;
  crown_events: AlbedoCrownEvent[];
}

export interface AlbedoRepoColdkeyLink {
  repo: string;
  coldkey: string;
  hotkey?: string | null;
  uid?: number | null;
  coronations: number;
  total_slot_hours: number;
  total_active_hours: number;
  total_estimated_alpha?: number | null;
  total_estimated_tao?: number | null;
  ongoing_daily_alpha?: number | null;
  in_reign: boolean;
  last_crowned_at?: string | null;
}

export interface AlbedoRepoCrownAnalysis {
  reward_basis: AlbedoRewardBasis;
  crowns_by_repo: AlbedoCrownLeaderboardRow[];
  crowns_by_coldkey: AlbedoCrownLeaderboardRow[];
  repo_coldkey_links: AlbedoRepoColdkeyLink[];
  multi_owner_repos: string[];
  total_repos_crowned: number;
  total_unique_coldkeys: number;
  grand_total_estimated_alpha?: number | null;
  grand_total_estimated_tao?: number | null;
  earliest_crown_version?: number | null;
  latest_crown_version?: number | null;
  archived_crown_count?: number;
  missing_crown_versions?: number[];
  crown_history_coverage_note?: string;
}

export interface AlbedoAnalysisOverview {
  subnet: number;
  source: string;
  source_url: string;
  updated_at?: string | null;
  judge_models: string[];
  total_duels: number;
  challenger_wins: number;
  king_wins: number;
  coronations: number;
  challenger_win_pct: number;
  king_win_pct: number;
  avg_win_margin?: number | null;
  avg_challenger_score?: number | null;
  avg_king_score?: number | null;
  required_win_margin?: number | null;
  binary_scoring_duels?: number;
  reign: AlbedoReignMember[];
  current_king?: AlbedoReignMember | null;
  current_eval?: AlbedoCurrentEval | null;
  queue_length: number;
  king_history: AlbedoKingCoronation[];
  king_tenures: AlbedoKingTenure[];
  reign_slot_holders: AlbedoReignSlotHolder[];
  repo_crown_analysis: AlbedoRepoCrownAnalysis;
  crowns_by_repo: AlbedoCrownLeaderboardRow[];
  crowns_by_coldkey: AlbedoCrownLeaderboardRow[];
  recent_duels: AlbedoDuelSummary[];
  challenger_by_namespace: AlbedoWinRateRow[];
  challenger_by_hotkey: AlbedoWinRateRow[];
  challenger_by_repo: AlbedoWinRateRow[];
  king_defense_by_model: AlbedoWinRateRow[];
  judge_aggregates: AlbedoJudgeAggregate[];
  judge_details: AlbedoJudgeDetail[];
  judge_consensus: AlbedoJudgeConsensus[];
  judge_analytics: AlbedoJudgeAnalytics;
  metric_aggregates: AlbedoMetricAggregate[];
  margin_histogram: AlbedoMarginBucket[];
  timeline: AlbedoTimelinePoint[];
  pipeline: AlbedoPipelineStage[];
  miner_lookup_coverage_pct?: number | null;
  repo_submission_stats: AlbedoRepoSubmissionStats[];
  note: string;
}

import { fetchWithCache, invalidateApiCache } from "@/lib/apiCache";

async function fetchApiRaw<T>(path: string): Promise<T> {
  const url = `${apiBase()}${path}`;
  const maxAttempts = typeof window === "undefined" ? 3 : 1;
  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const res = await fetch(url, { cache: "no-store" });
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
    } catch (error) {
      lastError = error;
      if (attempt < maxAttempts) {
        await new Promise((r) => setTimeout(r, attempt * 500));
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

async function fetchApi<T>(path: string, opts?: { forceRefresh?: boolean }): Promise<T> {
  if (typeof window === "undefined") {
    return fetchApiRaw<T>(path);
  }
  return fetchWithCache(path, () => fetchApiRaw<T>(path), opts);
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
  getIncentiveOverview: (subnet = DEFAULT_SUBNET, limit = 30, live = false) =>
    fetchApi<IncentiveOverview>(
      `/incentives?subnet=${subnet}&limit=${limit}${live ? "&live=true" : ""}`
    ),
  getMarketOverview: (subnet = DEFAULT_SUBNET, forceRefresh = false) =>
    fetchApi<MarketOverview>(`/market/overview?subnet=${subnet}`, { forceRefresh }),
  getRepoActivityOverview: (subnet = DEFAULT_SUBNET, forceRefresh = false) =>
    fetchApi<RepoActivityOverview>(`/repo-activity/overview?subnet=${subnet}`, { forceRefresh }),
  getRepoTracks: (subnet = DEFAULT_SUBNET, family?: string, inSync?: boolean, forceRefresh = false) => {
    const params = new URLSearchParams({ subnet: String(subnet) });
    if (family) params.set("family", family);
    if (inSync !== undefined) params.set("in_sync", String(inSync));
    return fetchApi<RepoTrackEntry[]>(`/repo-activity/repos?${params}`, { forceRefresh });
  },
  getRepoActivityFeed: (
    subnet = DEFAULT_SUBNET,
    opts?: { family?: string; eventType?: string; limit?: number; forceRefresh?: boolean }
  ) => {
    const params = new URLSearchParams({ subnet: String(subnet) });
    if (opts?.family) params.set("family", opts.family);
    if (opts?.eventType) params.set("event_type", opts.eventType);
    if (opts?.limit) params.set("limit", String(opts.limit));
    return fetchApi<RepoActivityEvent[]>(`/repo-activity/feed?${params}`, {
      forceRefresh: opts?.forceRefresh,
    });
  },
  getHippiusLatestRepos: (limit = 10, forceRefresh = false) =>
    fetchApi<HippiusLatestResponse>(`/repo-activity/hippius-latest?limit=${limit}`, {
      forceRefresh,
    }),
  syncRepoActivity: async (subnet = DEFAULT_SUBNET) => {
    const res = await fetch(`${apiBase()}/repo-activity/sync?subnet=${subnet}`, {
      method: "POST",
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`sync failed: HTTP ${res.status}`);
    }
    invalidateApiCache("/repo-activity");
    return res.json() as Promise<Record<string, unknown>>;
  },
  getAlbedoAnalysis: (subnet = DEFAULT_SUBNET, forceRefresh = false) =>
    fetchApi<AlbedoAnalysisOverview>(`/albedo/analysis?subnet=${subnet}`, { forceRefresh }),
  getAlbedoEvalQueue: (subnet = DEFAULT_SUBNET, forceRefresh = false, failLimit = 100) =>
    fetchApi<AlbedoEvalQueueOverview>(
      `/albedo/eval-queue?subnet=${subnet}&fail_limit=${failLimit}`,
      { forceRefresh }
    ),
  getAlbedoLiveDuel: (subnet = DEFAULT_SUBNET, forceRefresh = false) =>
    fetchApi<AlbedoLiveDuel>(`/albedo/live-duel?subnet=${subnet}`, { forceRefresh }),
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
