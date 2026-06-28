"""
Stage 9 (validation) — verify MintPy's load_data step produced consistent
ifgramStack.h5 / geometryRadar.h5 (Validation Check #9).

Usage:
    python check_mintpy_load.py --mintpy-dir <mintpy work dir>
"""

import argparse
import sys
from pathlib import Path

import h5py

REQUIRED_IFGRAM_DSETS = ["unwrapPhase", "coherence", "connectComponent", "bperp"]
REQUIRED_GEOMETRY_DSETS = ["height", "latitude", "longitude", "incidenceAngle", "azimuthAngle", "shadowMask"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mintpy-dir", required=True, help="MintPy work dir (contains inputs/)")
    args = ap.parse_args()

    inputs_dir = Path(args.mintpy_dir) / "inputs"
    ifgram_path = inputs_dir / "ifgramStack.h5"
    geom_path = inputs_dir / "geometryRadar.h5"

    errors = []
    for path in (ifgram_path, geom_path):
        if not path.exists():
            errors.append(f"missing file: {path}")
    if errors:
        sys.exit("FAIL: " + "; ".join(errors))

    with h5py.File(ifgram_path, "r") as f:
        missing = [d for d in REQUIRED_IFGRAM_DSETS if d not in f]
        if missing:
            errors.append(f"{ifgram_path.name} missing dataset(s): {missing}")
        else:
            n_pairs, n_rows, n_cols = f["unwrapPhase"].shape
            n_dates = len(set(f["date"][:].astype(str).flatten())) if "date" in f else None

    with h5py.File(geom_path, "r") as f:
        missing = [d for d in REQUIRED_GEOMETRY_DSETS if d not in f]
        if missing:
            errors.append(f"{geom_path.name} missing dataset(s): {missing}")
        else:
            geom_rows, geom_cols = f["height"].shape

    if errors:
        sys.exit("FAIL: " + "; ".join(errors))

    if (geom_rows, geom_cols) != (n_rows, n_cols):
        sys.exit(
            f"FAIL: dimension mismatch -- ifgramStack {n_rows}x{n_cols} "
            f"vs geometryRadar {geom_rows}x{geom_cols}"
        )

    print(
        f"OK: ifgramStack.h5 has {n_pairs} pairs over {n_rows}x{n_cols} pixels"
        + (f" ({n_dates} unique dates)" if n_dates else "")
        + f"; geometryRadar.h5 dims match ({geom_rows}x{geom_cols})."
    )


if __name__ == "__main__":
    main()
