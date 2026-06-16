"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  api,
  type Commitment,
  type CommitmentStats,
  type Registry,
  type SlotStatusData,
  type SyncStatus,
} from "@/lib/api";
import { useSubnet } from "@/lib/useSubnet";

const LIVE_URL = "/api/v1/live/stream";
export const DASHBOARD_POLL_MS = 3000;
const SYNC_POLL_MS = 30_000;

export interface LiveEvent {
  type: string;
  subnet?: number;
  uid?: number;
  hotkey?: string;
  coldkey?: string;
  repo?: string;
  model_uri?: string;
  commit_block?: number;
  registered_at_block?: number;
  timestamp?: string;
}

interface DashboardSyncContextValue {
  stats: CommitmentStats | null;
  commits: Commitment[];
  registry: Registry | null;
  syncStatus: SyncStatus | null;
  slotData: SlotStatusData | null;
  lastRefresh: Date | null;
  latencyMs: number | null;
  loading: boolean;
  apiError: string | null;
  liveStatus: "connecting" | "live" | "polling";
  flashUids: Set<number>;
  feed: LiveEvent[];
  refresh: () => Promise<void>;
}

const DashboardSyncContext = createContext<DashboardSyncContextValue | null>(null);

export function useDashboardSync(): DashboardSyncContextValue {
  const ctx = useContext(DashboardSyncContext);
  if (!ctx) {
    throw new Error("useDashboardSync must be used within DashboardSyncProvider");
  }
  return ctx;
}

interface DashboardSyncProviderProps {
  children: ReactNode;
  initialStats?: CommitmentStats | null;
  initialCommits?: Commitment[];
  initialRegistry?: Registry | null;
  initialSlotData?: SlotStatusData | null;
  initialSyncStatus?: SyncStatus | null;
}

export function DashboardSyncProvider({
  children,
  initialStats = null,
  initialCommits = [],
  initialRegistry = null,
  initialSlotData = null,
  initialSyncStatus = null,
}: DashboardSyncProviderProps) {
  const { subnet } = useSubnet();
  const [stats, setStats] = useState<CommitmentStats | null>(initialStats);
  const [commits, setCommits] = useState<Commitment[]>(initialCommits);
  const [registry, setRegistry] = useState<Registry | null>(initialRegistry);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(initialSyncStatus);
  const [slotData, setSlotData] = useState<SlotStatusData | null>(initialSlotData);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(
    initialCommits.length > 0 || initialSlotData ? new Date() : null
  );
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(!initialCommits.length && !initialSlotData);
  const [apiError, setApiError] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<"connecting" | "live" | "polling">("connecting");
  const [flashUids, setFlashUids] = useState<Set<number>>(new Set());
  const [feed, setFeed] = useState<LiveEvent[]>([]);

  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const knownUids = useRef<Set<number>>(
    new Set(initialCommits.map((c) => c.uid).filter((u): u is number => u != null))
  );
  const subnetRef = useRef(subnet);
  const refreshInFlight = useRef(false);
  const refreshQueued = useRef(false);
  const hydratedRef = useRef(initialCommits.length > 0 || !!initialSlotData);

  const flash = useCallback((uid: number | undefined) => {
    if (uid == null) return;
    setFlashUids((prev) => new Set(prev).add(uid));
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlashUids(new Set()), 6000);
  }, []);

  const refreshCore = useCallback(async () => {
    if (refreshInFlight.current) {
      refreshQueued.current = true;
      return;
    }
    refreshInFlight.current = true;

    const fetchSubnet = subnet;
    const t0 = performance.now();
    try {
      const [s, c, r, slots] = await Promise.all([
        api.getStats(fetchSubnet),
        api.getCommitments(fetchSubnet),
        api.getRegistry(fetchSubnet),
        api.getSlotStatus(fetchSubnet, "all", "uid_asc", false),
      ]);
      if (subnetRef.current !== fetchSubnet) return;

      for (const row of c.commitments) {
        if (row.uid != null && !knownUids.current.has(row.uid)) {
          flash(row.uid);
        }
      }
      knownUids.current = new Set(
        c.commitments.map((row) => row.uid).filter((u): u is number => u != null)
      );

      setStats(s);
      setCommits(c.commitments);
      setRegistry(r);
      setSlotData(slots);
      setLastRefresh(new Date());
      setLatencyMs(Math.round(performance.now() - t0));
      setApiError(null);
    } catch (err) {
      if (subnetRef.current !== fetchSubnet) return;
      setLiveStatus("polling");
      setApiError(err instanceof Error ? err.message : "API unreachable");
    } finally {
      refreshInFlight.current = false;
      if (subnetRef.current === fetchSubnet) setLoading(false);
      if (refreshQueued.current) {
        refreshQueued.current = false;
        void refreshCore();
      }
    }
  }, [subnet, flash]);

  const refreshSync = useCallback(async () => {
    const fetchSubnet = subnet;
    try {
      const sync = await api.getSyncStatus(fetchSubnet, false);
      if (subnetRef.current === fetchSubnet) setSyncStatus(sync);
    } catch {
      /* sync metadata is non-critical */
    }
  }, [subnet]);

  const refresh = useCallback(async () => {
    await Promise.all([refreshCore(), refreshSync()]);
  }, [refreshCore, refreshSync]);

  useEffect(() => {
    subnetRef.current = subnet;
    setStats(null);
    setCommits([]);
    setRegistry(null);
    setSyncStatus(null);
    setSlotData(null);
    setFeed([]);
    setApiError(null);
    setLoading(true);
    knownUids.current = new Set();
    hydratedRef.current = false;
  }, [subnet]);

  useEffect(() => {
    if (hydratedRef.current) {
      hydratedRef.current = false;
      void refreshSync();
    } else {
      void refresh();
    }
    const interval = setInterval(refreshCore, DASHBOARD_POLL_MS);
    const syncInterval = setInterval(refreshSync, SYNC_POLL_MS);
    return () => {
      clearInterval(interval);
      clearInterval(syncInterval);
    };
  }, [refresh, refreshCore, refreshSync]);

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      es = new EventSource(`${LIVE_URL}?subnet=${subnet}`);
      setLiveStatus("connecting");

      es.addEventListener("connected", () => setLiveStatus("live"));
      es.addEventListener("commit", (e) => {
        try {
          const data: LiveEvent = JSON.parse(e.data);
          if (data.subnet != null && data.subnet !== subnet) return;
          setFeed((prev) => [data, ...prev].slice(0, 30));
          flash(data.uid);
          void refreshCore();
        } catch {
          /* ignore */
        }
      });
      es.addEventListener("ping", () => setLiveStatus("live"));
      es.onerror = () => {
        setLiveStatus("polling");
        es?.close();
        retryTimer = setTimeout(connect, 2000);
      };
    };

    connect();
    return () => {
      es?.close();
      clearTimeout(retryTimer);
    };
  }, [subnet, flash, refreshCore]);

  return (
    <DashboardSyncContext.Provider
      value={{
        stats,
        commits,
        registry,
        syncStatus,
        slotData,
        lastRefresh,
        latencyMs,
        loading,
        apiError,
        liveStatus,
        flashUids,
        feed,
        refresh,
      }}
    >
      {children}
    </DashboardSyncContext.Provider>
  );
}
