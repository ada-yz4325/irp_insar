"""
Stage 2 (follow-up) — record which swath(s)/burst(s) a completed ISCE2
stack actually resolved to, given the declared subset in
configs/burst_subset.yaml.

stackSentinel.py has no native --burst-index flag in this ISCE2 version;
burst-level restriction happens implicitly via swathNum + the common
footprint overlap across the stack (or an explicit -b/--bbox clip). This
script inspects the real reference/IW*/burst_*.xml outputs after the
stack has been built and writes the resolved burst count/indices to
metadata/resolved_burst_subset.yaml, so the declared config and the
actual outcome are both on record.

Usage:
    python record_burst_subset.py --work-dir <isce2 workDir> --out metadata/resolved_burst_subset.yaml
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


def find_resolved_bursts(reference_dir: Path) -> dict:
    swaths = {}
    for swath_dir in sorted(reference_dir.glob("IW*")):
        if not swath_dir.is_dir():
            continue
        bursts = sorted(p.stem for p in swath_dir.glob("burst_*.slc.xml"))
        if bursts:
            swaths[swath_dir.name] = bursts
    return swaths


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", required=True, help="ISCE2 stack workDir (contains reference/)")
    ap.add_argument("--out", required=True, help="Output resolved_burst_subset.yaml path")
    args = ap.parse_args()

    reference_dir = Path(args.work_dir) / "reference"
    if not reference_dir.is_dir():
        sys.exit(f"No reference/ directory found under {args.work_dir} -- has the stack run yet?")

    swaths = find_resolved_bursts(reference_dir)
    if not swaths:
        sys.exit(f"No burst_*.slc.xml files found under {reference_dir} -- stack may have failed early")

    total_bursts = sum(len(b) for b in swaths.values())
    record = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "work_dir": str(args.work_dir),
        "resolved_swaths": list(swaths.keys()),
        "resolved_bursts_per_swath": {k: len(v) for k, v in swaths.items()},
        "total_bursts": total_bursts,
        "burst_names_per_swath": swaths,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        yaml.safe_dump(record, f, sort_keys=False)

    print(
        f"OK: resolved {total_bursts} burst(s) across swath(s) {list(swaths.keys())}. "
        f"Wrote {out_path}"
    )


if __name__ == "__main__":
    main()
