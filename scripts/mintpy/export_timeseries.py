"""
Export MintPy timeseries.h5 to a pixel-indexed CSV for forecasting.

Usage:
    python export_timeseries.py \
        --ts  ../../data/mintpy_outputs/timeseries.h5 \
        --coh ../../data/mintpy_outputs/temporalCoherence.h5 \
        --out ../../data/processed/timeseries.csv \
        --min-coh 0.7
"""

import argparse
import numpy as np
import pandas as pd
import h5py
from pathlib import Path


def load_timeseries(ts_path: str, coh_path: str, min_coh: float):
    with h5py.File(ts_path, "r") as f:
        dates = [d.decode() for d in f["date"][:]]
        ts = f["timeseries"][:]          # (n_dates, rows, cols) in metres

    with h5py.File(coh_path, "r") as f:
        coh = f["temporalCoherence"][:]  # (rows, cols)

    mask = coh >= min_coh
    rows, cols = np.where(mask)

    records = []
    for r, c in zip(rows, cols):
        pixel_ts = ts[:, r, c] * 1000    # m → mm
        for date, val in zip(dates, pixel_ts):
            records.append({"row": r, "col": c, "date": date, "displacement_mm": val})

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ts",      required=True)
    parser.add_argument("--coh",     required=True)
    parser.add_argument("--out",     required=True)
    parser.add_argument("--min-coh", type=float, default=0.7)
    args = parser.parse_args()

    print(f"Loading time series from {args.ts}")
    df = load_timeseries(args.ts, args.coh, args.min_coh)
    print(f"Pixels after coherence mask: {df['row'].nunique() * 0 + len(df) // len(df['date'].unique())}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Saved → {args.out}  ({len(df)} rows)")


if __name__ == "__main__":
    main()
