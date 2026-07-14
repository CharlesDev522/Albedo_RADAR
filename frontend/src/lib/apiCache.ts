type CacheEntry<T> = {
  data: T;
  fetchedAt: number;
};

const dataCache = new Map<string, CacheEntry<unknown>>();
const inflight = new Map<string, Promise<unknown>>();

/** Path prefix → stale-while-revalidate TTL (client only). */
const SWR_TTL_MS: Record<string, number> = {
  "/albedo/analysis": 25_000,
  "/albedo/eval-queue": 8_000,
  "/albedo/live-duel": 8_000,
  "/repo-activity/overview": 15_000,
  "/repo-activity/repos": 15_000,
  "/repo-activity/feed": 15_000,
  "/repo-activity/hippius-latest": 60_000,
  "/market/overview": 45_000,
};

function swrTtlForPath(path: string): number {
  if (typeof window === "undefined") return 0;
  for (const [prefix, ttl] of Object.entries(SWR_TTL_MS)) {
    if (path.startsWith(prefix)) return ttl;
  }
  return 0;
}

export function invalidateApiCache(prefix?: string): void {
  for (const key of dataCache.keys()) {
    if (!prefix || key.startsWith(prefix)) dataCache.delete(key);
  }
}

export async function fetchWithCache<T>(
  key: string,
  fetcher: () => Promise<T>,
  opts?: { ttlMs?: number; forceRefresh?: boolean }
): Promise<T> {
  const ttlMs = opts?.ttlMs ?? swrTtlForPath(key);
  const now = Date.now();
  const cached = dataCache.get(key) as CacheEntry<T> | undefined;

  if (!opts?.forceRefresh && cached && ttlMs > 0 && now - cached.fetchedAt < ttlMs) {
    return cached.data;
  }

  if (!opts?.forceRefresh && cached && ttlMs > 0) {
    const existing = inflight.get(key);
    if (!existing) {
      const revalidate = fetcher()
        .then((data) => {
          dataCache.set(key, { data, fetchedAt: Date.now() });
          return data;
        })
        .finally(() => inflight.delete(key));
      inflight.set(key, revalidate);
    }
    return cached.data;
  }

  const pending = inflight.get(key);
  if (pending) return pending as Promise<T>;

  const request = fetcher()
    .then((data) => {
      dataCache.set(key, { data, fetchedAt: Date.now() });
      return data;
    })
    .finally(() => inflight.delete(key));

  inflight.set(key, request);
  return request;
}
