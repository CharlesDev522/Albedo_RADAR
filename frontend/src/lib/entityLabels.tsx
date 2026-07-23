import { shortAddr, shortRepo, modelLinkFromUri } from "@/lib/api";
import { hostBadgeLabel, inferRepoHostFromModelUri } from "@/lib/modelHub";
import { repoOwner } from "@/lib/minerGroups";

/** HF account / namespace (e.g. foremost, jusua) — not the model repo slug. */
export function minerAccountLabel(opts: {
  namespace?: string | null;
  repo?: string | null;
  modelName?: string | null;
}): string {
  if (opts.namespace?.trim()) return opts.namespace.trim();
  const owner = repoOwner(opts.repo);
  if (owner) return owner;
  if (opts.modelName) return shortRepo(opts.modelName, 28);
  return "—";
}

/** Secondary model slug for tooltips / subtitles. */
export function minerModelSlug(opts: {
  modelName?: string | null;
  repo?: string | null;
}): string | null {
  if (opts.modelName?.trim()) return shortRepo(opts.modelName, 36);
  if (opts.repo?.trim()) {
    const slash = opts.repo.indexOf("/");
    return slash >= 0 ? shortRepo(opts.repo.slice(slash + 1), 36) : shortRepo(opts.repo, 36);
  }
  return null;
}

/** Primary repo name with coldkey hint — matches clusters / backend label format. */
export function EntityNameCell({
  label,
  repo,
  coldkey,
  coldkeys,
  repos,
  modelUri,
  title,
}: {
  label?: string | null;
  repo?: string | null;
  coldkey?: string | null;
  coldkeys?: string[];
  repos?: string[];
  modelUri?: string | null;
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
  const hubUrl = modelUri ? modelLinkFromUri(modelUri) : null;
  const host = modelUri ? inferRepoHostFromModelUri(modelUri) : null;
  const tip = title ?? [repoName, ck, host ? hostBadgeLabel(host) : null, ...(repos ?? []), ...(coldkeys ?? [])]
    .filter(Boolean)
    .join(" · ");

  const nameBody = (
    <>
      {repoName && ck ? (
        <>
          <span className="text-zinc-200">{shortRepo(repoName, 32)}</span>
          <span className="text-zinc-500 ml-1 mono text-[9px]">({shortAddr(ck, 6)})</span>
        </>
      ) : repoName ? (
        <span className="text-zinc-200">{shortRepo(repoName, 34)}</span>
      ) : ck ? (
        <span className="text-zinc-400 mono">{shortAddr(ck, 10)}</span>
      ) : (
        <span className="text-zinc-600">—</span>
      )}
      {host && (
        <span
          className={`ml-1.5 text-[8px] uppercase tracking-wide px-1 py-0.5 rounded border ${
            host === "huggingface"
              ? "text-orange-300 border-orange-500/30 bg-orange-500/10"
              : "text-sky-300 border-sky-500/30 bg-sky-500/10"
          }`}
        >
          {hostBadgeLabel(host)}
        </span>
      )}
    </>
  );

  if (hubUrl && repoName) {
    return (
      <a href={hubUrl} target="_blank" rel="noreferrer" className="hover:underline" title={tip}>
        {nameBody}
      </a>
    );
  }

  if (repoName && ck) {
    return <span title={tip}>{nameBody}</span>;
  }
  if (repoName) {
    return (
      <span title={tip}>
        {nameBody}
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
