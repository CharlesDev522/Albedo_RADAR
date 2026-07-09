#!/usr/bin/env python3
"""Deduplicate dual-zero JSONL exports by sample_id.

Keeps the first record for each sample_id and drops later duplicates.
Use this after manually concatenating per-duel JSONL files, or to re-run
deduplication on an existing combined dataset.

Example:
  python dedup_dual_zero_jsonl.py combined.jsonl -o combined.dedup.jsonl
  python dedup_dual_zero_jsonl.py duel-a.jsonl duel-b.jsonl -o dataset.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def dedupe_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    removed = 0
    for record in records:
        sample_id = str(record.get("sample_id") or "")
        if sample_id and sample_id in seen:
            removed += 1
            continue
        if sample_id:
            seen.add(sample_id)
        unique.append(record)
    return unique, removed


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        records.append(obj)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [json.dumps(record, ensure_ascii=False) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deduplicate dual-zero JSONL files by sample_id (first record wins)."
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="Input JSONL file(s)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output JSONL path",
    )
    args = parser.parse_args(argv)

    combined: list[dict[str, Any]] = []
    for input_path in args.inputs:
        if not input_path.is_file():
            print(f"error: file not found: {input_path}", file=sys.stderr)
            return 1
        combined.extend(load_jsonl(input_path))

    unique, removed = dedupe_records(combined)
    write_jsonl(args.output, unique)

    print(
        f"Wrote {len(unique)} unique samples to {args.output} "
        f"(input lines={len(combined)}, duplicates_removed={removed})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
