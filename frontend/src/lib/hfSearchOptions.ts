export type HfSortKey = "createdAt" | "lastModified" | "downloads" | "likes";

export const HF_SORT_OPTIONS: { key: HfSortKey; label: string }[] = [
  { key: "createdAt", label: "Recently created" },
  { key: "lastModified", label: "Recently updated" },
  { key: "downloads", label: "Most downloads" },
  { key: "likes", label: "Most likes" },
];

export const HF_DEFAULT_TAG_OPTIONS = [
  "safetensors",
  "qwen3_5_moe",
  "transformers",
  "pytorch",
] as const;

export function hfSortLabel(key: string): string {
  return HF_SORT_OPTIONS.find((opt) => opt.key === key)?.label ?? key;
}

export function toggleTagSelection(tags: string[], tag: string): string[] {
  const normalized = tag.toLowerCase();
  const has = tags.some((t) => t.toLowerCase() === normalized);
  if (has) return tags.filter((t) => t.toLowerCase() !== normalized);
  return [...tags, tag];
}

export function hfSortMetricLabel(sort: HfSortKey): string {
  switch (sort) {
    case "lastModified":
      return "updated";
    case "downloads":
      return "downloads";
    case "likes":
      return "likes";
    default:
      return "created";
  }
}
