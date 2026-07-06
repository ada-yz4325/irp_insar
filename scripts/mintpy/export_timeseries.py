"""
Stage 14 — export MintPy timeseries.h5 to a pixel-indexed CSV
(exports/timeseries_points.csv) for plotting and forecasting.

Usage:
    python export_timeseries.py \
        --ts  data/mintpy_outputs/timeseries.h5 \
        --coh data/mintpy_outputs/temporalCoherence.h5 \
        --out exports/timeseries_points.csv \
        --min-coh 0.7

    # or restrict to Stage 10's PS-like mask instead of a raw coherence cut:
    python export_timeseries.py \
        --ts   data/mintpy_outputs/timeseries.h5 \
        --mask data/mintpy_outputs/masks/mask_ps_like.h5 \
        --out  exports/timeseries_points.csv
"""

import argparse
from pathlib import Path

import h5py
import numpy as np
import pandas as pd


def load_timeseries(ts_path: str, mask: np.ndarray, max_points: int = 50000):
    rows, cols = np.where(mask)
    n_ps = len(rows)

    if n_ps > max_points:
        rng = np.random.default_rng(42)
        idx = np.sort(rng.choice(n_ps, size=max_points, replace=False))
        rows, cols = rows[idx], cols[idx]
        print(f"  Subsampled {n_ps:,} → {max_points:,} PS points")

    n_ps = len(rows)
    with h5py.File(ts_path, "r") as f:
        dates = [d.decode() for d in f["date"][:]]
        n_dates = len(dates)
        # Read one 2D date slice (~31 MB each) then extract PS pixels;
        # avoids loading the full 1.9 GB array and h5py sorted-index constraint
        ts_ps = np.empty((n_dates, n_ps), dtype=np.float32)
        for i in range(n_dates):
            ts_ps[i] = f["timeseries"][i][rows, cols]

    # Build long-format DataFrame with vectorised ops (no Python dict loop)
    row_rep = np.repeat(rows, n_dates)
    col_rep = np.repeat(cols, n_dates)
    date_rep = np.tile(dates, n_ps)
    disp_flat = (ts_ps.T.ravel() * 1000.0).astype(np.float32)  # m → mm

    return pd.DataFrame({
        "row": row_rep,
        "col": col_rep,
        "date": date_rep,
        "displacement_mm": disp_flat,
    })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ts",      required=True)
    parser.add_argument("--coh",     default=None, help="temporalCoherence.h5 (used if --mask not given)")
    parser.add_argument("--mask",    default=None, help="mask_ps_like.h5 (Stage 10) -- takes priority over --coh/--min-coh")
    parser.add_argument("--out",     required=True)
    parser.add_argument("--min-coh", type=float, default=0.7)
    args = parser.parse_args()

    if args.mask:
        with h5py.File(args.mask, "r") as f:
            mask = f["mask"][:].astype(bool)
        print(f"Using PS-like mask from {args.mask}")
    elif args.coh:
        with h5py.File(args.coh, "r") as f:
            mask = f["temporalCoherence"][:] >= args.min_coh
        print(f"Using temporalCoherence >= {args.min_coh} from {args.coh}")
    else:
        raise SystemExit("Must provide either --mask or --coh")

    print(f"Loading time series from {args.ts}")
    df = load_timeseries(args.ts, mask, max_points=50000)
    n_pixels = df[["row", "col"]].drop_duplicates().shape[0] if len(df) else 0
    print(f"Pixels after mask: {n_pixels}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Saved → {args.out}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
