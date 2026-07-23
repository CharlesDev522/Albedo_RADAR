/**
 * Resolve FastAPI base URL for server-side fetches (SSR + Next route proxy).
 * Browser clients should use relative `/api/v1` (see api.ts).
 */

const DEFAULT_LOCAL = "http://localhost:8000/api/v1";

export function resolveBackendApiV1Base(): string {
  const raw =
    process.env.INTERNAL_API_PROXY ||
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    DEFAULT_LOCAL;
  return raw.replace(/\/$/, "");
}

/** Origin without `/api/v1` suffix — for proxy target construction. */
export function resolveBackendOrigin(): string {
  return resolveBackendApiV1Base().replace(/\/api\/v1\/?$/i, "").replace(/\/$/, "");
}

/** When `api` hostname only works inside Docker, fall back to localhost (local `npm run dev`). */
export function localhostFallbackUrl(url: string): string | null {
  if (!url.includes("://api:") && !url.includes("://api/")) {
    return null;
  }
  return url.replace("://api:", "://localhost:").replace("://api/", "://localhost/");
}
