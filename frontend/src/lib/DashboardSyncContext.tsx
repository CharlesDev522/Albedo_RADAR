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
  type IncentiveOverview,
  type Registry,
  type SlotStatusData,
  type SyncStatus,
} from "@/lib/api";
import { getSubnetProfile } from "@/lib/subnets";
import type { DashboardView } from "@/lib/subnets";
import { usePageVisibility } from "@/lib/usePageVisibility";
import { useSubnet } from "@/lib/useSubnet";

const LIVE_URL = "/api/v1/live/stream";
export const DASHBOARD_POLL_MS = 3000;
/** Clusters use the same cadence as the main dashboard (was 8s — felt stale). */
export const CLUSTERS_POLL_MS = DASHBOARD_POLL_MS;
const SYNC_POLL_MS = 15_000;
const SUBNET_EXTRAS_POLL_MS = 12_000;

export interface LiveEvent {
  type: string;
  subnet?: number;
  uid?: number;
  hotkey?: string;
  coldkey?: string;
  repo?: string;
  digest?: string;
  version?: string;
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
  liveStatus: "connecting" | "live" | "polling" | "idle";
  flashUids: Set<number>;
  feed: LiveEvent[];
  incentiveOverview: IncentiveOverview | null;
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
  initialSlotData?: SlotStatusData | null;
  initialSyncStatus?: SyncStatus | null;
}

function corePollMs(view: DashboardView): number | null {
  if (view === "dashboard") return DASHBOARD_POLL_MS;
  if (view === "clusters") return CLUSTERS_POLL_MS;
  return null;
}

export function DashboardSyncProvider({
  children,
  initialStats = null,
  initialCommits = [],
  initialSlotData = null,
  initialSyncStatus = null,
}: DashboardSyncProviderProps) {
  const { subnet, view } = useSubnet();
  const pageVisible = usePageVisibility();
  const [stats, setStats] = useState<CommitmentStats | null>(initialStats);
  const [commits, setCommits] = useState<Commitment[]>(initialCommits);
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus | null>(initialSyncStatus);
  const [slotData, setSlotData] = useState<SlotStatusData | null>(initialSlotData);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(
    initialCommits.length > 0 || initialSlotData ? new Date() : null
  );
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [loading, setLoading] = useState(!initialCommits.length && !initialSlotData);
  const [apiError, setApiError] = useState<string | null>(null);
  const [liveStatus, setLiveStatus] = useState<"connecting" | "live" | "polling" | "idle">("idle");
  const [flashUids, setFlashUids] = useState<Set<number>>(new Set());
  const [feed, setFeed] = useState<LiveEvent[]>([]);
  const [incentiveOverview, setIncentiveOverview] = useState<IncentiveOverview | null>(null);

  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const knownUids = useRef<Set<number>>(
    new Set(initialCommits.map((c) => c.uid).filter((u): u is number => u != null))
  );
  const subnetRef = useRef(subnet);
  const viewRef = useRef(view);
  const refreshInFlight = useRef(false);
  const refreshQueued = useRef(false);
  const hydratedRef = useRef(initialCommits.length > 0 || !!initialSlotData);

  const flash = useCallback((uid: number | undefined) => {
    if (uid == null) return;
    setFlashUids((prev) => new Set(prev).add(uid));
    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlashUids(new Set()), 6000);
  }, []);

  const applyCommits = useCallback(
    (rows: Commitment[]) => {
      for (const row of rows) {
        if (row.uid != null && !knownUids.current.has(row.uid)) {
          flash(row.uid);
        }
      }
      knownUids.current = new Set(
        rows.map((row) => row.uid).filter((u): u is number => u != null)
      );
      setCommits(rows);
    },
    [flash]
  );

  const refreshCore = useCallback(async () => {
    if (refreshInFlight.current) {
      refreshQueued.current = true;
      return;
    }
    refreshInFlight.current = true;

    const fetchSubnet = subnet;
    const activeView = viewRef.current;
    const t0 = performance.now();
    try {
      if (activeView === "dashboard") {
        const [s, c, slots] = await Promise.all([
          api.getStats(fetchSubnet),
          api.getCommitments(fetchSubnet),
          api.getSlotStatus(fetchSubnet, "all", "uid_asc", false),
        ]);
        if (subnetRef.current !== fetchSubnet || viewRef.current !== activeView) return;

        setStats(s);
        applyCommits(c.commitments);
        setSlotData(slots);
      } else if (activeView === "clusters") {
        const [s, c, r, slots] = await Promise.all([
          api.getStats(fetchSubnet),
          api.getCommitments(fetchSubnet),
          api.getRegistry(fetchSubnet),
          api.getSlotStatus(fetchSubnet, "all", "uid_asc", false),
        ]);
        if (subnetRef.current !== fetchSubnet || viewRef.current !== activeView) return;

        setStats(s);
        applyCommits(c.commitments);
        setRegistry(r);
        setSlotData(slots);
      } else {
        return;
      }

      setLastRefresh(new Date());
      setLatencyMs(Math.round(performance.now() - t0));
      setApiError(null);
    } catch (err) {
      if (subnetRef.current !== fetchSubnet) return;
      setLiveStatus(activeView === "dashboard" ? "polling" : "idle");
      setApiError(err instanceof Error ? err.message : "API unreachable");
    } finally {
      refreshInFlight.current = false;
      if (subnetRef.current === fetchSubnet) setLoading(false);
      if (refreshQueued.current) {
        refreshQueued.current = false;
        void refreshCore();
      }
    }
  }, [subnet, applyCommits]);

  const refreshSync = useCallback(async () => {
    if (viewRef.current !== "dashboard" && viewRef.current !== "clusters") return;

    const fetchSubnet = subnet;
    try {
      const sync = await api.getSyncStatus(fetchSubnet, false);
      if (subnetRef.current === fetchSubnet) setSyncStatus(sync);
    } catch {
      /* sync metadata is non-critical */
    }
  }, [subnet]);

  const refreshSubnetExtras = useCallback(async () => {
    if (viewRef.current !== "dashboard") return;

    const profile = getSubnetProfile(subnet);
    const fetchSubnet = subnet;

    if (!profile.features.incentiveColumn) {
      setIncentiveOverview(null);
      return;
    }

    try {
      const incentives = await api.getIncentiveOverview(fetchSubnet, 30, false);
      if (subnetRef.current === fetchSubnet) setIncentiveOverview(incentives);
    } catch {
      /* subnet extras are non-critical */
    }
  }, [subnet]);

  const refresh = useCallback(async () => {
    await Promise.all([refreshCore(), refreshSync(), refreshSubnetExtras()]);
  }, [refreshCore, refreshSync, refreshSubnetExtras]);

  useEffect(() => {
    subnetRef.current = subnet;
    viewRef.current = view;
  }, [subnet, view]);

  useEffect(() => {
    subnetRef.current = subnet;
    setStats(null);
    setCommits([]);
    setRegistry(null);
    setSyncStatus(null);
    setSlotData(null);
    setFeed([]);
    setIncentiveOverview(null);
    setApiError(null);
    setLoading(true);
    knownUids.current = new Set();
    hydratedRef.current = false;
  }, [subnet]);

  useEffect(() => {
    if (!pageVisible) return;

    const pollMs = corePollMs(view);
    if (pollMs == null) {
      setLiveStatus("idle");
      return;
    }

    if (hydratedRef.current) {
      hydratedRef.current = false;
      if (view === "dashboard") void refreshSync();
      else void refreshCore();
    } else {
      void refresh();
    }

    const interval = setInterval(refreshCore, pollMs);
    const syncInterval =
      view === "dashboard" || view === "clusters"
        ? setInterval(refreshSync, SYNC_POLL_MS)
        : null;
    const extrasInterval =
      view === "dashboard" ? setInterval(refreshSubnetExtras, SUBNET_EXTRAS_POLL_MS) : null;

    return () => {
      clearInterval(interval);
      if (syncInterval) clearInterval(syncInterval);
      if (extrasInterval) clearInterval(extrasInterval);
    };
  }, [pageVisible, view, refresh, refreshCore, refreshSync, refreshSubnetExtras]);

  useEffect(() => {
    const usesLiveStream = view === "dashboard" || view === "clusters";
    if (!pageVisible || !usesLiveStream) {
      if (view !== "dashboard" && view !== "clusters") setLiveStatus("idle");
      return;
    }

    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      es = new EventSource(`${LIVE_URL}?subnet=${subnet}`);
      setLiveStatus(view === "dashboard" ? "connecting" : "live");

      es.addEventListener("connected", () => setLiveStatus("live"));
      es.addEventListener("commit", (e) => {
        try {
          const data: LiveEvent = JSON.parse(e.data);
          if (data.subnet != null && data.subnet !== subnet) return;
          if (view === "dashboard") {
            setFeed((prev) => [data, ...prev].slice(0, 30));
          }
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
  }, [subnet, flash, refreshCore, pageVisible, view]);

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
        incentiveOverview,
        refresh,
      }}
    >
      {children}
    </DashboardSyncContext.Provider>
  );
}
