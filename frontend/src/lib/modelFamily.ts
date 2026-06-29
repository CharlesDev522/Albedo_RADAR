/** Albedo SN97 competition era from Hippius repo paths (ahead of public chain.toml). */

export type AlbedoModelFamily = "qwen3.6-35b" | "qwen3-4b";

const QWEN36_35B_CANONICAL = /^[^/]+\/albedo-qwen3\.6-35b(?:-.+)?$/i;
const QWEN3_4B_CANONICAL = /^[^/]+\/albedo-qwen3-4b(?:-.+)?$/i;
const QWEN36_35B_HINT = /qwen3\.6[-_.]?35b|albedo-qwen3\.6/i;
const QWEN3_4B_HINT = /qwen3[-_]4b|albedo-qwen3-4b/i;

export function inferAlbedoModelFamily(repo: string | null | undefined): AlbedoModelFamily | null {
  if (!repo || !repo.includes("/")) return null;
  const text = repo.trim();
  if (QWEN36_35B_CANONICAL.test(text) || QWEN36_35B_HINT.test(text)) return "qwen3.6-35b";
  if (QWEN3_4B_CANONICAL.test(text) || QWEN3_4B_HINT.test(text)) return "qwen3-4b";
  return null;
}

export function modelFamilyLabel(family: AlbedoModelFamily | null | undefined): string | null {
  if (family === "qwen3.6-35b") return "Qwen3.6-35B";
  if (family === "qwen3-4b") return "Qwen3-4B";
  return null;
}

export function modelFamilyStyle(family: AlbedoModelFamily | null | undefined): string {
  if (family === "qwen3.6-35b") {
    return "text-sky-300 border-sky-500/40 bg-sky-500/10";
  }
  if (family === "qwen3-4b") {
    return "text-amber-300 border-amber-500/40 bg-amber-500/10";
  }
  return "text-zinc-500 border-zinc-700 bg-zinc-800/30";
}
