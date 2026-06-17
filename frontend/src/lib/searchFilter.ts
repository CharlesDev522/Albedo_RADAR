/** Client-side text search helpers for dashboard tables and lists. */

export function normalizeSearchQuery(query: string): string {
  return query.trim().toLowerCase();
}

export function isSearchActive(query: string): boolean {
  return normalizeSearchQuery(query).length > 0;
}

function haystack(...parts: (string | number | null | undefined)[]): string {
  return parts
    .filter((p) => p != null && String(p).length > 0)
    .map((p) => String(p).toLowerCase())
    .join(" ");
}

/** Match uid (exact if query is numeric), hotkey, coldkey, repo, and other string fields. */
export function matchesMinerFields(
  query: string,
  fields: {
    uid?: number | null;
    hotkey?: string | null;
    coldkey?: string | null;
    repo?: string | null;
    digest?: string | null;
    modelUri?: string | null;
    version?: string | null;
    commitmentType?: string | null;
    detail?: string | null;
  }
): boolean {
  const q = normalizeSearchQuery(query);
  if (!q) return true;

  if (/^\d+$/.test(q) && fields.uid != null && String(fields.uid) === q) {
    return true;
  }

  return haystack(
    fields.uid,
    fields.hotkey,
    fields.coldkey,
    fields.repo,
    fields.digest,
    fields.modelUri,
    fields.version,
    fields.commitmentType,
    fields.detail
  ).includes(q);
}

export function matchesGroup(
  query: string,
  group: { label: string; key: string; miners: { uid: number; hotkey: string; coldkey: string; repo: string | null }[] }
): boolean {
  const q = normalizeSearchQuery(query);
  if (!q) return true;

  if (group.label.toLowerCase().includes(q) || group.key.toLowerCase().includes(q)) {
    return true;
  }

  return group.miners.some((m) =>
    matchesMinerFields(q, {
      uid: m.uid,
      hotkey: m.hotkey,
      coldkey: m.coldkey,
      repo: m.repo,
    })
  );
}
