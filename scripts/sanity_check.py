#!/usr/bin/env python3
"""
sanity_check.py — parquet cache sanity check + manifest bookkeeping.

Reads row counts (from parquet metadata, not full file) for each of the
three cache parquets and compares against a JSON manifest of previous
counts. Fails if any count shifts by more than TOLERANCE (default 20%).

Intended use:

    # Verify current caches against stored manifest (non-destructive):
    sanity_check.py verify <app_dir> <manifest_path>

    # After a known-good refresh, update the manifest:
    sanity_check.py update <app_dir> <manifest_path>

Exit codes:
    0 — OK (or manifest updated)
    1 — FAIL (mismatch / missing files / unreadable parquet)
    2 — usage error

Emits a single JSON line to stdout with the current counts, so callers
can pipe it into a log or status file.
"""

import glob
import json
import os
import sys

try:
    import pyarrow.parquet as pq
except ImportError as exc:
    print(f'FAIL: pyarrow not importable ({exc})', file=sys.stderr)
    sys.exit(1)


CACHE_PREFIXES = ['neo_cache', 'apparition_cache', 'boxscore_cache']
TOLERANCE = 0.20  # 20% — plenty of slack for genuine daily growth/shrinkage


def current_counts(app_dir: str) -> dict:
    """Read row count from the newest parquet matching each cache prefix."""
    counts = {}
    for prefix in CACHE_PREFIXES:
        matches = glob.glob(os.path.join(app_dir, f'.{prefix}_*.parquet'))
        if not matches:
            raise RuntimeError(f'no files matching .{prefix}_*.parquet in {app_dir}')
        latest = max(matches, key=os.path.getmtime)
        counts[prefix] = pq.ParquetFile(latest).metadata.num_rows
    return counts


def load_manifest(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as fp:
        return json.load(fp)


def save_manifest(path: str, counts: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fp:
        json.dump(counts, fp, indent=2)
        fp.write('\n')


def verify(counts: dict, manifest: dict) -> list[str]:
    """Return list of human-readable problems; empty list means OK."""
    problems = []
    for prefix, n in counts.items():
        prior = manifest.get(prefix)
        if prior is None:
            # First run — no baseline to compare against; accept whatever.
            continue
        if prior <= 0:
            problems.append(f'{prefix}: prior manifest value {prior} is invalid')
            continue
        ratio = abs(n - prior) / prior
        if ratio > TOLERANCE:
            direction = 'grew' if n > prior else 'shrank'
            problems.append(
                f'{prefix}: rows {direction} from {prior:,} to {n:,} '
                f'({ratio * 100:.1f}% change, tolerance {TOLERANCE * 100:.0f}%)'
            )
    return problems


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in ('verify', 'update'):
        print(__doc__, file=sys.stderr)
        return 2
    mode, app_dir, manifest_path = sys.argv[1:]

    try:
        counts = current_counts(app_dir)
    except Exception as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1

    if mode == 'verify':
        problems = verify(counts, load_manifest(manifest_path))
        print(json.dumps(counts))
        if problems:
            for p in problems:
                print(f'FAIL: {p}', file=sys.stderr)
            return 1
        return 0

    # mode == 'update'
    save_manifest(manifest_path, counts)
    print(json.dumps(counts))
    return 0


if __name__ == '__main__':
    sys.exit(main())
