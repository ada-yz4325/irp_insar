#!/usr/bin/env python3
"""
Compute Amplitude Dispersion Index (ADI) for PS-InSAR candidate selection.

ADI = sigma_A / mu_A  (Ferretti et al. 2001)

Reads the merged coregistered SLCs from ISCE2 topsStack output, computes
ADI per pixel across all dates, and saves the result as a NumPy array with
a matching GDAL-readable ENVI header for use by build_ps_mask_psinsar.py.

Threshold used in reference paper (Zhou et al. 2024, RS 16(9) 1528):
  ADI <= 0.56  AND  temporalCoherence >= 0.72

Usage:
    python compute_adi_psinsar.py --workdir /path/to/isce2_beijing_psinsar
    python compute_adi_psinsar.py --workdir /path/to/isce2_beijing_psinsar \\
        --outdir data/mintpy_outputs_psinsar --chunk-rows 512
"""
import argparse
import os
import sys
import glob
import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--workdir', required=True,
                   help='ISCE2 topsStack workDir (contains merged/SLC/)')
    p.add_argument('--outdir', default=None,
                   help='Output directory (default: <workdir>/../mintpy_outputs_psinsar)')
    p.add_argument('--chunk-rows', type=int, default=256,
                   help='Process this many rows at a time to limit RAM (default: 256)')
    return p.parse_args()


def find_slc_files(workdir):
    """Return sorted list of merged SLC base paths (without .vrt suffix).

    topsStack writes merged SLCs as *.slc.full.vrt (GDAL virtual datasets
    pointing to the per-burst coregistered SLCs).  We match those VRTs and
    strip the trailing .vrt so callers can do slc_path + '.vrt' consistently.
    """
    pattern = os.path.join(workdir, 'merged', 'SLC', '*', '*.slc.full.vrt')
    vrts = sorted(glob.glob(pattern))
    if not vrts:
        sys.exit(f"ERROR: No merged SLC files found under {workdir}/merged/SLC/\n"
                 f"       Run ISCE2 topsStack through the merge step first.")
    # Strip .vrt → base path is e.g. .../merged/SLC/20161003/20161003.slc.full
    return [v[:-4] for v in vrts]


def read_slc_header(slc_path):
    """Read ISCE2 .slc.vrt or .slc.xml to get dimensions."""
    vrt = slc_path + '.vrt'
    if not os.path.exists(vrt):
        sys.exit(f"ERROR: VRT file not found: {vrt}")
    from osgeo import gdal
    ds = gdal.Open(vrt)
    if ds is None:
        sys.exit(f"ERROR: GDAL cannot open {vrt}")
    nrows, ncols = ds.RasterYSize, ds.RasterXSize
    ds = None
    return nrows, ncols


def compute_adi(slc_files, nrows, ncols, chunk_rows):
    """Compute ADI = std(|z|) / mean(|z|) in row-chunks to limit RAM."""
    n_dates = len(slc_files)
    adi = np.zeros((nrows, ncols), dtype=np.float32)

    from osgeo import gdal

    for row_start in range(0, nrows, chunk_rows):
        row_end = min(row_start + chunk_rows, nrows)
        n_rows_chunk = row_end - row_start
        amp_stack = np.zeros((n_dates, n_rows_chunk, ncols), dtype=np.float32)

        for i, slc_path in enumerate(slc_files):
            ds = gdal.Open(slc_path + '.vrt')
            data = ds.ReadAsArray(0, row_start, ncols, n_rows_chunk)
            ds = None
            # SLC is complex; amplitude = |z|
            if np.iscomplexobj(data):
                amp_stack[i] = np.abs(data).astype(np.float32)
            else:
                amp_stack[i] = data.astype(np.float32)

        mu = amp_stack.mean(axis=0)
        sigma = amp_stack.std(axis=0)
        # Avoid division by zero in water/shadow pixels
        with np.errstate(divide='ignore', invalid='ignore'):
            chunk_adi = np.where(mu > 0, sigma / mu, np.nan)
        adi[row_start:row_end] = chunk_adi

        pct = 100.0 * row_end / nrows
        print(f"  rows {row_start:5d}–{row_end:5d} / {nrows}  ({pct:.0f}%)", flush=True)

    return adi


def save_adi(adi, outpath, slc_ref):
    """Save ADI array as float32 binary + ENVI-style header."""
    np.save(outpath + '.npy', adi)

    # Also save as GDAL GeoTiff using the SLC VRT as georef source
    try:
        from osgeo import gdal, gdal_array
        src_ds = gdal.Open(slc_ref + '.vrt')
        driver = gdal.GetDriverByName('GTiff')
        out_ds = driver.Create(outpath + '.tif', adi.shape[1], adi.shape[0],
                               1, gdal.GDT_Float32,
                               options=['COMPRESS=DEFLATE', 'TILED=YES'])
        out_ds.SetGeoTransform(src_ds.GetGeoTransform())
        out_ds.SetProjection(src_ds.GetProjection())
        out_ds.GetRasterBand(1).WriteArray(adi)
        out_ds.GetRasterBand(1).SetNoDataValue(np.nan)
        out_ds.FlushCache()
        src_ds = None
        out_ds = None
        print(f"  GeoTIFF saved: {outpath}.tif")
    except Exception as e:
        print(f"  Warning: GeoTIFF save failed ({e}); .npy still written.")


def main():
    args = parse_args()
    workdir = os.path.abspath(args.workdir)

    if args.outdir:
        outdir = os.path.abspath(args.outdir)
    else:
        outdir = os.path.join(os.path.dirname(workdir), 'mintpy_outputs_psinsar')
    os.makedirs(outdir, exist_ok=True)

    print(f"ISCE2 workdir : {workdir}")
    print(f"Output dir    : {outdir}")
    print(f"Chunk rows    : {args.chunk_rows}")

    slc_files = find_slc_files(workdir)
    print(f"\nFound {len(slc_files)} merged SLC files:")
    for f in slc_files[:3]:
        print(f"  {f}")
    if len(slc_files) > 3:
        print(f"  ... ({len(slc_files) - 3} more)")

    nrows, ncols = read_slc_header(slc_files[0])
    print(f"\nRaster size: {nrows} rows × {ncols} cols")
    mem_gb = len(slc_files) * args.chunk_rows * ncols * 4 / 1e9
    print(f"Peak RAM per chunk: ~{mem_gb:.1f} GB\n")

    print("Computing ADI ...")
    adi = compute_adi(slc_files, nrows, ncols, args.chunk_rows)

    valid = np.sum(~np.isnan(adi))
    ps_count = np.sum(adi <= 0.56)
    print(f"\nADI stats (valid pixels: {valid:,}):")
    print(f"  mean ADI : {np.nanmean(adi):.3f}")
    print(f"  median   : {np.nanmedian(adi):.3f}")
    print(f"  ADI ≤ 0.56 (PS candidates): {ps_count:,}  "
          f"({100*ps_count/valid:.1f}% of valid)")

    outpath = os.path.join(outdir, 'adi_psinsar')
    save_adi(adi, outpath, slc_files[0])
    print(f"\nSaved → {outpath}.npy  and  {outpath}.tif")
    print("\nNext: run build_ps_mask_psinsar.py to combine ADI with temporalCoherence.")


if __name__ == '__main__':
    main()
