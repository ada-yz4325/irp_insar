"""
Stage 13 — velocity uncertainty export + GeoTIFF, in vertical deformation.

MintPy's own `velocity` dostep produces velocity.h5 (LOS, both 'velocity'
and 'velocityStd' datasets -- smallbaselineApp's --uq default is "residue",
Fattahi & Amelung 2015). scripts/mintpy/project_los_to_vertical.py runs
right after that dostep and projects it to velocity_vertical.h5 (single-
geometry vertical approximation, see that script's docstring). This script
does the parts the report needs that smallbaselineApp doesn't already
produce as separate, mask-applied files, all in the vertical domain:

  1. extracts 'velocityStd' into its own PS-like-masked
     velocity_std_vertical.h5
  2. geocodes velocity_vertical.h5 and mask_ps_like.h5 (neither is part of
     MintPy's own geocode dostep file list, which only knows about the
     original LOS velocity.h5)
  3. exports a PS-masked, geocoded velocity.tif (GeoTIFF) of vertical
     deformation rate

Usage:
    python export_velocity_products.py --mintpy-dir <dir> --out-dir exports
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from mintpy.utils import readfile, writefile


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mintpy-dir", required=True, help="MintPy work dir")
    ap.add_argument("--out-dir", required=True, help="exports/ directory for velocity.tif")
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    velocity_file = mintpy_dir / "velocity_vertical.h5"
    mask_file = mintpy_dir / "masks" / "mask_ps_like.h5"
    geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"
    geo_dir = mintpy_dir / "geo"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for f in (velocity_file, mask_file, geom_file):
        if not f.exists():
            sys.exit(f"Missing required file: {f} -- has project_los_to_vertical.py run yet?")

    # --- velocity_std_vertical.h5: extract + PS-like mask ---
    std, atr = readfile.read(str(velocity_file), datasetName="velocityStd")
    mask, _ = readfile.read(str(mask_file))
    std_masked = np.where(mask, std, np.nan).astype(np.float32)

    std_atr = dict(atr)
    std_atr["FILE_TYPE"] = "velocity"
    std_out = mintpy_dir / "velocity_std_vertical.h5"
    writefile.write(std_masked, out_file=str(std_out), metadata=std_atr)
    print(f"Wrote {std_out}")

    # --- geocode velocity_vertical.h5 + the PS-like mask (not in MintPy's
    # own geocode dostep file list) so they line up spatially ---
    geo_dir.mkdir(exist_ok=True)
    import mintpy.cli.geocode as geocode

    geo_velocity = geo_dir / "geo_velocity_vertical.h5"
    if not geo_velocity.exists():
        geocode.main([str(velocity_file), "-l", str(geom_file), "--outdir", str(geo_dir)])

    geo_mask = geo_dir / "geo_mask_ps_like.h5"
    if not geo_mask.exists():
        geocode.main([str(mask_file), "-l", str(geom_file), "--outdir", str(geo_dir)])

    # --- GeoTIFF export, PS-masked, vertical deformation rate ---
    import mintpy.cli.save_gdal as save_gdal
    tif_out = out_dir / "velocity.tif"
    save_gdal.main([
        str(geo_velocity), "-d", "velocity", "-m", str(geo_mask),
        "-o", str(tif_out), "--of", "GTiff",
    ])
    print(f"Wrote {tif_out}")


if __name__ == "__main__":
    main()
