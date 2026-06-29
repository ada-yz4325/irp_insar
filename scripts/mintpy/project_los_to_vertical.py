#!/usr/bin/env python3
"""Stage 12/13 extension — project LOS displacement/velocity to vertical.

InSAR measures displacement along the satellite-target line of sight (LOS),
not vertical ground motion. This stack is single-geometry (ascending only),
so a true horizontal/vertical decomposition (which needs both ascending and
descending looks, e.g. mintpy.cli.asc_desc2horz_vert) isn't possible. Instead
this applies the standard single-geometry approximation: assume horizontal
motion is negligible and project the LOS value onto vertical using the local
incidence angle.

    vertical = LOS / cos(incidence_angle)

Sign convention matches MintPy's own asc_desc2horz_vert.py: positive LOS
means motion toward the satellite. Dividing by cos(incidence_angle) (always
positive for real incidence angles) preserves sign, so positive vertical =
uplift, negative = subsidence.

Writes *_vertical.h5 companions next to the LOS originals, preserving every
other dataset/attribute unchanged (so they remain readable by MintPy's own
view.py/save_gdal.py etc).

Usage:
    python project_los_to_vertical.py --mintpy-dir data/mintpy_outputs
"""
import argparse
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np
from mintpy.utils import readfile

# (input filename, output filename, dataset names to project, is_timeseries)
# Runs right after the `velocity` dostep, before Stage 13's
# export_velocity_products.py -- velocity_std.h5 doesn't exist yet at this
# point in the pipeline (export_velocity_products.py derives it from
# velocity_vertical.h5's already-projected 'velocityStd' dataset instead of
# needing a separate LOS-domain std file projected here).
TARGETS = [
    ("timeseries.h5", "timeseries_vertical.h5", ["timeseries"], True),
    ("velocity.h5", "velocity_vertical.h5", ["velocity", "velocityStd"], False),
]


def project_file(in_path: Path, out_path: Path, dataset_names: list, cos_inc: np.ndarray):
    shutil.copy(in_path, out_path)
    with h5py.File(out_path, "r+") as f:
        for name in dataset_names:
            if name not in f:
                continue
            data = f[name][:]
            f[name][...] = data / cos_inc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mintpy-dir", required=True)
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"
    if not geom_file.exists():
        sys.exit(f"Missing {geom_file}")

    inc_deg, _ = readfile.read(str(geom_file), datasetName="incidenceAngle")
    cos_inc_2d = np.cos(np.deg2rad(inc_deg)).astype(np.float32)
    cos_inc_2d[np.abs(cos_inc_2d) < 1e-3] = np.nan
    print(f"incidence angle: {np.nanmin(inc_deg):.2f}-{np.nanmax(inc_deg):.2f} deg, "
          f"vertical/LOS scale factor: {np.nanmin(1/cos_inc_2d):.3f}-{np.nanmax(1/cos_inc_2d):.3f}")

    for in_name, out_name, dsets, is_timeseries in TARGETS:
        in_path = mintpy_dir / in_name
        if not in_path.exists():
            print(f"WARNING: {in_path} not found, skipping", file=sys.stderr)
            continue
        out_path = mintpy_dir / out_name
        cos_b = cos_inc_2d[np.newaxis, :, :] if is_timeseries else cos_inc_2d
        project_file(in_path, out_path, dsets, cos_b)
        print(f"Wrote {out_path} (projected: {dsets})")


if __name__ == "__main__":
    main()
