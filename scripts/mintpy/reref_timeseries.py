#!/usr/bin/env python3
"""
Re-reference an existing MintPy timeseries.h5 to a new spatial reference pixel
without re-running the full network inversion.

Reads the current timeseries (already ERA5-corrected), subtracts the chosen
reference pixel's displacement history from every pixel epoch-by-epoch (one
slice at a time to keep RAM below ~100 MB), and updates the REF_* metadata.

Usage:
    python reref_timeseries.py \\
        --mintpy-dir /path/to/mintpy_outputs_psinsar \\
        --lat 40.0500 --lon 116.0500
"""
import argparse
import sys
from pathlib import Path

import h5py
import numpy as np


def find_ref_pixel(geom_file: Path, mask_file: Path,
                   ref_lat: float, ref_lon: float):
    """Return (row, col, actual_lat, actual_lon) of nearest coherent pixel."""
    from mintpy.utils import readfile
    lat, _ = readfile.read(str(geom_file), datasetName="latitude")
    lon, _ = readfile.read(str(geom_file), datasetName="longitude")
    with h5py.File(mask_file) as f:
        mask = f["mask"][:].astype(bool)

    dist = np.abs(lat - ref_lat) + np.abs(lon - ref_lon)
    dist[~mask] = np.inf
    if np.isinf(dist.min()):
        sys.exit("No coherent pixels near requested reference location.")

    r, c = np.unravel_index(np.argmin(dist), dist.shape)
    return int(r), int(c), float(lat[r, c]), float(lon[r, c])


def reref_inplace(ts_file: Path, ref_row: int, ref_col: int):
    """
    Subtract reference pixel timeseries from all pixels in-place,
    reading/writing one epoch at a time to limit RAM.
    """
    with h5py.File(ts_file, "r") as f:
        n_dates = f["timeseries"].shape[0]
        ref_ts = f["timeseries"][:, ref_row, ref_col]   # (n_dates,)

    with h5py.File(ts_file, "r+") as f:
        for i in range(n_dates):
            f["timeseries"][i] -= ref_ts[i]
            if (i + 1) % 10 == 0 or i == n_dates - 1:
                print(f"  epoch {i+1:3d}/{n_dates}", flush=True)


def update_ref_metadata(ts_file: Path, ref_row: int, ref_col: int,
                        ref_lat: float, ref_lon: float):
    with h5py.File(ts_file, "r+") as f:
        for k, v in [("REF_Y", ref_row), ("REF_X", ref_col),
                     ("REF_LAT", ref_lat), ("REF_LON", ref_lon)]:
            f.attrs[k] = str(v)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mintpy-dir", required=True)
    ap.add_argument("--lat", type=float, required=True, help="Reference latitude  (°N)")
    ap.add_argument("--lon", type=float, required=True, help="Reference longitude (°E)")
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    ts_file   = mintpy_dir / "timeseries.h5"
    geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"
    mask_file = mintpy_dir / "maskTempCoh.h5"

    for f in (ts_file, geom_file, mask_file):
        if not f.exists():
            sys.exit(f"Missing: {f}")

    print(f"Requested reference : {args.lat:.4f}°N  {args.lon:.4f}°E")
    r, c, act_lat, act_lon = find_ref_pixel(geom_file, mask_file, args.lat, args.lon)
    print(f"Nearest coherent px : row={r}  col={c}  "
          f"({act_lat:.4f}°N  {act_lon:.4f}°E)")

    with h5py.File(ts_file, "r") as f:
        old_ref_lat = f.attrs.get("REF_LAT", "unknown")
        old_ref_lon = f.attrs.get("REF_LON", "unknown")
    print(f"Previous reference  : {old_ref_lat}°N  {old_ref_lon}°E")

    print(f"\nRe-referencing {ts_file.name} ({ts_file.stat().st_size/1e9:.2f} GB) …")
    reref_inplace(ts_file, r, c)
    update_ref_metadata(ts_file, r, c, act_lat, act_lon)
    print(f"\nDone — reference updated to ({act_lat:.4f}°N, {act_lon:.4f}°E)")


if __name__ == "__main__":
    main()
