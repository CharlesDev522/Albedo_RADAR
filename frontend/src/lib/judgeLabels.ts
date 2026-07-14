/** Normalize GLM 5.1 / 5.2 (and future) to one duel-table column. */

export function normalizeJudgeColumnKey(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return trimmed;
  if (trimmed.toLowerCase().startsWith("glm")) return "glm";
  return trimmed;
}

export function judgeShortFromModel(judge: string): string {
  const slash = judge.lastIndexOf("/");
  const tail = slash >= 0 ? judge.slice(slash + 1) : judge;
  return normalizeJudgeColumnKey(tail);
}

export function judgeColumnHeader(name: string): string {
  if (name === "glm" || name.toLowerCase().startsWith("glm")) return "GLM";
  if (name.startsWith("qwen")) return "Qwen";
  if (name.startsWith("deepseek")) return "DS";
  return name.split("-")[0];
}

export const DEFAULT_JUDGE_COLUMNS = [
  "glm",
  "qwen3.5-397b-a17b",
  "deepseek-v3.2",
] as const;
