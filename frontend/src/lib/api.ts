const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface Miner {
  id: number;
  uid: number;
  hotkey: string;
  coldkey: string;
  subnet: number;
  status: string;
  is_validator: boolean;
  current_stake: number;
  current_emission: number;
  current_incentive: number;
  current_rank: number;
  rank_position: number | null;
  first_seen: string;
  last_seen: string;
}

export interface LeaderboardEntry {
  rank: number;
  miner_id: number;
  uid: number;
  hotkey: string;
  coldkey: string;
  value: number;
}

export interface Leaderboard {
  category: string;
  subnet: number;
  entries: LeaderboardEntry[];
  updated_at: string;
}

export interface Event {
  id: number;
  event_type: string;
  subnet: number;
  block: number | null;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface SubnetStats {
  subnet: number;
  block: number;
  neuron_count: number;
  active_miners: number;
  active_validators: number;
  total_stake: number;
  total_emission: number;
  last_updated: string;
}

async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { next: { revalidate: 30 } });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  getMiners: (subnet = 1) => fetchApi<{ miners: Miner[]; total: number }>(`/miners?subnet=${subnet}&limit=50`),
  getLeaderboard: (category: string, subnet = 1) =>
    fetchApi<Leaderboard>(`/leaderboards/${category}?subnet=${subnet}&limit=10`),
  getEvents: (subnet = 1) => fetchApi<{ events: Event[] }>(`/events?subnet=${subnet}&limit=20`),
  getRegistrations: (subnet = 1) => fetchApi<{ events: Event[] }>(`/events/registrations?subnet=${subnet}`),
  getSubnetStats: (subnet = 1) => fetchApi<SubnetStats>(`/subnets/${subnet}/stats`),
  getClusters: (subnet = 1) =>
    fetchApi<Array<{ coldkey: string; miner_count: number; total_stake: number }>>(
      `/coldkeys/clusters?subnet=${subnet}&min_miners=2`
    ),
};

export function truncateAddress(addr: string, chars = 6): string {
  if (addr.length <= chars * 2 + 3) return addr;
  return `${addr.slice(0, chars)}...${addr.slice(-chars)}`;
}

export function formatNumber(n: number, decimals = 4): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(2)}K`;
  return n.toFixed(decimals);
}
