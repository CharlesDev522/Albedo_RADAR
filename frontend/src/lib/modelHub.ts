/** Dual Hippius / Hugging Face model URI parsing and hub browse URLs. */

export type RepoHost = "hippius" | "huggingface";

const HIPPIUS_DIGEST_RE = /^sha256:[0-9a-f]{64}$/i;
const HF_GIT_SHA_RE = /^[0-9a-f]{40}$/i;
const HF_GIT_SHA256_RE = /^[0-9a-f]{64}$/i;

export function parseModelRepo(uri: string | null | undefined): string | null {
  if (!uri) return null;
  let s = uri.replace(/^[a-z][a-z0-9+.-]*:\/\//i, "");
  s = s.replace(/@[^/]*$/, "");
  const slash = s.indexOf("/");
  if (slash > 0 && s.slice(0, slash).includes(".")) {
    s = s.slice(slash + 1);
  }
  const repo = s.trim();
  return repo && repo.includes("/") ? repo : null;
}

export function digestFromModelUri(uri: string | null | undefined): string | null {
  if (!uri || !uri.includes("@")) return null;
  return uri.split("@").pop()?.trim() || null;
}

export function inferRepoHostFromDigest(digest: string | null | undefined): RepoHost {
  const d = (digest || "").trim().toLowerCase();
  if (!d) return "hippius";
  if (d.startsWith("revision:") || d.startsWith("hf:")) return "huggingface";
  if (HIPPIUS_DIGEST_RE.test(d)) return "hippius";
  if (HF_GIT_SHA_RE.test(d) || HF_GIT_SHA256_RE.test(d)) return "huggingface";
  return "hippius";
}

export function inferRepoHostFromModelUri(uri: string | null | undefined): RepoHost {
  return inferRepoHostFromDigest(digestFromModelUri(uri));
}

export function isHfModelUri(uri: string | null | undefined): boolean {
  if (!uri) return false;
  if (uri.startsWith("hf://")) return true;
  return inferRepoHostFromModelUri(uri) === "huggingface";
}

export function hippiusModelUrl(repo: string, branch = "main"): string {
  const clean = repo.replace(/^\/+|\/+$/g, "");
  return `https://hub.hippius.com/models/${clean}/${branch}`;
}

export function hfModelUrl(repo: string, digest?: string | null): string {
  const clean = repo.replace(/^\/+|\/+$/g, "");
  if (digest?.startsWith("revision:")) {
    return `https://huggingface.co/${clean}/tree/${digest.slice("revision:".length)}`;
  }
  if (digest?.startsWith("hf:")) {
    return `https://huggingface.co/${clean}/tree/${digest.slice("hf:".length)}`;
  }
  if (digest && (HF_GIT_SHA_RE.test(digest) || HF_GIT_SHA256_RE.test(digest))) {
    return `https://huggingface.co/${clean}/tree/${digest}`;
  }
  if (digest) return `https://huggingface.co/${clean}/tree/${digest}`;
  return `https://huggingface.co/${clean}`;
}

export function hubRepoUrl(uri: string | null | undefined): string | null {
  const repo = parseModelRepo(uri);
  if (!repo) return null;
  if (isHfModelUri(uri)) return hfModelUrl(repo, digestFromModelUri(uri));
  return hippiusModelUrl(repo);
}

export function modelLinkFromUri(modelUri: string | null | undefined): string | null {
  return hubRepoUrl(modelUri);
}

export function hostBadgeLabel(host: RepoHost): string {
  return host === "huggingface" ? "HF" : "hippius";
}
