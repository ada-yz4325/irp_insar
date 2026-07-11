#!/usr/bin/env python3
"""
Three-period VLM composite — our own basemap style (ESRI satellite imagery,
district boundaries, scale bar, north arrow), three periods side by side,
one shared colorbar. Reuses the rendering helpers from plot_vlm_basemap.py;
free layout, not styled to match any paper.

Usage:
    python plot_three_panel_composite.py \\
        --exports-dir exports_beijing_iw1_ps_ds \\
        --periods 2016-2018 2019-2020 2021 \\
        --bbox "116.30 117.10 39.65 40.10" \\
        --vmin -100 --vmax 30 \\
        --outname vlm_iw1_three_panel_composite.png \\
        --outdir figures
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy.ndimage import median_filter
import rasterio
import rasterio.transform
import contextily as ctx

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_vlm_basemap import add_scale_bar, add_north_arrow, add_admin_boundaries  # noqa: E402


def load_points(tif_path, bbox, filt=3, decimate=2):
    with rasterio.open(tif_path) as src:
        vel = src.read(1).astype(np.float64)
        nodata = src.nodata
        tf = src.transform
    if nodata is not None:
        vel[vel == nodata] = np.nan
    vel[vel == 0] = np.nan
    vel_mm = vel * 1000.0

    if filt > 1:
        finite = np.isfinite(vel_mm)
        filled = np.where(finite, vel_mm, 0.0)
        vel_mm = np.where(finite, median_filter(filled, size=filt), np.nan)

    step = max(1, decimate)
    ri, ci = np.where(np.isfinite(vel_mm[::step, ::step]))
    ri, ci = ri * step, ci * step
    xs, ys = rasterio.transform.xy(tf, ri.tolist(), ci.tolist())
    lons = np.array(xs, np.float32)
    lats = np.array(ys, np.float32)
    vals = vel_mm[ri, ci].astype(np.float32)

    lon_min, lon_max, lat_min, lat_max = bbox
    inbox = ((lons >= lon_min) & (lons <= lon_max) &
             (lats >= lat_min) & (lats <= lat_max))
    return lons[inbox], lats[inbox], vals[inbox]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--exports-dir', required=True)
    ap.add_argument('--periods', nargs=3, default=['2016-2018', '2019-2020', '2021'])
    ap.add_argument('--period-labels', nargs=3, default=None)
    ap.add_argument('--bbox', default='116.30 117.10 39.65 40.10')
    ap.add_argument('--vmin', type=float, default=-100)
    ap.add_argument('--vmax', type=float, default=30)
    ap.add_argument('--cmap', default='RdYlBu')
    ap.add_argument('--filter', type=int, default=3)
    ap.add_argument('--decimate', type=int, default=2)
    ap.add_argument('--dpi', type=int, default=220)
    ap.add_argument('--outname', default='vlm_iw1_three_panel_composite.png')
    ap.add_argument('--outdir', default=str(REPO_ROOT / 'figures'))
    args = ap.parse_args()

    bbox = tuple(float(v) for v in args.bbox.split())
    lon_min, lon_max, lat_min, lat_max = bbox
    period_labels = args.period_labels or args.periods
    edir = Path(args.exports_dir)
    cmap = plt.get_cmap(args.cmap)

    fig, axes = plt.subplots(1, 3, figsize=(27, 9), dpi=args.dpi, sharey=True)

    total_pts = 0
    for i, (period, label) in enumerate(zip(args.periods, period_labels)):
        ax = axes[i]
        tif = edir / f'velocity_{period}.tif'
        if not tif.exists():
            raise SystemExit(f'Missing: {tif}')
        lons, lats, vals = load_points(tif, bbox, filt=args.filter, decimate=args.decimate)
        total_pts += len(vals)

        sc = ax.scatter(lons, lats, c=vals, cmap=cmap, vmin=args.vmin, vmax=args.vmax,
                        s=0.6, alpha=0.9, linewidths=0, rasterized=True, zorder=3)

        print(f'  {label}: fetching basemap tiles...')
        try:
            ctx.add_basemap(ax, crs='EPSG:4326', source=ctx.providers.Esri.WorldImagery,
                            zoom='auto', attribution_size=5, zorder=1)
        except Exception as e:
            print(f'  tile fetch failed for {label}: {e}')

        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        add_admin_boundaries(ax, bbox)

        if i == 0:
            add_scale_bar(ax, lon_min, lat_min, length_km=20)
        add_north_arrow(ax)

        ax.set_xlabel('Longitude', fontsize=12)
        if i == 0:
            ax.set_ylabel('Latitude', fontsize=12)
        lon_ticks = np.arange(np.ceil(lon_min * 10) / 10, np.floor(lon_max * 10) / 10 + 0.01, 0.2)
        ax.set_xticks(lon_ticks)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f°E'))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°N'))
        ax.tick_params(labelsize=10)
        ax.grid(True, linestyle='--', linewidth=0.3, alpha=0.4, color='white', zorder=2)
        ax.set_title(label, fontsize=15, fontweight='bold', pad=10)

    fig.suptitle('Vertical Land Motion — Beijing IW1 Chaoyang / Tongzhou / Daxing  ·  PS+DS',
                 fontsize=17, y=1.01)

    cbar = fig.colorbar(axes[-1].collections[0], ax=axes, orientation='vertical',
                        fraction=0.018, pad=0.012, extend='both')
    cbar.set_label('Vertical velocity (mm/yr)', fontsize=13, rotation=270, labelpad=20)
    cbar.ax.tick_params(labelsize=11)
    if args.vmin < 0 < args.vmax:
        cbar.ax.axhline(y=(0 - args.vmin) / (args.vmax - args.vmin),
                        color='k', linewidth=1.0, alpha=0.7)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / args.outname
    plt.savefig(out, dpi=args.dpi, bbox_inches='tight', facecolor='white')
    print(f'Saved -> {out}  (total points plotted: {total_pts:,})')


if __name__ == '__main__':
    main()
