"""
Stage 7 (follow-up) — build a low-quality-unwrap mask per interferogram pair.

ISCE2's topsStack unwrap step (run_16_unwrap, via SNAPHU) writes a
.unw.conncomp connected-component label image alongside each filt_fine.unw:
component 0 marks pixels SNAPHU could not confidently unwrap (isolated /
disconnected regions). This script turns that into an explicit boolean
mask per pair under isce2/unwrap_mask/, and logs unwrap success/failure
per pair to isce2/unwrap_logs/unwrap_summary.csv (Stage 7 outputs 3+4+5).

Usage:
    python build_unwrap_mask.py --work-dir <isce2 workDir>
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "utils"))
from isce_io import read_isce_image  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work-dir", required=True, help="ISCE2 stack workDir")
    args = ap.parse_args()

    work_dir = Path(args.work_dir)
    ifg_dir = work_dir / "merged" / "interferograms"
    if not ifg_dir.is_dir():
        sys.exit(f"No merged/interferograms/ under {work_dir} -- has unwrap (run_16) finished yet?")

    mask_dir = work_dir / "unwrap_mask"
    log_dir = work_dir / "unwrap_logs"
    mask_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for pair_dir in sorted(ifg_dir.iterdir()):
        if not pair_dir.is_dir():
            continue
        conncomp_path = pair_dir / "filt_fine.unw.conncomp"
        unw_path = pair_dir / "filt_fine.unw"

        if not (conncomp_path.with_suffix(conncomp_path.suffix + ".xml")).exists():
            rows.append({"pair": pair_dir.name, "status": "missing_conncomp",
                         "valid_fraction": "", "mask_file": ""})
            continue

        conncomp = read_isce_image(str(conncomp_path))
        valid = conncomp != 0
        valid_fraction = float(valid.mean())

        out_path = mask_dir / f"{pair_dir.name}.mask"
        valid.astype("uint8").tofile(out_path)

        status = "ok" if unw_path.exists() else "unwrap_missing"
        rows.append({
            "pair": pair_dir.name,
            "status": status,
            "valid_fraction": round(valid_fraction, 4),
            "mask_file": str(out_path),
        })

    if not rows:
        sys.exit(f"No interferogram pair directories found under {ifg_dir}")

    summary_path = log_dir / "unwrap_summary.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["pair", "status", "valid_fraction", "mask_file"])
        writer.writeheader()
        writer.writerows(rows)

    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_fail = len(rows) - n_ok
    print(f"OK: {n_ok}/{len(rows)} pairs unwrapped with conncomp masks written to {mask_dir}")
    if n_fail:
        print(f"WARNING: {n_fail} pair(s) missing conncomp/unw output -- see {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
