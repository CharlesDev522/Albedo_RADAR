"use client";

export default function SortableTh({
  label,
  direction,
  onClick,
  className = "",
}: {
  label: string;
  direction: "asc" | "desc" | null;
  onClick: () => void;
  className?: string;
}) {
  return (
    <th className={className}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-0.5 hover:text-zinc-200 transition-colors ${
          direction ? "text-zinc-200" : "text-zinc-500"
        }`}
      >
        {label}
        <span className="text-[8px] opacity-70">{direction === "asc" ? "↑" : direction === "desc" ? "↓" : "↕"}</span>
      </button>
    </th>
  );
}
