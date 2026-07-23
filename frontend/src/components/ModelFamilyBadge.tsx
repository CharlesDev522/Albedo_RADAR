/** Small badge for Albedo model competition era. */

import {
  inferAlbedoModelFamily,
  modelFamilyLabel,
  modelFamilyStyle,
  type AlbedoModelFamily,
} from "@/lib/modelFamily";

export function ModelFamilyBadge({
  repo,
  family,
  className = "",
}: {
  repo?: string | null;
  family?: AlbedoModelFamily | string | null;
  className?: string;
}) {
  const resolved = (family as AlbedoModelFamily | null) ?? inferAlbedoModelFamily(repo);
  const label = modelFamilyLabel(resolved);
  if (!label) return null;

  return (
    <span
      className={`inline-flex px-1.5 py-0.5 rounded border text-[8px] uppercase tracking-wide shrink-0 ${modelFamilyStyle(
        resolved
      )} ${className}`}
      title={`Competition era: ${label}`}
    >
      {label}
    </span>
  );
}
