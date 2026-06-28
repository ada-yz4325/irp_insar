"""
Stage 10 — PS-like stable-pixel mask.

MintPy is fundamentally an SBAS-style time-series processor, not a
StaMPS-style amplitude-dispersion PS-InSAR algorithm. Per the task spec,
the goal here is narrower: restrict the SBAS analysis to quality-screened
urban scatterers using the quality metrics MintPy already computes, plus
the per-pair unwrap reliability built in Stage 7 and the shadow/layover
geometry from Stage 8. Criteria combined (all AND'd):
  - average spatial coherence  >= --min-avg-coh   (from avgSpatialCoh.h5)
  - temporal coherence         >= --min-temp-coh  (from temporalCoherence.h5)
  - non-shadow / non-layover                      (from geometryRadar.h5)
  - per-pixel unwrap reliability >= --min-unwrap-valid-fraction, if Stage 7's
    isce2/unwrap_mask/*.mask files are available (optional -- skipped with a
    warning otherwise)
No water mask criterion: not produced by this stack (see check_geometry.py).

Usage:
    python build_ps_like_mask.py --mintpy-dir <dir> [--isce-work-dir <dir>]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from mintpy.utils import readfile, writefile


def load_unwrap_valid_fraction(isce_work_dir: str, shape: tuple):
    mask_dir = Path(isce_work_dir) / "unwrap_mask"
    if not mask_dir.is_dir():
        return None
    files = sorted(mask_dir.glob("*.mask"))
    if not files:
        return None

    acc = np.zeros(shape, dtype=np.float64)
    n = 0
    for f in files:
        arr = np.fromfile(f, dtype=np.uint8)
        if arr.size != shape[0] * shape[1]:
            continue
        acc += arr.reshape(shape)
        n += 1
    return acc / n if n else None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mintpy-dir", required=True, help="MintPy work dir")
    ap.add_argument(
        "--isce-work-dir", default=None,
        help="ISCE2 workDir (for Stage 7 unwrap masks); criterion skipped if omitted",
    )
    ap.add_argument("--min-avg-coh", type=float, default=0.7)
    ap.add_argument("--min-temp-coh", type=float, default=0.7)
    ap.add_argument("--min-unwrap-valid-fraction", type=float, default=0.7)
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    avg_coh_file = mintpy_dir / "avgSpatialCoh.h5"
    temp_coh_file = mintpy_dir / "temporalCoherence.h5"
    geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"

    for f in (avg_coh_file, temp_coh_file):
        if not f.exists():
            sys.exit(f"Missing {f} -- has invert_network (Stage 12) finished yet?")

    avg_coh, atr = readfile.read(str(avg_coh_file))
    temp_coh, _ = readfile.read(str(temp_coh_file))

    mask_avg = avg_coh >= args.min_avg_coh
    mask_temp = temp_coh >= args.min_temp_coh
    mask_ps_like = mask_avg & mask_temp

    if geom_file.exists():
        shadow, _ = readfile.read(str(geom_file), datasetName="shadowMask")
        mask_ps_like &= (shadow == 0)
    else:
        print("WARNING: no geometryRadar.h5 -- skipping shadow/layover exclusion", file=sys.stderr)

    if args.isce_work_dir:
        valid_frac = load_unwrap_valid_fraction(args.isce_work_dir, avg_coh.shape)
        if valid_frac is not None:
            mask_ps_like &= (valid_frac >= args.min_unwrap_valid_fraction)
        else:
            print(
                "WARNING: no per-pair unwrap masks found under "
                f"{args.isce_work_dir}/unwrap_mask -- skipping unwrap-reliability criterion",
                file=sys.stderr,
            )

    masks_dir = mintpy_dir / "masks"
    masks_dir.mkdir(parents=True, exist_ok=True)

    def save(name, arr):
        out_atr = dict(atr)
        out_atr["FILE_TYPE"] = "mask"
        writefile.write(arr, out_file=str(masks_dir / name), metadata=out_atr)

    save("mask_avg_coherence.h5", mask_avg)
    save("mask_temporal_coherence.h5", mask_temp)
    save("mask_ps_like.h5", mask_ps_like)

    n_valid = int(mask_ps_like.sum())
    frac = n_valid / mask_ps_like.size
    print(f"OK: PS-like mask has {n_valid}/{mask_ps_like.size} valid pixels ({frac:.2%}). Wrote to {masks_dir}")
    if frac < 0.001:
        print("WARNING: <0.1% valid pixels -- thresholds may be too strict for this AOI", file=sys.stderr)


if __name__ == "__main__":
    main()
