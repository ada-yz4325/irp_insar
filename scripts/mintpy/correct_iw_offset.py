#!/usr/bin/env python3
"""
Correct IW subswath calibration offsets in MintPy velocity.h5.

Sentinel-1 TOPS mode processes three IW subswaths (IW1/IW2/IW3) and merges
them. If NESD (Network ESD) azimuth calibration fails for one or more swaths,
the merged velocity shows sharp discontinuities at swath seam lines.

This script:
1. Identifies IW seam longitudes from velocity discontinuities.
2. Estimates the velocity offset between adjacent swaths by comparing
   statistics in narrow strips just inside each seam.
3. Shifts IW1 and IW3 velocities to align with IW2 (the reference swath,
   which contains the spatial reference point).
4. Writes velocity_iw_corrected.h5 (copy of velocity.h5 + correction) and
   exports a corrected velocity GeoTIFF.

The original velocity.h5 is never modified.

Usage:
    python correct_iw_offset.py --mintpy-dir /path/to/mintpy_outputs_psinsar
        [--iw12-seam 116.10] [--iw23-seam 116.48]
        [--strip-width 0.08] [--out-dir /path/to/exports]

Seam longitudes default to auto-detect from the velocity profile.
"""
import argparse
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np


# ── helpers ──────────────────────────────────────────────────────────────────

def load_arrays(mintpy_dir: Path):
    vel_file  = mintpy_dir / "velocity.h5"
    geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"
    mask_file = mintpy_dir / "mask_ps_psinsar.h5"
    for f in (vel_file, geom_file, mask_file):
        if not f.exists():
            sys.exit(f"Missing: {f}")
    with h5py.File(vel_file,  "r") as f: vel  = f["velocity"][:] * 1000.0  # → mm/yr
    with h5py.File(geom_file, "r") as g: lon  = g["longitude"][:]
    with h5py.File(mask_file, "r") as m: mask = m["mask"][:].astype(bool)
    return vel, lon, mask


def strip_median(vel, lon, mask, lon_min, lon_max):
    px = (lon >= lon_min) & (lon < lon_max) & mask
    v  = vel[px]
    v  = v[np.isfinite(v)]
    return float(np.median(v)), len(v)


def autodetect_seams(vel, lon, mask):
    """Scan 0.05° strips and find the two biggest one-step drops."""
    edges = np.arange(115.0, 117.6, 0.05)
    meds  = []
    for lo in edges:
        m, n = strip_median(vel, lon, mask, lo, lo + 0.05)
        meds.append((lo, m, n))
    # look for largest downward jumps
    drops = []
    for i in range(1, len(meds)):
        lo_prev, m_prev, n_prev = meds[i-1]
        lo_curr, m_curr, n_curr = meds[i]
        if n_prev > 200 and n_curr > 200:
            drops.append((m_curr - m_prev, lo_curr))   # negative = drop
    drops.sort()           # most negative first
    seam_lons = sorted([d[1] for d in drops[:2]])
    return seam_lons[0], seam_lons[1]


def estimate_offset(vel, lon, mask, seam_lon, strip_w):
    """
    Estimate velocity offset as (IW_east - IW_west) at a seam.
    Uses strips of width `strip_w` just inside each swath.
    """
    gap   = 0.02   # small gap right at the seam to avoid overlap pixels
    west_med, n_w = strip_median(vel, lon, mask,
                                 seam_lon - strip_w - gap, seam_lon - gap)
    east_med, n_e = strip_median(vel, lon, mask,
                                 seam_lon + gap, seam_lon + strip_w + gap)
    offset = east_med - west_med       # east_swath - west_swath  (negative = east too low)
    print(f"  Seam ~{seam_lon:.2f}°E  |  west median={west_med:+.1f} (n={n_w:,})  "
          f"east median={east_med:+.1f} (n={n_e:,})  |  offset={offset:+.1f} mm/yr")
    return offset


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mintpy-dir", required=True)
    ap.add_argument("--iw12-seam",  type=float, default=None,
                    help="IW1/IW2 seam longitude (auto-detect if omitted)")
    ap.add_argument("--iw23-seam",  type=float, default=None,
                    help="IW2/IW3 seam longitude (auto-detect if omitted)")
    ap.add_argument("--strip-width", type=float, default=0.08,
                    help="Longitude width of estimation strip on each seam side (default 0.08°)")
    ap.add_argument("--out-dir",    default=None,
                    help="Export directory for corrected GeoTIFF (default: same as mintpy-dir)")
    args = ap.parse_args()

    mintpy_dir = Path(args.mintpy_dir)
    out_dir    = Path(args.out_dir) if args.out_dir else mintpy_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading velocity + geometry from {mintpy_dir} …")
    vel, lon, mask = load_arrays(mintpy_dir)

    # ── detect seams ──────────────────────────────────────────────────────────
    if args.iw12_seam is None or args.iw23_seam is None:
        print("Auto-detecting IW seam longitudes …")
        s12_auto, s23_auto = autodetect_seams(vel, lon, mask)
        print(f"  Detected: IW1/IW2 ≈ {s12_auto:.2f}°E,  IW2/IW3 ≈ {s23_auto:.2f}°E")
    iw12_seam = args.iw12_seam if args.iw12_seam is not None else s12_auto
    iw23_seam = args.iw23_seam if args.iw23_seam is not None else s23_auto

    print(f"\nUsing seams: IW1/IW2 = {iw12_seam:.2f}°E,  IW2/IW3 = {iw23_seam:.2f}°E")

    # ── estimate offsets ──────────────────────────────────────────────────────
    print("\nEstimating swath offsets (IW2 is the reference / zero-correction swath):")
    # IW1 offset: IW1 east edge vs IW2 west edge → IW1 is offset by +delta vs IW2
    delta_iw1 = estimate_offset(vel, lon, mask, iw12_seam, args.strip_width)
    # IW3 offset: IW2 east edge vs IW3 west edge → IW3 is offset by -delta vs IW2
    delta_iw3 = estimate_offset(vel, lon, mask, iw23_seam, args.strip_width)

    # Corrections to apply (make east side match west side of each seam):
    corr_iw1 = -delta_iw1   # shift IW1 so it matches IW2
    corr_iw3 = -delta_iw3   # shift IW3 so it matches IW2

    print(f"\nCorrections:")
    print(f"  IW1 (lon < {iw12_seam:.2f}°E): {corr_iw1:+.1f} mm/yr")
    print(f"  IW2 ({iw12_seam:.2f}–{iw23_seam:.2f}°E): ±0  (reference)")
    print(f"  IW3 (lon > {iw23_seam:.2f}°E): {corr_iw3:+.1f} mm/yr")

    # ── apply correction to velocity array (mm/yr) ────────────────────────────
    vel_corr = vel.copy()
    iw1_mask = (lon < iw12_seam) & mask
    iw3_mask = (lon > iw23_seam) & mask
    vel_corr[iw1_mask] += corr_iw1
    vel_corr[iw3_mask] += corr_iw3

    print(f"\nIW1 pixels corrected: {iw1_mask.sum():,}")
    print(f"IW3 pixels corrected: {iw3_mask.sum():,}")

    # ── write corrected velocity.h5 ───────────────────────────────────────────
    src_vel  = mintpy_dir / "velocity.h5"
    dst_vel  = mintpy_dir / "velocity_iw_corrected.h5"
    shutil.copy2(src_vel, dst_vel)
    with h5py.File(dst_vel, "r+") as f:
        f["velocity"][:] = vel_corr / 1000.0   # back to m/yr
        f.attrs["IW_CORRECTION_IW12_SEAM"] = str(iw12_seam)
        f.attrs["IW_CORRECTION_IW23_SEAM"] = str(iw23_seam)
        f.attrs["IW_CORRECTION_IW1_MM_YR"] = str(corr_iw1)
        f.attrs["IW_CORRECTION_IW3_MM_YR"] = str(corr_iw3)
        f.attrs["IW_CORRECTION_NOTE"]       = (
            "Post-hoc IW swath offset correction applied to compensate NESD "
            "calibration bias. Original velocity.h5 is unchanged. "
            "IW2 is the reference swath (no correction applied)."
        )
    print(f"\nWrote corrected velocity → {dst_vel}")

    # ── export corrected GeoTIFF ──────────────────────────────────────────────
    try:
        from mintpy.utils import readfile, writefile
        from mintpy import save_gdal
        atr = readfile.read_attribute(str(src_vel))
        out_tif = out_dir / "velocity_iw_corrected.tif"
        save_gdal.save2gdal(vel_corr / 1000.0, atr, str(out_tif),
                            dataType="float32", epsgCode=4326)
        print(f"Wrote corrected GeoTIFF  → {out_tif}")
    except Exception as e:
        print(f"GeoTIFF export skipped ({e}) — use export_velocity_products.py manually")

    # ── summary stats ─────────────────────────────────────────────────────────
    v_valid = vel_corr[mask & np.isfinite(vel_corr)]
    print(f"\nCorrected velocity stats (all PS pixels):")
    print(f"  p2/p98 : {np.percentile(v_valid,2):+.1f} / {np.percentile(v_valid,98):+.1f} mm/yr")
    print(f"  median  : {np.median(v_valid):+.1f} mm/yr")


if __name__ == "__main__":
    main()
