#!/usr/bin/env python3
"""
Plot a geographic subset of a VLM GeoTIFF over a satellite basemap.
Generalizable to any city — pass the appropriate --input velocity.tif.

Usage:
  python plot_vlm_subset.py --input exports_chengdu/velocity.tif \\
      --bbox "103.95 104.15 30.55 30.72" --label chengdu_urban

  python plot_vlm_subset.py --input exports_beijing/velocity.tif \\
      --bbox "116.2 116.6 39.7 40.1" --label beijing_urban --vmin -30 --vmax 10

bbox format: "LON_MIN LON_MAX LAT_MIN LAT_MAX"
Output: figures/vlm_subset_<label>.png  (or --outdir to override)
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
    p.add_argument('--input',  required=True,
                   help='Path to velocity GeoTIFF (m/yr, EPSG:4326)')
    p.add_argument('--bbox',   required=True,
                   help='LON_MIN LON_MAX LAT_MIN LAT_MAX (space-separated, degrees)')
    p.add_argument('--label',  default='subset',
                   help='Output filename suffix, e.g. chengdu_urban')
    p.add_argument('--outdir', default=os.path.join(REPO_ROOT, 'figures'),
                   help='Output directory (default: repo figures/)')
    p.add_argument('--vmin',   type=float, default=-20, help='Colorbar min (mm/yr)')
    p.add_argument('--vmax',   type=float, default=20,  help='Colorbar max (mm/yr)')
    p.add_argument('--cmap',   default='jet', help='Matplotlib colormap name')
    p.add_argument('--dpi',    type=int, default=200)
    p.add_argument('--decimate', type=int, default=1,
                   help='Keep every Nth valid pixel (1=all, 2=half, for speed)')
    return p.parse_args()

def main():
    args = parse_args()
    lon_min, lon_max, lat_min, lat_max = map(float, args.bbox.split())
    print(f"Input:  {args.input}")
    print(f"Subset: lon [{lon_min}, {lon_max}]  lat [{lat_min}, {lat_max}]")

    os.makedirs(args.outdir, exist_ok=True)

    print("Reading velocity GeoTIFF …")
    with rasterio.open(args.input) as src:
        vel = src.read(1).astype(float)
        nodata = src.nodata
        tf = src.transform

    if nodata is not None:
        vel[vel == nodata] = np.nan
    vel_mm = vel * 1000.0

    step = max(1, args.decimate)
    ri, ci = np.where(~np.isnan(vel_mm[::step, ::step]))
    ri, ci = ri * step, ci * step
    xs, ys = rasterio.transform.xy(tf, ri, ci)
    lons = np.array(xs, dtype=np.float32)
    lats = np.array(ys, dtype=np.float32)
    vals = vel_mm[ri, ci].astype(np.float32)

    mask = ((lons >= lon_min) & (lons <= lon_max) &
            (lats >= lat_min) & (lats <= lat_max))
    lons, lats, vals = lons[mask], lats[mask], vals[mask]
    print(f"  Points in subset: {len(vals):,}")

    if len(vals) == 0:
        sys.exit("ERROR: no valid pixels in this bbox — check coordinates.")

    print(f"  Value range: {vals.min():.1f} to {vals.max():.1f} mm/yr  "
          f"p2/p98: {np.percentile(vals,2):.1f}/{np.percentile(vals,98):.1f}")

    fig, ax = plt.subplots(figsize=(10, 7), dpi=args.dpi)
    sc = ax.scatter(lons, lats, c=vals,
                    cmap=args.cmap, vmin=args.vmin, vmax=args.vmax,
                    s=1.5, alpha=0.9, linewidths=0, rasterized=True)

    print("Fetching satellite tiles …")
    try:
        ctx.add_basemap(ax, crs='EPSG:4326',
                        source=ctx.providers.Esri.WorldImagery,
                        zoom='auto', attribution_size=7)
    except Exception as e:
        print(f"  Warning: tile download failed ({e}) — no basemap")

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_xlabel('Longitude', fontsize=11)
    ax.set_ylabel('Latitude', fontsize=11)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f°E'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.3f°N'))
    ax.tick_params(labelsize=9)

    cbar = fig.colorbar(sc, ax=ax, pad=0.02, fraction=0.03)
    cbar.set_label('Vertical Vel. (mm/yr)', fontsize=11, rotation=270, labelpad=20)

    ax.set_title(f'VLM subset — {args.label}', fontsize=12, pad=8)

    out = os.path.join(args.outdir, f'vlm_subset_{args.label}.png')
    plt.tight_layout()
    plt.savefig(out, dpi=args.dpi, bbox_inches='tight')
    print(f"Saved → {out}")

if __name__ == '__main__':
    main()
