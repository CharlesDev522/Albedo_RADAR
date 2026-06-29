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
    modelFamily?: string | null;
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
    fields.detail,
    fields.modelFamily
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

/** Match repo activity track rows (repos table). */
export function matchesRepoTrack(
  query: string,
  track: {
    uid?: number | null;
    hotkey?: string | null;
    coldkey?: string | null;
    repo?: string | null;
    chain_digest?: string | null;
    hub_digest?: string | null;
    model_family?: string | null;
    repo_host?: string | null;
    track_source?: string | null;
    hub_commit_message?: string | null;
  }
): boolean {
  const q = normalizeSearchQuery(query);
  if (!q) return true;

  return matchesMinerFields(q, {
    uid: track.uid,
    hotkey: track.hotkey,
    coldkey: track.coldkey,
    repo: track.repo,
    digest: track.chain_digest ?? track.hub_digest,
    modelFamily: track.model_family,
  }) ||
    haystack(
      track.repo_host,
      track.track_source,
      track.hub_commit_message,
      track.chain_digest,
      track.hub_digest
    ).includes(q);
}

/** Match repo activity feed events. */
export function matchesRepoActivityEvent(
  query: string,
  event: {
    uid?: number | null;
    hotkey?: string | null;
    coldkey?: string | null;
    repo?: string | null;
    chain_digest?: string | null;
    hub_digest?: string | null;
    model_family?: string | null;
    event_type?: string | null;
    commit_message?: string | null;
  }
): boolean {
  const q = normalizeSearchQuery(query);
  if (!q) return true;

  return (
    matchesMinerFields(q, {
      uid: event.uid,
      hotkey: event.hotkey,
      coldkey: event.coldkey,
      repo: event.repo,
      digest: event.chain_digest ?? event.hub_digest,
      modelFamily: event.model_family,
    }) ||
    haystack(
      event.event_type,
      event.commit_message,
      event.chain_digest,
      event.hub_digest
    ).includes(q)
  );
}
