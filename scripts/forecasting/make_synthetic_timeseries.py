"""
Generate a synthetic pixel-wise displacement time series CSV that mimics
the real output of export_timeseries.py, for developing and stress-testing
forecasting models before MintPy produces real data.

Schema (matches export_timeseries.py exactly):
    row, col, date, displacement_mm

Pixel archetypes generated (mixed into one CSV, identifiable by `row`):
    row 0      — stable ground (near-zero trend, small noise)
    row 1      — steady linear subsidence (e.g. -15 mm/yr)
    row 2      — steady linear uplift (e.g. +8 mm/yr)
    row 3      — seasonal signal only (annual cycle, no trend)
    row 4      — trend + seasonal + noise (the realistic combined case)
    row 5      — noisy / low-coherence pixel (large noise, occasional NaN gaps)
    row 6      — pixel with an unwrapping-error outlier (sudden jump)

Usage:
    python make_synthetic_timeseries.py --out ../../data/processed/synthetic_timeseries.csv \
        --start 2020-06-20 --n-dates 46 --interval-days 12
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def make_dates(start: str, n_dates: int, interval_days: int) -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n_dates, freq=f"{interval_days}D")


def gen_pixel_series(dates: pd.DatetimeIndex, archetype: str, rng: np.random.Generator) -> np.ndarray:
    t_years = (dates - dates[0]).days.values / 365.25
    n = len(dates)

    if archetype == "stable":
        return rng.normal(0, 2.0, n)

    if archetype == "subsidence":
        return -15.0 * t_years + rng.normal(0, 3.0, n)

    if archetype == "uplift":
        return 8.0 * t_years + rng.normal(0, 3.0, n)

    if archetype == "seasonal":
        return 5.0 * np.sin(2 * np.pi * t_years) + rng.normal(0, 2.0, n)

    if archetype == "combined":
        return (-10.0 * t_years + 4.0 * np.sin(2 * np.pi * t_years)
                + rng.normal(0, 2.5, n))

    if archetype == "noisy":
        series = rng.normal(0, 8.0, n)
        # simulate a few missing acquisitions (failed coherence/unwrapping)
        gap_idx = rng.choice(n, size=max(1, n // 10), replace=False)
        series[gap_idx] = np.nan
        return series

    if archetype == "outlier":
        series = -5.0 * t_years + rng.normal(0, 2.0, n)
        jump_idx = rng.integers(n // 3, 2 * n // 3)
        series[jump_idx:] += 40.0  # simulated unwrapping-error jump
        return series

    raise ValueError(f"Unknown archetype: {archetype}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--start", default="2020-06-20")
    parser.add_argument("--n-dates", type=int, default=46)
    parser.add_argument("--interval-days", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    dates = make_dates(args.start, args.n_dates, args.interval_days)

    archetypes = ["stable", "subsidence", "uplift", "seasonal", "combined", "noisy", "outlier"]
    records = []
    for row, archetype in enumerate(archetypes):
        series = gen_pixel_series(dates, archetype, rng)
        for date, val in zip(dates, series):
            records.append({
                "row": row, "col": 0, "date": date.strftime("%Y%m%d"),
                "displacement_mm": val,
            })

    df = pd.DataFrame(records)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    print(f"Saved synthetic time series → {out_path}")
    print(f"  {len(archetypes)} pixels (rows 0-{len(archetypes)-1}) × {args.n_dates} dates")
    print(f"  Archetypes: {dict(enumerate(archetypes))}")


if __name__ == "__main__":
    main()
