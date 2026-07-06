"""
Stage 14 — quick-look figures for the urban PS-InSAR pipeline.

Produces:
    figures/velocity_map.png            -- PS-masked mean vertical velocity (mm/yr)
    figures/temporal_coherence.png       -- temporalCoherence.h5
    figures/ps_like_mask.png             -- mask_ps_like.h5
    figures/selected_point_timeseries.png -- vertical displacement history for
                                              a few sample PS-like points

Usage:
    python plot_pipeline_results.py --mintpy-dir <dir> --exports-dir exports --out-dir figures
"""

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mintpy.utils import readfile


def plot_velocity(mintpy_dir: Path, mask: np.ndarray, out_dir: Path):
    vel, _ = readfile.read(str(mintpy_dir / "velocity_vertical.h5"), datasetName="velocity")
    vel_mm = np.where(mask, vel * 1000.0, np.nan)

    vmax = np.nanpercentile(np.abs(vel_mm), 95) if np.isfinite(vel_mm).any() else 1.0
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(vel_mm, cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    plt.colorbar(im, label="Vertical velocity (mm/yr, +up)")
    ax.set_title("PS-like masked mean vertical velocity")
    plt.tight_layout()
    out = out_dir / "velocity_map.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out}")


def plot_temporal_coherence(mintpy_dir: Path, out_dir: Path):
    coh, _ = readfile.read(str(mintpy_dir / "temporalCoherence.h5"))
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(coh, cmap="gray", vmin=0, vmax=1)
    plt.colorbar(im, label="Temporal coherence")
    ax.set_title("Temporal coherence")
    plt.tight_layout()
    out = out_dir / "temporal_coherence.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out}")


def plot_ps_mask(mask: np.ndarray, out_dir: Path):
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(mask, cmap="gray_r", vmin=0, vmax=1)
    plt.colorbar(im, label="PS-like (1=valid)")
    ax.set_title(f"PS-like stable-pixel mask ({mask.sum()}/{mask.size} valid, {mask.mean():.2%})")
    plt.tight_layout()
    out = out_dir / "ps_like_mask.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out}")


def plot_selected_timeseries(exports_dir: Path, out_dir: Path, n_points: int):
    csv_path = exports_dir / "timeseries_points.csv"
    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found -- skipping selected-point time series plot", file=sys.stderr)
        return

    df = pd.read_csv(csv_path)
    if df.empty:
        print(f"WARNING: {csv_path} is empty -- skipping", file=sys.stderr)
        return

    pixels = df[["row", "col"]].drop_duplicates()
    chosen = pixels.sample(n=min(n_points, len(pixels)), random_state=42)

    fig, ax = plt.subplots(figsize=(9, 5))
    for _, (r, c) in chosen.iterrows():
        sub = df[(df["row"] == r) & (df["col"] == c)].sort_values("date")
        ax.plot(pd.to_datetime(sub["date"], format="%Y%m%d"), sub["displacement_mm"],
                marker="o", markersize=3, label=f"({r},{c})")

    ax.set_xlabel("Date")
    ax.set_ylabel("Vertical displacement (mm, +up)")
    ax.set_title(f"Selected PS-like point vertical time series (n={len(chosen)})")
    ax.legend(fontsize=8)
    plt.tight_layout()
    out = out_dir / "selected_point_timeseries.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mintpy-dir", required=True)
    ap.add_argument("--exports-dir", required=True)
    ap.add_argument("--out-dir", default="figures")
    ap.add_argument("--n-points", type=int, default=5)
    ap.add_argument("--mask", default=None,
                    help="PS mask HDF5 (default: <mintpy-dir>/masks/mask_ps_like.h5)")
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    exports_dir = Path(args.exports_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mask_file = Path(args.mask) if args.mask else mintpy_dir / "masks" / "mask_ps_like.h5"
    if not mask_file.exists():
        sys.exit(f"Missing {mask_file} -- has Stage 10 run yet?")
    mask, _ = readfile.read(str(mask_file))
    mask = mask.astype(bool)

    plot_velocity(mintpy_dir, mask, out_dir)
    plot_temporal_coherence(mintpy_dir, out_dir)
    plot_ps_mask(mask, out_dir)
    plot_selected_timeseries(exports_dir, out_dir, args.n_points)


if __name__ == "__main__":
    main()
