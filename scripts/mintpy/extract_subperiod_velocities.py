"""
Extract sub-period velocity GeoTIFFs from a completed MintPy stack.

For each period:
  1. timeseries2velocity   → velocity_<label>.h5  (LOS)
  2. LOS → vertical        → velocity_vertical_<label>.h5
  3. geocode               → geo/geo_velocity_vertical_<label>.h5
  4. save_gdal + PS mask   → exports/velocity_<label>.tif
  5. secondary-ref correct → subtract stable-bedrock median

Usage:
    python extract_subperiod_velocities.py \\
        --mintpy-dir /path/to/mintpy_outputs_iw2_2016_2021 \\
        --mask       mask_ps_psinsar.h5 \\
        --out-dir    exports_beijing_iw2_2016_2021 \\
        --periods 20161003:20191231:2016-2019 \\
                  20200101:20211130:2020-2021 \\
                  20161003:20211130:2016-2021
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np
import rasterio
import rasterio.transform


# --------------------------------------------------------------------------- #
#  LOS → vertical projection (single-geometry approximation)                  #
# --------------------------------------------------------------------------- #

def project_los_to_vertical_file(mintpy_dir: Path, vel_h5: Path, out_h5: Path):
    from mintpy.utils import readfile
    geom = mintpy_dir / 'inputs' / 'geometryRadar.h5'
    inc_deg, _ = readfile.read(str(geom), datasetName='incidenceAngle')
    cos_inc = np.cos(np.deg2rad(inc_deg)).astype(np.float32)
    cos_inc[np.abs(cos_inc) < 1e-3] = np.nan

    shutil.copy2(vel_h5, out_h5)
    with h5py.File(out_h5, 'r+') as f:
        for dset in ('velocity', 'velocityStd'):
            if dset in f:
                f[dset][...] = f[dset][:] / cos_inc
    print(f"  LOS→vertical: {out_h5.name}")


# --------------------------------------------------------------------------- #
#  Secondary reference correction (subtract western-bedrock median)           #
# --------------------------------------------------------------------------- #

def apply_secondary_ref(tif_path: Path,
                        lon0: float, lon1: float,
                        lat0: float, lat1: float) -> float:
    with rasterio.open(tif_path) as src:
        v  = src.read(1).astype(np.float32)
        nd = src.nodata
        tf = src.transform
        profile = src.profile.copy()

    if nd is not None:
        v[v == nd] = np.nan
    v[v == 0] = np.nan

    h, w = v.shape
    ri, ci = np.mgrid[0:h, 0:w]
    xs, ys = rasterio.transform.xy(tf, ri.ravel(), ci.ravel())
    lons = np.array(xs, np.float32).reshape(h, w)
    lats = np.array(ys, np.float32).reshape(h, w)

    m = (lons >= lon0) & (lons <= lon1) & (lats >= lat0) & (lats <= lat1) & np.isfinite(v)
    if not m.any():
        print('  WARNING: no valid pixels in secondary-ref bbox')
        return 0.0

    ref = float(np.median(v[m]))
    print(f"  Ref correction: {ref*1000:.2f} mm/yr  ({m.sum():,} px)")

    v_corr = np.where(np.isfinite(v), v - ref, np.nan).astype(np.float32)
    profile.update(nodata=np.nan, dtype='float32')
    with rasterio.open(tif_path, 'w', **profile) as dst:
        dst.write(v_corr, 1)
    return ref


# --------------------------------------------------------------------------- #
#  Main                                                                        #
# --------------------------------------------------------------------------- #

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mintpy-dir', required=True)
    ap.add_argument('--mask',       required=True,
                    help='PS mask filename (relative to mintpy-dir), e.g. mask_ps_psinsar.h5')
    ap.add_argument('--out-dir',    required=True)
    ap.add_argument('--ref-lon-min', type=float, default=115.6)
    ap.add_argument('--ref-lon-max', type=float, default=116.0)
    ap.add_argument('--ref-lat-min', type=float, default=39.9)
    ap.add_argument('--ref-lat-max', type=float, default=40.1)
    ap.add_argument('--periods', nargs='+', required=True,
                    help='START:END:LABEL, e.g. 20161003:20191231:2016-2019')
    args = ap.parse_args()

    mdir   = Path(args.mintpy_dir)
    odir   = Path(args.out_dir);  odir.mkdir(parents=True, exist_ok=True)
    mask   = mdir / args.mask
    ts     = mdir / 'timeseries_demErr.h5'
    geom   = mdir / 'inputs' / 'geometryRadar.h5'
    geo_d  = mdir / 'geo';  geo_d.mkdir(exist_ok=True)

    for f in (ts, mask, geom):
        if not f.exists():
            sys.exit(f'Required file missing: {f}')

    import mintpy.cli.geocode  as geocode_cli
    import mintpy.cli.save_gdal as save_gdal_cli

    # Geocode PS mask once
    geo_mask = geo_d / ('geo_' + mask.name)
    if not geo_mask.exists():
        print(f'Geocoding PS mask → {geo_mask.name}')
        geocode_cli.main([str(mask), '-l', str(geom), '--outdir', str(geo_d)])

    for spec in args.periods:
        parts = spec.split(':')
        if len(parts) != 3:
            sys.exit(f'Bad period spec "{spec}": need START:END:LABEL')
        start, end, label = parts
        print(f'\n{"="*60}')
        print(f'Period: {label}  ({start} → {end})')
        print('='*60)

        # 1. timeseries2velocity
        vel_los = mdir / f'velocity_{label}.h5'
        if vel_los.exists():
            print(f'  velocity_{label}.h5 already exists — skipping timeseries2velocity')
        else:
            subprocess.run([
                'timeseries2velocity.py', str(ts),
                '--start-date', start, '--end-date', end,
                '--output', str(vel_los),
            ], check=True)

        # 2. LOS → vertical
        vel_vert = mdir / f'velocity_vertical_{label}.h5'
        if vel_vert.exists():
            print(f'  velocity_vertical_{label}.h5 exists — skipping projection')
        else:
            project_los_to_vertical_file(mdir, vel_los, vel_vert)

        # 3. Geocode
        geo_vel = geo_d / f'geo_velocity_vertical_{label}.h5'
        if geo_vel.exists():
            print(f'  {geo_vel.name} exists — skipping geocode')
        else:
            print(f'  Geocoding vertical velocity → {geo_vel.name}')
            geocode_cli.main([str(vel_vert), '-l', str(geom), '--outdir', str(geo_d)])

        # 4. Export GeoTIFF
        tif_out = odir / f'velocity_{label}.tif'
        save_gdal_cli.main([
            str(geo_vel), '-d', 'velocity', '-m', str(geo_mask),
            '-o', str(tif_out), '--of', 'GTiff',
        ])

        # 5. Secondary reference correction
        ref = apply_secondary_ref(
            tif_out,
            args.ref_lon_min, args.ref_lon_max,
            args.ref_lat_min, args.ref_lat_max,
        )
        vm_mm = ref * 1000
        print(f'  Exported + corrected → {tif_out}')

    print('\n=== Sub-period extraction complete ===')


if __name__ == '__main__':
    main()
