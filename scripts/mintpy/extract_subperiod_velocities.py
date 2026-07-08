"""
Extract sub-period velocity GeoTIFFs from a completed MintPy stack.

For each period:
  1. timeseries2velocity   → velocity_<label>.h5  (LOS)
  2. LOS → vertical        → velocity_vertical_<label>.h5
  3. Geocode               → geo/geo_velocity_vertical_<label>.h5
  4. Per-period combined mask (PS + DS-relaxed + std filter)
  5. save_gdal + masked export → exports/velocity_<label>.tif
  6. Secondary-ref correction → subtract stable-bedrock median

DS mode (--ds-thr > 0):
  Pixels with temporal coherence >= --ds-thr are added to the PS mask,
  subject to velocity uncertainty <= --std-max mm/yr.
  With 117 scenes/5 years, TC=0.60–0.72 pixels have median std 0.68 mm/yr
  (better than PS median 0.80 mm/yr), so including them is safe.

Usage:
    python extract_subperiod_velocities.py \\
        --mintpy-dir /path/to/mintpy_outputs_iw2_2016_2021 \\
        --mask       mask_ps_psinsar.h5 \\
        --out-dir    exports_beijing_iw2_2016_2021 \\
        --ds-thr     0.60 \\
        --periods 20161003:20191231:2016-2019:6 \\
                  20200101:20211130:2020-2021:20 \\
                  20161003:20211130:2016-2021:5
    (The 4th colon-field is the per-period std-max in mm/yr.)
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


# ─────────────────────────────────────────────────────────────────
#  LOS → vertical projection
# ─────────────────────────────────────────────────────────────────

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
    print(f'  LOS→vertical: {out_h5.name}')


# ─────────────────────────────────────────────────────────────────
#  Build per-period combined mask (PS + DS + std filter)
# ─────────────────────────────────────────────────────────────────

def build_combined_mask(mintpy_dir: Path,
                        ps_mask_file: Path,
                        vel_vert_h5: Path,
                        label: str,
                        ds_thr: float,
                        std_max_mm: float) -> Path:
    """
    Return path to combined mask HDF5 (created if needed).
    mask = (PS_mask) | (TC >= ds_thr AND std_vert <= std_max_mm)
    """
    combined = mintpy_dir / f'mask_combined_{label}.h5'
    if combined.exists():
        print(f'  Combined mask already exists: {combined.name}')
        return combined

    from mintpy.utils import readfile, writefile

    # Load PS mask
    ps, atr = readfile.read(str(ps_mask_file))
    ps = ps.astype(bool)

    # Load temporal coherence
    tc_file = mintpy_dir / 'temporalCoherence.h5'
    tc, _ = readfile.read(str(tc_file))

    # Load vertical velocity std
    std_mask = np.zeros_like(ps)
    with h5py.File(vel_vert_h5, 'r') as h:
        if 'velocityStd' in h:
            vstd_vert = h['velocityStd'][:] * 1000.0  # → mm/yr
            std_mask = np.isfinite(vstd_vert) & (vstd_vert <= std_max_mm)
        else:
            std_mask = np.ones_like(ps)

    # DS pixels: TC >= threshold, std OK, but NOT already in PS
    ds_mask = (tc >= ds_thr) & std_mask

    # Combined: PS union DS
    combined_mask = (ps | ds_mask).astype(np.uint8)
    n_ps   = ps.sum()
    n_ds   = (ds_mask & ~ps).sum()
    n_tot  = combined_mask.sum()
    print(f'  Mask stats — PS: {n_ps:,}  DS-added: {n_ds:,}  total: {n_tot:,}')

    writefile.write(combined_mask, out_file=str(combined), metadata=atr)
    return combined


# ─────────────────────────────────────────────────────────────────
#  Secondary reference correction
# ─────────────────────────────────────────────────────────────────

def apply_secondary_ref(tif_path: Path,
                        lon0: float, lon1: float,
                        lat0: float, lat1: float) -> float:
    with rasterio.open(tif_path) as src:
        v   = src.read(1).astype(np.float32)
        nd  = src.nodata
        tf  = src.transform
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

    # Robust reference: inter-quartile median (clip at IQR tails)
    ref_vals = v[m] * 1000.0   # mm/yr
    q25, q75 = np.percentile(ref_vals, 25), np.percentile(ref_vals, 75)
    iqr = q75 - q25
    inliers = m & (v * 1000 >= q25 - 1.5 * iqr) & (v * 1000 <= q75 + 1.5 * iqr)
    ref_mm = float(np.median(v[inliers] * 1000.0)) if inliers.any() else float(np.median(ref_vals))
    print(f'  Ref correction: {ref_mm:.2f} mm/yr  ({inliers.sum():,} inlier px / {m.sum():,} total)')

    ref_m = ref_mm / 1000.0
    v_corr = np.where(np.isfinite(v), v - ref_m, np.nan).astype(np.float32)
    profile.update(nodata=np.nan, dtype='float32')
    with rasterio.open(tif_path, 'w', **profile) as dst:
        dst.write(v_corr, 1)
    return ref_mm


# ─────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mintpy-dir', required=True)
    ap.add_argument('--mask',       required=True,
                    help='PS mask filename (relative to mintpy-dir), e.g. mask_ps_psinsar.h5')
    ap.add_argument('--out-dir',    required=True)
    ap.add_argument('--ds-thr',     type=float, default=0.60,
                    help='Temporal coherence threshold for DS-like pixels (default 0.60). '
                         'Set to 0 to use PS-only mask.')
    ap.add_argument('--ref-lon-min', type=float, default=115.6)
    ap.add_argument('--ref-lon-max', type=float, default=116.0)
    ap.add_argument('--ref-lat-min', type=float, default=39.9)
    ap.add_argument('--ref-lat-max', type=float, default=40.1)
    ap.add_argument('--periods', nargs='+', required=True,
                    help='START:END:LABEL[:STD_MAX_MM], e.g. 20161003:20191231:2016-2019:6  '
                         'STD_MAX_MM is the per-period velocity uncertainty cap (mm/yr).')
    args = ap.parse_args()

    mdir  = Path(args.mintpy_dir)
    odir  = Path(args.out_dir);  odir.mkdir(parents=True, exist_ok=True)
    mask  = mdir / args.mask
    ts    = mdir / 'timeseries_demErr.h5'
    geom  = mdir / 'inputs' / 'geometryRadar.h5'
    geo_d = mdir / 'geo';  geo_d.mkdir(exist_ok=True)

    for f in (ts, mask, geom):
        if not f.exists():
            sys.exit(f'Required file missing: {f}')

    import mintpy.cli.geocode   as geocode_cli
    import mintpy.cli.save_gdal as save_gdal_cli

    for spec in args.periods:
        parts = spec.split(':')
        if len(parts) < 3:
            sys.exit(f'Bad period spec "{spec}": need at least START:END:LABEL')
        start, end, label = parts[0], parts[1], parts[2]
        std_max_mm = float(parts[3]) if len(parts) >= 4 else 10.0
        print(f'\n{"="*60}')
        print(f'Period: {label}  ({start} → {end})  std_max={std_max_mm} mm/yr')
        print('='*60)

        # 1. timeseries2velocity (LOS)
        vel_los = mdir / f'velocity_{label}.h5'
        if vel_los.exists():
            print(f'  velocity_{label}.h5 already exists — skipping')
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

        # 3. Build combined mask
        if args.ds_thr > 0:
            combined_mask = build_combined_mask(
                mdir, mask, vel_vert, label,
                ds_thr=args.ds_thr, std_max_mm=std_max_mm)
        else:
            combined_mask = mask

        # Geocode combined mask
        geo_combined = geo_d / ('geo_' + combined_mask.name)
        if not geo_combined.exists():
            print(f'  Geocoding combined mask → {geo_combined.name}')
            geocode_cli.main([str(combined_mask), '-l', str(geom),
                              '--outdir', str(geo_d)])

        # 4. Geocode velocity (vertical)
        geo_vel = geo_d / f'geo_velocity_vertical_{label}.h5'
        if geo_vel.exists():
            print(f'  {geo_vel.name} exists — skipping geocode')
        else:
            print(f'  Geocoding vertical velocity → {geo_vel.name}')
            geocode_cli.main([str(vel_vert), '-l', str(geom), '--outdir', str(geo_d)])

        # 5. Export GeoTIFF
        tif_out = odir / f'velocity_{label}.tif'
        save_gdal_cli.main([
            str(geo_vel), '-d', 'velocity', '-m', str(geo_combined),
            '-o', str(tif_out), '--of', 'GTiff',
        ])

        # 6. Secondary reference correction (IQR-robust)
        apply_secondary_ref(
            tif_out,
            args.ref_lon_min, args.ref_lon_max,
            args.ref_lat_min, args.ref_lat_max,
        )
        print(f'  Exported + corrected → {tif_out}')

    print('\n=== Sub-period extraction complete ===')


if __name__ == '__main__':
    main()
