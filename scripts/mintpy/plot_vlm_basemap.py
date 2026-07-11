#!/usr/bin/env python3
"""
Paper-quality VLM basemap plot over ESRI satellite imagery.

Features:
  - Spatial 3x3 median filter to suppress salt-and-pepper noise
  - RdYlBu diverging colormap (red=subsiding, blue=uplift/stable)
  - Beijing district boundary overlay (data/admin/beijing_districts.json)
  - Manual scale bar and north arrow
  - Per-point velocity uncertainty masking (--std-tif)
  - Statistics annotation (n_points, period, data source)

Usage:
  python plot_vlm_basemap.py \\
      --input  exports_beijing_iw2_2016_2021/velocity_2016-2021.tif \\
      --label  "Beijing IW2" \\
      --period "Oct 2016 – Nov 2021" \\
      --bbox   "115.80 116.52 39.65 40.10" \\
      --vmin -40 --vmax 5 --dpi 300
"""
import argparse
import os
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patheffects as pe
from matplotlib.colors import LinearSegmentedColormap
from scipy.ndimage import median_filter
import rasterio
import rasterio.transform
import contextily as ctx

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_JSON = REPO_ROOT / 'data' / 'admin' / 'beijing_districts.json'


# ── Custom colormap: white at 0, blue toward positive, red toward negative ──
def make_vlm_cmap():
    """Diverging colormap tuned for InSAR VLM (mostly negative values)."""
    return plt.get_cmap('RdYlBu')


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--input',    required=True,
                   help='Velocity GeoTIFF path (m/yr, EPSG:4326)')
    p.add_argument('--std-tif',  default=None,
                   help='Optional velocity-uncertainty GeoTIFF (m/yr); pixels with '
                        'std > --std-max are masked out before plotting.')
    p.add_argument('--std-max',  type=float, default=None,
                   help='Max allowed velocity uncertainty in mm/yr (default: no filter)')
    p.add_argument('--label',    default='city')
    p.add_argument('--period',   default=None,
                   help='Period string for title, e.g. "Oct 2016 – Dec 2019"')
    p.add_argument('--outname',  default=None,
                   help='Output filename (no directory). Default: vlm_<label>.png')
    p.add_argument('--outdir',   default=str(REPO_ROOT / 'figures'))
    p.add_argument('--bbox',     default=None,
                   help='LON_MIN LON_MAX LAT_MIN LAT_MAX — display window')
    p.add_argument('--vmin',     type=float, default=-30)
    p.add_argument('--vmax',     type=float, default=5)
    p.add_argument('--cmap',     default='RdYlBu')
    p.add_argument('--filter',   type=int, default=3,
                   help='Spatial median-filter kernel size in raster pixels (default 3, set 1 to disable)')
    p.add_argument('--decimate', type=int, default=2,
                   help='Plot every Nth pixel (default 2)')
    p.add_argument('--dpi',      type=int, default=250)
    p.add_argument('--no-admin', action='store_true',
                   help='Skip Beijing district boundary overlay')
    p.add_argument('--subtitle', default='Sentinel-1 SBAS+PS',
                   help='Second title line, e.g. "Sentinel-1 IW1 SBAS+PS+DS" (default: "Sentinel-1 SBAS+PS")')
    p.add_argument('--ref-desc', default='reference point',
                   help='Short description of the reference point for the footer annotation, '
                        'e.g. "connected-component-validated point, 39.821N 116.509E"')
    return p.parse_args()


def add_scale_bar(ax, lon_min, lat_min, length_km=20):
    """Draw a manual scale bar in the lower-left corner."""
    import pyproj
    geod = pyproj.Geod(ellps='WGS84')
    lon_start = lon_min + 0.04
    lat_bar   = lat_min + 0.025
    # Convert km to degrees longitude at this latitude
    _, _, dist_m = geod.inv(lon_start, lat_bar, lon_start + 1.0, lat_bar)
    deg_per_km = 1.0 / (dist_m / 1000.0)
    bar_len = length_km * deg_per_km

    bar_props = dict(linewidth=3, solid_capstyle='butt', color='white',
                     path_effects=[pe.Stroke(linewidth=5, foreground='black'), pe.Normal()])
    ax.plot([lon_start, lon_start + bar_len], [lat_bar, lat_bar],
            transform=ax.transData, **bar_props)
    ax.text(lon_start + bar_len / 2, lat_bar + 0.008, f'{length_km} km',
            ha='center', va='bottom', fontsize=9, color='white', fontweight='bold',
            path_effects=[pe.Stroke(linewidth=2, foreground='black'), pe.Normal()])


def add_north_arrow(ax):
    """Draw a north arrow in the upper-right corner."""
    ax_xlim = ax.get_xlim(); ax_ylim = ax.get_ylim()
    x = ax_xlim[0] + 0.93 * (ax_xlim[1] - ax_xlim[0])
    y = ax_ylim[0] + 0.88 * (ax_ylim[1] - ax_ylim[0])
    dy = 0.022 * (ax_ylim[1] - ax_ylim[0])
    arrowprops = dict(arrowstyle='->', color='white', lw=2,
                      path_effects=[pe.Stroke(linewidth=3, foreground='black'), pe.Normal()])
    ax.annotate('', xy=(x, y + dy), xytext=(x, y),
                arrowprops=arrowprops)
    ax.text(x, y - 0.003 * (ax_ylim[1] - ax_ylim[0]), 'N',
            ha='center', va='top', fontsize=10, fontweight='bold', color='white',
            path_effects=[pe.Stroke(linewidth=2, foreground='black'), pe.Normal()])


# Chinese → English/pinyin district name lookup (Beijing 16 districts)
_DIST_NAMES = {
    '东城区': 'Dongcheng', '西城区': 'Xicheng', '朝阳区': 'Chaoyang',
    '丰台区': 'Fengtai',   '石景山区': 'Shijingshan', '海淀区': 'Haidian',
    '门头沟区': 'Mentougou', '房山区': 'Fangshan',   '通州区': 'Tongzhou',
    '顺义区': 'Shunyi',    '昌平区': 'Changping',   '大兴区': 'Daxing',
    '怀柔区': 'Huairou',   '平谷区': 'Pinggu',      '密云区': 'Miyun',
    '延庆区': 'Yanqing',
}


def add_admin_boundaries(ax, bbox):
    """Overlay Beijing district boundaries from local GeoJSON with English labels."""
    if not ADMIN_JSON.exists():
        print(f'  Admin GeoJSON not found at {ADMIN_JSON} — skipping')
        return
    try:
        import geopandas as gpd
        gdf = gpd.read_file(str(ADMIN_JSON))
        lon_min, lon_max, lat_min, lat_max = bbox
        gdf_clip = gdf.cx[lon_min:lon_max, lat_min:lat_max]
        if gdf_clip.empty:
            print('  No districts in AOI bbox — skipping')
            return
        gdf_clip.boundary.plot(ax=ax, color='white', linewidth=0.8, alpha=0.75,
                               path_effects=[pe.Stroke(linewidth=1.6, foreground='black', alpha=0.5),
                                             pe.Normal()])
        # Label districts whose centroid is inside the view. Skip labels that
        # would land within min_sep of an already-placed one (e.g. tiny,
        # adjacent Xicheng/Dongcheng otherwise print on top of each other).
        min_sep = 0.10 * (lon_max - lon_min)
        placed = []
        for _, row in gdf_clip.iterrows():
            cx, cy = row.geometry.centroid.x, row.geometry.centroid.y
            if lon_min < cx < lon_max and lat_min < cy < lat_max:
                if any(((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 < min_sep for px, py in placed):
                    continue
                placed.append((cx, cy))
                cn_name = row.get('name', '')
                label   = _DIST_NAMES.get(cn_name, cn_name)
                ax.text(cx, cy, label, ha='center', va='center', fontsize=6.5,
                        color='white', alpha=0.92, fontweight='bold',
                        path_effects=[pe.Stroke(linewidth=1.8, foreground='black', alpha=0.6),
                                      pe.Normal()])
        print(f'  Added {len(gdf_clip)} district boundaries')
    except Exception as e:
        print(f'  Admin boundary error: {e}')


def main():
    args = parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    # ── Load velocity raster ──────────────────────────────────────────────────
    print(f'Reading {args.input}')
    with rasterio.open(args.input) as src:
        vel = src.read(1).astype(np.float64)
        nodata = src.nodata
        tf = src.transform

    if nodata is not None:
        vel[vel == nodata] = np.nan
    vel_mm = vel * 1000.0          # m/yr → mm/yr

    # ── Optional std-based masking ────────────────────────────────────────────
    if args.std_tif and args.std_max is not None:
        print(f'Applying uncertainty mask: std ≤ {args.std_max} mm/yr')
        with rasterio.open(args.std_tif) as ss:
            std_mm = ss.read(1).astype(np.float64) * 1000.0
            nd_s = ss.nodata
        if nd_s is not None:
            std_mm[std_mm == nd_s] = np.nan
        bad = (~np.isfinite(std_mm)) | (std_mm > args.std_max)
        n_before = np.sum(np.isfinite(vel_mm))
        vel_mm[bad] = np.nan
        print(f'  Masked {n_before - np.sum(np.isfinite(vel_mm)):,} high-uncertainty pixels')

    # ── Spatial median filter to suppress noise ───────────────────────────────
    if args.filter > 1:
        finite_mask = np.isfinite(vel_mm)
        vel_filled = np.where(finite_mask, vel_mm, 0.0)
        vel_filt   = median_filter(vel_filled, size=args.filter)
        # Restore NaN where original was NaN
        vel_mm = np.where(finite_mask, vel_filt, np.nan)
        print(f'Applied {args.filter}×{args.filter} median filter')

    nrows, ncols = vel_mm.shape
    n_valid = np.sum(np.isfinite(vel_mm))
    print(f'Raster: {nrows}×{ncols}  valid: {n_valid:,} px')

    # ── Extract scatter points ────────────────────────────────────────────────
    step = max(1, args.decimate)
    ri, ci = np.where(np.isfinite(vel_mm[::step, ::step]))
    ri, ci = ri * step, ci * step
    xs, ys = rasterio.transform.xy(tf, ri.tolist(), ci.tolist())
    lons = np.array(xs, np.float32)
    lats = np.array(ys, np.float32)
    vals = vel_mm[ri, ci].astype(np.float32)

    # ── AOI crop ──────────────────────────────────────────────────────────────
    if args.bbox:
        lon_min, lon_max, lat_min, lat_max = map(float, args.bbox.split())
    else:
        valid_lons = lons[np.isfinite(vals)]
        valid_lats = lats[np.isfinite(vals)]
        lon_min, lon_max = float(valid_lons.min()), float(valid_lons.max())
        lat_min, lat_max = float(valid_lats.min()), float(valid_lats.max())

    inbox = ((lons >= lon_min) & (lons <= lon_max) &
             (lats >= lat_min) & (lats <= lat_max))
    lons, lats, vals = lons[inbox], lats[inbox], vals[inbox]
    n_pts = len(vals)
    p2  = float(np.nanpercentile(vals, 2))
    p98 = float(np.nanpercentile(vals, 98))
    med = float(np.nanmedian(vals))
    print(f'Plot points: {n_pts:,}  p2/med/p98: {p2:.1f}/{med:.1f}/{p98:.1f} mm/yr')

    # ── Figure setup ──────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(13, 8), dpi=args.dpi)

    # Scatter plot — rasterized to keep file size manageable
    cmap = plt.get_cmap(args.cmap)
    sc = ax.scatter(lons, lats, c=vals,
                    cmap=cmap, vmin=args.vmin, vmax=args.vmax,
                    s=0.4, alpha=0.90, linewidths=0, rasterized=True,
                    zorder=3)

    # ── Satellite basemap ─────────────────────────────────────────────────────
    print('Fetching ESRI World Imagery tiles …')
    try:
        ctx.add_basemap(ax, crs='EPSG:4326',
                        source=ctx.providers.Esri.WorldImagery,
                        zoom='auto', attribution_size=6, zorder=1)
        print('  Tiles OK')
    except Exception as e:
        print(f'  Tile download failed: {e}')

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)

    # ── District boundaries ───────────────────────────────────────────────────
    if not args.no_admin:
        add_admin_boundaries(ax, (lon_min, lon_max, lat_min, lat_max))

    # ── Scale bar + north arrow ───────────────────────────────────────────────
    add_scale_bar(ax, lon_min, lat_min, length_km=20)
    add_north_arrow(ax)

    # ── Axes formatting ───────────────────────────────────────────────────────
    ax.set_xlabel('Longitude', fontsize=11)
    ax.set_ylabel('Latitude', fontsize=11)
    lon_ticks = np.arange(np.ceil(lon_min * 10) / 10,
                           np.floor(lon_max * 10) / 10 + 0.01, 0.1)
    lat_ticks = np.arange(np.ceil(lat_min * 10) / 10,
                           np.floor(lat_max * 10) / 10 + 0.01, 0.05)
    ax.set_xticks(lon_ticks)
    ax.set_yticks(lat_ticks)
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°E'))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.2f°N'))
    ax.tick_params(labelsize=9)
    ax.grid(True, linestyle='--', linewidth=0.3, alpha=0.4, color='white', zorder=2)

    # ── Colorbar ──────────────────────────────────────────────────────────────
    cbar = fig.colorbar(sc, ax=ax, pad=0.015, fraction=0.028, extend='min')
    cbar.set_label('Vertical velocity (mm/yr)', fontsize=11,
                   rotation=270, labelpad=18)
    cbar.ax.tick_params(labelsize=9)
    # Add zero reference line on colorbar
    if args.vmin < 0 < args.vmax:
        cbar.ax.axhline(y=(0 - args.vmin) / (args.vmax - args.vmin),
                        color='k', linewidth=1.0, alpha=0.7)

    # ── Title ─────────────────────────────────────────────────────────────────
    period_str = f'  [{args.period}]' if args.period else ''
    ax.set_title(
        f'Vertical Land Motion — {args.label}{period_str}\n'
        f'{args.subtitle}  ·  n={n_pts:,} pts',
        fontsize=12, pad=8
    )

    # ── Data-source annotation ────────────────────────────────────────────────
    ax.text(0.01, 0.01,
            f'InSAR: Sentinel-1 | Processing: ISCE2+MintPy | Ref: {args.ref_desc}',
            transform=ax.transAxes, fontsize=6, color='white', alpha=0.8,
            path_effects=[pe.Stroke(linewidth=1.5, foreground='black', alpha=0.5),
                          pe.Normal()],
            va='bottom', ha='left')

    # ── Save ──────────────────────────────────────────────────────────────────
    fname = args.outname if args.outname else f'vlm_{args.label.replace(" ", "_")}.png'
    out = os.path.join(args.outdir, fname)
    plt.tight_layout()
    plt.savefig(out, dpi=args.dpi, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved → {out}')


if __name__ == '__main__':
    main()
