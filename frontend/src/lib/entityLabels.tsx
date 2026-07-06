import { shortAddr, shortRepo } from "@/lib/api";

/** Primary repo name with coldkey hint — matches clusters / backend label format. */
export function EntityNameCell({
  label,
  repo,
  coldkey,
  coldkeys,
  repos,
  title,
}: {
  label?: string | null;
  repo?: string | null;
  coldkey?: string | null;
  coldkeys?: string[];
  repos?: string[];
  title?: string;
}) {
  if (label) {
    return (
      <span className="text-zinc-200" title={title ?? label}>
        {label}
      </span>
    );
  }

  const repoName = repo ?? repos?.[0];
  const ck = coldkey ?? (coldkeys?.length === 1 ? coldkeys[0] : null);
  const tip = title ?? [repoName, ck, ...(repos ?? []), ...(coldkeys ?? [])].filter(Boolean).join(" · ");

  if (repoName && ck) {
    return (
      <span title={tip}>
        <span className="text-zinc-200">{shortRepo(repoName, 32)}</span>
        <span className="text-zinc-500 ml-1 mono text-[9px]">({shortAddr(ck, 6)})</span>
      </span>
    );
  }
  if (repoName) {
    return (
      <span className="text-zinc-200" title={tip}>
        {shortRepo(repoName, 34)}
      </span>
    );
  }
  if (ck) {
    return (
      <span className="text-zinc-400 mono" title={tip}>
        {shortAddr(ck, 10)}
      </span>
    );
  }
  return <span className="text-zinc-600">—</span>;
}
