"""
Stage 14 — export PS-like stable-pixel locations to exports/ps_like_points.geojson.

Each point carries its radar-coordinate (row, col), lat/lon (from
geometryRadar.h5) and mean vertical velocity / velocity uncertainty
(mm/yr, from velocity_vertical.h5 / velocity_std_vertical.h5 -- see
scripts/mintpy/project_los_to_vertical.py) as properties, restricted to
Stage 10's mask_ps_like.h5.

Usage:
    python export_ps_points_geojson.py --mintpy-dir <dir> --out exports/ps_like_points.geojson
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from mintpy.utils import readfile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mintpy-dir", required=True, help="MintPy work dir")
    ap.add_argument("--out", required=True, help="Output .geojson path")
    ap.add_argument("--mask", default=None,
                    help="PS mask HDF5 (default: <mintpy-dir>/masks/mask_ps_like.h5)")
    ap.add_argument(
        "--max-points", type=int, default=None,
        help="Optional cap on number of points written (evenly subsampled)",
    )
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    mask_file = Path(args.mask) if args.mask else mintpy_dir / "masks" / "mask_ps_like.h5"
    geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"
    velocity_file = mintpy_dir / "velocity_vertical.h5"
    std_file = mintpy_dir / "velocity_std_vertical.h5"

    for f in (mask_file, geom_file, velocity_file):
        if not f.exists():
            sys.exit(f"Missing required file: {f}")

    mask, _ = readfile.read(str(mask_file))
    lat, _ = readfile.read(str(geom_file), datasetName="latitude")
    lon, _ = readfile.read(str(geom_file), datasetName="longitude")
    vel, _ = readfile.read(str(velocity_file), datasetName="velocity")  # m/yr
    vel_std = None
    if std_file.exists():
        vel_std, _ = readfile.read(str(std_file))  # m/yr

    rows, cols = np.where(mask)
    if args.max_points and len(rows) > args.max_points:
        idx = np.linspace(0, len(rows) - 1, args.max_points).astype(int)
        rows, cols = rows[idx], cols[idx]

    features = []
    for r, c in zip(rows, cols):
        props = {
            "row": int(r),
            "col": int(c),
            "velocity_mm_yr": float(vel[r, c]) * 1000.0,
        }
        if vel_std is not None:
            props["velocity_std_mm_yr"] = float(vel_std[r, c]) * 1000.0
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon[r, c]), float(lat[r, c])]},
            "properties": props,
        })

    geojson = {"type": "FeatureCollection", "features": features}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(geojson, f)

    print(f"OK: wrote {len(features)} PS-like point(s) to {out_path}")


if __name__ == "__main__":
    main()
