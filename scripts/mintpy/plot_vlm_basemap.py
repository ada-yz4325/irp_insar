#!/usr/bin/env python3
"""
Plot VLM (vertical velocity GeoTIFF) over ESRI satellite basemap.
Generalizable to any city — pass the appropriate --input and --label.

Usage:
  python plot_vlm_basemap.py --input exports_chengdu/velocity.tif --label chengdu
  python plot_vlm_basemap.py --input exports_beijing/velocity.tif --label beijing \\
      --bbox "116.1 116.8 39.6 40.2" --vmin -30 --vmax 10

Output: figures/vlm_over_basemap_<label>.png
"""
import argparse, sys, os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import rasterio
import rasterio.transform
import contextily as ctx

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input',    required=True,
                   help='Path to velocity GeoTIFF (m/yr, EPSG:4326)')
    p.add_argument('--label',    default='city',
                   help='Short name used in output filename, e.g. chengdu')
    p.add_argument('--bbox',     default=None,
                   help='LON_MIN LON_MAX LAT_MIN LAT_MAX — crop display to this AOI. '
                        'Defaults to the full valid-pixel extent of the GeoTIFF.')
    p.add_argument('--outdir',   default=os.path.join(REPO_ROOT, 'figures'))
    p.add_argument('--vmin',     type=float, default=-20)
    p.add_argument('--vmax',     type=float, default=20)
    p.add_argument('--cmap',     default='jet')
    p.add_argument('--dpi',      type=int, default=200)
    p.add_argument('--decimate', type=int, default=2)
    return p.parse_args()

def main():
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    step = max(1, args.decimate)

    print(f"Input:  {args.input}")
    print("Reading velocity GeoTIFF …")
    with rasterio.open(args.input) as src:
        vel = src.read(1).astype(float)
        nodata = src.nodata
        tf = src.transform

    if nodata is not None:
        vel[vel == nodata] = np.nan
    vel_mm = vel * 1000.0

    nrows, ncols = vel_mm.shape
    print(f"  Raster: {nrows}×{ncols}  valid px: {np.sum(~np.isnan(vel_mm)):,}")

    ri, ci = np.where(~np.isnan(vel_mm[::step, ::step]))
    ri, ci = ri * step, ci * step
    xs, ys = rasterio.transform.xy(tf, ri, ci)
    lons = np.array(xs, dtype=np.float32)
    lats = np.array(ys, dtype=np.float32)
    vals = vel_mm[ri, ci].astype(np.float32)

    # AOI crop — use --bbox if given, else derive from data extent
    if args.bbox:
        lon_min, lon_max, lat_min, lat_max = map(float, args.bbox.split())
    else:
        lon_min, lon_max = float(lons.min()), float(lons.max())
        lat_min, lat_max = float(lats.min()), float(lats.max())
        print(f"  Auto AOI from data extent: "
              f"lon [{lon_min:.3f}, {lon_max:.3f}]  lat [{lat_min:.3f}, {lat_max:.3f}]")

    mask = ((lons >= lon_min) & (lons <= lon_max) &
            (lats >= lat_min) & (lats <= lat_max))
    lons, lats, vals = lons[mask], lats[mask], vals[mask]
    print(f"  Points after crop: {len(vals):,}  "
          f"p2/p98: {np.percentile(vals,2):.1f}/{np.percentile(vals,98):.1f} mm/yr")

    print("Plotting …")
    fig, ax = plt.subplots(figsize=(13, 8), dpi=150)
    sc = ax.scatter(lons, lats, c=vals,
                    cmap=args.cmap, vmin=args.vmin, vmax=args.vmax,
                    s=0.5, alpha=0.85, linewidths=0, rasterized=True)

    print("Fetching satellite tiles (ESRI World Imagery) …")
    try:
        ctx.add_basemap(ax, crs='EPSG:4326',
                        source=ctx.providers.Esri.WorldImagery,
                        zoom='auto', attribution_size=7)
        print("  Tiles OK")
    except Exception as e:
        print(f"  Tile download failed: {e} — no basemap")

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_xlabel('Longitude', fontsize=12)
    ax.set_ylabel('Latitude', fontsize=12)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°E'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°N'))
    ax.tick_params(labelsize=10)

    cbar = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.03)
    cbar.set_label('Vertical Vel. (mm/yr)', fontsize=12, rotation=270, labelpad=20)
    cbar.ax.tick_params(labelsize=10)

    ax.set_title(f'Vertical Land Motion — {args.label}  (Sentinel-1, SBAS+PS-like)',
                 fontsize=13, pad=10)

    out = os.path.join(args.outdir, f'vlm_over_basemap_{args.label}.png')
    plt.tight_layout()
    plt.savefig(out, dpi=args.dpi, bbox_inches='tight')
    print(f"Saved → {out}")

if __name__ == '__main__':
    main()
