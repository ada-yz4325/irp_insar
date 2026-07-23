#!/usr/bin/env python3
"""
Paper-style multi-panel VLM figure: three sub-period rate maps + a shared
discrete legend panel, laid out like Zhou et al. 2024 Figure 5 (a/b/c maps,
panel d = legend with binned Def. Rate color key, district glossary,
reference point, scale bar, north arrow). Map content uses our own source
imagery (ESRI satellite basemap + scattered PS/DS points), not a flat
paper-style background -- only the page layout and discrete color-bin
legend follow the paper.

Usage:
    python plot_paper_style_panels.py \\
        --exports-dir exports_beijing_iw1_ps_ds \\
        --periods 2016-2018 2019-2020 2021 \\
        --ref-lalo 39.82087 116.50944 \\
        --bbox "116.30 117.10 39.65 40.10" \\
        --outname vlm_iw1_paper_style_panels.png \\
        --outdir figures
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import ListedColormap, BoundaryNorm
from scipy.ndimage import median_filter
import rasterio
import rasterio.transform
import contextily as ctx
import shapely

REPO_ROOT = Path(__file__).resolve().parents[2]
ADMIN_JSON = REPO_ROOT / 'data' / 'admin' / 'beijing_districts.json'

# Districts our IW1 stack actually has substantial data over -- used as the
# default clip AOI (approximates "the same area shown in the paper" without
# claiming to reproduce their unpublished exact polygon; see docstring).
# Deliberately excludes Fengtai/Haidian/Shijingshan: those districts' full
# administrative extent reaches well *west* of IW1's true swath footprint
# (that's western/central Beijing, covered by the separate IW2 stack, not
# this one) -- including them here would widen the clip AOI into area we
# have zero data for, which is the opposite of the goal (a tight, filled
# map, not a wider empty one).
DEFAULT_AOI_DISTRICTS = ['朝阳区', '通州区', '大兴区']

# Default Def. Rate bin edges (mm/yr), matching the paper's Beijing legend.
# Other regions pass --bin-edges to override -- Himalaya's own value range
# (roughly -80..+35 mm/yr p0.5-p99.5 across all 3 periods) happens to fit
# comfortably inside these same edges, so it's also this script's fallback.
DEFAULT_BIN_EDGES = [-100, -90, -80, -70, -60, -50, -40, -30, -20, -10, 10, 20, 30]

_DIST_NAMES = {
    '东城区': 'Dongcheng', '西城区': 'Xicheng', '朝阳区': 'Chaoyang',
    '丰台区': 'Fengtai', '石景山区': 'Shijingshan', '海淀区': 'Haidian',
    '门头沟区': 'Mentougou', '房山区': 'Fangshan', '通州区': 'Tongzhou',
    '顺义区': 'Shunyi', '昌平区': 'Changping', '大兴区': 'Daxing',
    '怀柔区': 'Huairou', '平谷区': 'Pinggu', '密云区': 'Miyun',
    '延庆区': 'Yanqing',
}


def load_aoi_polygon(district_names=None, admin_json=None, aoi_wkt=None):
    """Either union of named districts (Chinese names, as in an admin geojson)
    or a directly-supplied WKT polygon -> a single shapely (Multi)Polygon used
    to clip the plotted points. Exactly one of (district_names, aoi_wkt)
    should be given."""
    if aoi_wkt:
        import shapely.wkt
        return shapely.wkt.loads(aoi_wkt)
    import geopandas as gpd
    gdf = gpd.read_file(str(admin_json))
    sel = gdf[gdf['name'].isin(district_names)]
    if sel.empty:
        raise SystemExit(f'No districts matched {district_names} in {admin_json}')
    return sel.union_all()


def make_bin_labels(edges):
    labels = [f'< {edges[0]:g}']
    for i in range(len(edges) - 2):
        lo, hi = edges[i], edges[i + 1]
        if lo < 0 <= hi or (lo <= 0 and hi >= 0 and lo != hi):
            labels.append(f'{lo:+g} ~ {hi:+g}')
        else:
            labels.append(f'{lo:g} ~ {hi:g}')
    labels[-1] = f'{edges[-2]:+g} ~ {edges[-1]:+g}'
    return labels


def make_cmap_norm(bin_edges):
    cmap_base = plt.get_cmap('jet_r')
    n = len(bin_edges) - 1
    colors = [cmap_base(i / (n - 1)) for i in range(n)]
    cmap = ListedColormap(colors)
    cmap.set_under(cmap_base(0.0))
    cmap.set_over(cmap_base(1.0))
    norm = BoundaryNorm(bin_edges, cmap.N)
    return cmap, norm


def load_period_points(tif_path, bbox, filt=3, decimate=2, aoi_polygon=None):
    """Load a period's velocity raster as decimated (lon, lat, mm/yr) points
    for scatter plotting over a satellite basemap (our own map style).
    If aoi_polygon is given, points outside it are dropped (shapely.vectorized,
    fast enough for O(1e6) points)."""
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
    if aoi_polygon is not None:
        inbox &= shapely.contains_xy(aoi_polygon, lons.astype(np.float64),
                                     lats.astype(np.float64))
    return lons[inbox], lats[inbox], vals[inbox]


def add_admin(ax, bbox, admin_json=None):
    if admin_json is None or not Path(admin_json).exists():
        return
    import geopandas as gpd
    gdf = gpd.read_file(str(admin_json))
    lon_min, lon_max, lat_min, lat_max = bbox
    gdf_clip = gdf.cx[lon_min:lon_max, lat_min:lat_max]
    if gdf_clip.empty:
        return
    # white-on-black-stroke styling reads on top of satellite imagery
    gdf_clip.boundary.plot(ax=ax, color='white', linewidth=0.8, alpha=0.8, zorder=5,
                           path_effects=[pe.Stroke(linewidth=1.6, foreground='black', alpha=0.5),
                                         pe.Normal()])
    # min separation between label anchors (degrees) to avoid overlapping text
    # for small, adjacent districts (e.g. Xicheng/Dongcheng)
    min_sep = 0.10 * (lon_max - lon_min)
    placed = []
    for _, row in gdf_clip.iterrows():
        cx, cy = row.geometry.centroid.x, row.geometry.centroid.y
        if not (lon_min < cx < lon_max and lat_min < cy < lat_max):
            continue
        if any(((cx - px) ** 2 + (cy - py) ** 2) ** 0.5 < min_sep for px, py in placed):
            continue
        placed.append((cx, cy))
        label = _DIST_NAMES.get(row.get('name', ''), row.get('name', ''))
        ax.text(cx, cy, label, ha='center', va='center', fontsize=7.5,
                color='white', fontweight='bold', zorder=6,
                path_effects=[pe.Stroke(linewidth=1.8, foreground='black', alpha=0.6), pe.Normal()])


def add_scalebar_north(ax, lon_min, lat_min, length_km=20):
    import pyproj
    geod = pyproj.Geod(ellps='WGS84')
    lon_start = lon_min + 0.03
    lat_bar = lat_min + 0.02
    _, _, dist_m = geod.inv(lon_start, lat_bar, lon_start + 1.0, lat_bar)
    bar_len = length_km / (dist_m / 1000.0)
    ax.plot([lon_start, lon_start + bar_len], [lat_bar, lat_bar],
            color='white', linewidth=2.6, solid_capstyle='butt', zorder=7,
            path_effects=[pe.Stroke(linewidth=4, foreground='black'), pe.Normal()])
    ax.text(lon_start + bar_len / 2, lat_bar + 0.012, f'{length_km} km',
            ha='center', va='bottom', fontsize=8, zorder=7, color='white', fontweight='bold',
            path_effects=[pe.Stroke(linewidth=2, foreground='black'), pe.Normal()])
    ax_xlim = ax.get_xlim(); ax_ylim = ax.get_ylim()
    x = ax_xlim[0] + 0.92 * (ax_xlim[1] - ax_xlim[0])
    y = ax_ylim[0] + 0.85 * (ax_ylim[1] - ax_ylim[0])
    dy = 0.03 * (ax_ylim[1] - ax_ylim[0])
    ax.annotate('', xy=(x, y + dy), xytext=(x, y),
                arrowprops=dict(arrowstyle='-|>', color='white', lw=2,
                                path_effects=[pe.Stroke(linewidth=3.5, foreground='black'), pe.Normal()]))
    ax.text(x, y - 0.004 * (ax_ylim[1] - ax_ylim[0]), 'N', ha='center', va='top',
            fontsize=9, fontweight='bold', zorder=7, color='white',
            path_effects=[pe.Stroke(linewidth=2, foreground='black'), pe.Normal()])


def plot_panel(ax, tif_path, bbox, cmap, norm, ref_lalo, panel_letter, period_label,
               show_scale=False, filt=3, decimate=2, aoi_polygon=None, admin_json=None):
    lon_min, lon_max, lat_min, lat_max = bbox
    lons, lats, vals = load_period_points(tif_path, bbox, filt=filt, decimate=decimate,
                                          aoi_polygon=aoi_polygon)
    mesh = ax.scatter(lons, lats, c=vals, cmap=cmap, norm=norm,
                      s=0.6, alpha=0.9, linewidths=0, rasterized=True, zorder=3)
    try:
        ctx.add_basemap(ax, crs='EPSG:4326', source=ctx.providers.Esri.WorldImagery,
                        zoom='auto', attribution_size=4, zorder=1)
    except Exception as e:
        print(f'  tile fetch failed: {e}')
    add_admin(ax, bbox, admin_json=admin_json)
    if aoi_polygon is not None:
        # distinct outline for the clip AOI itself, on top of the individual
        # (lighter) district boundaries -- echoes the paper's own practice of
        # drawing its "Beijing Plain" study-area outline distinctly from
        # ordinary district lines.
        import geopandas as gpd
        gpd.GeoSeries([aoi_polygon]).boundary.plot(
            ax=ax, color='#c77dff', linewidth=1.6, zorder=6, alpha=0.95)
    if ref_lalo:
        ax.scatter([ref_lalo[1]], [ref_lalo[0]], marker='+', s=170, color='red',
                   linewidth=2.6, zorder=8)
    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.tick_params(labelsize=8)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.1f}°E'))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f'{v:.2f}°N'))
    for spine in ax.spines.values():
        spine.set_linewidth(1.1)
    # Solid background chips (not stroke-outlined text) for the panel letter
    # and period label -- robust and unambiguous regardless of what's behind them.
    ax.text(0.03, 0.065, panel_letter, transform=ax.transAxes, fontsize=16,
            fontweight='bold', va='bottom', ha='left', zorder=9, color='white',
            bbox=dict(boxstyle='square,pad=0.25', facecolor='black', alpha=0.65,
                     edgecolor='none'))
    ax.text(0.97, 0.045, period_label, transform=ax.transAxes, fontsize=14,
            fontweight='bold', va='bottom', ha='right', zorder=9, color='white',
            bbox=dict(boxstyle='square,pad=0.3', facecolor='black', alpha=0.65,
                     edgecolor='none'))
    if show_scale:
        add_scalebar_north(ax, lon_min, lat_min)
    return mesh


def build_legend_panel(ax, cmap, norm, bin_labels, district_keys=None,
                       aoi_label='Clip AOI', footer_text='', show_district_boundary=True):
    """Fill the whole panel height evenly (paper's legend uses the full page
    height; our first draft only used the middle ~30%, which read as cramped
    with a lot of dead space above and below).

    district_keys: optional list of (abbr, full_name) pairs for a "District
    key" glossary block. When None (no admin boundary data for this region),
    that block is omitted and the symbol key below it simply moves up to
    fill the space, rather than leaving a hole in the layout.
    """
    ax.axis('off')
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    # ---- left column: Def. Rate color-bin legend, spans nearly the full height
    ax.text(0.04, 0.965, 'Def. Rate', fontsize=15, fontweight='bold', va='top')
    ax.text(0.04, 0.915, '(mm/yr)', fontsize=15, fontweight='bold', va='top')

    n = len(bin_labels)
    y_top, y_bot = 0.855, 0.06
    h = (y_top - y_bot) / n
    cmap_base = plt.get_cmap('jet_r')
    for i, lbl in enumerate(bin_labels):
        y = y_top - (i + 1) * h
        color = cmap_base(i / (n - 1))
        ax.add_patch(plt.Rectangle((0.04, y), 0.13, h * 0.82, facecolor=color,
                                   edgecolor='black', linewidth=0.5))
        ax.text(0.20, y + h * 0.41, lbl, fontsize=11.5, va='center')

    # ---- right column: optional district glossary (upper) + symbol key
    # (lower), each block spread out to match the left column's full-height span
    gx = 0.52
    sym_top = 0.87

    if district_keys:
        ax.text(gx, 0.965, 'District key', fontsize=13, fontweight='bold', va='top')
        dk_top = 0.87
        dk_step = 0.072
        for i, (abbr, full) in enumerate(district_keys):
            y = dk_top - i * dk_step
            ax.text(gx, y, f'{abbr}', fontsize=11.5, fontweight='bold', va='center')
            ax.text(gx + 0.11, y, f': {full}', fontsize=11.5, va='center')
        divider_y = dk_top - len(district_keys) * dk_step - 0.035
        ax.plot([gx, 0.98], [divider_y, divider_y], color='#dddddd', linewidth=1)
        sym_top = divider_y - 0.06

    sym_step = 0.075
    ax.plot([gx + 0.015], [sym_top], marker='+', color='red', markersize=16,
            markeredgewidth=2.6, linestyle='none')
    ax.text(gx + 0.09, sym_top, 'Reference point', fontsize=11.5, va='center')

    i = 1
    if show_district_boundary:
        ax.plot([gx + 0.015], [sym_top - i * sym_step], marker='s', markerfacecolor='none',
                markeredgecolor='#333333', markersize=11, linestyle='none')
        ax.text(gx + 0.09, sym_top - i * sym_step, 'District boundary', fontsize=11.5, va='center')
        i += 1

    ax.plot([gx - 0.005, gx + 0.035], [sym_top - i * sym_step] * 2,
            color='#c77dff', linewidth=2.4)
    ax.text(gx + 0.09, sym_top - i * sym_step, aoi_label, fontsize=11.5, va='center')

    if footer_text:
        ax.text(gx, 0.075, footer_text, fontsize=9, color='#555555', va='top', linespacing=1.6)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--exports-dir', required=True)
    ap.add_argument('--periods', nargs=3, default=['2016-2018', '2019-2020', '2021'])
    ap.add_argument('--period-labels', nargs=3, default=None,
                    help='Display labels, default: same as --periods')
    ap.add_argument('--ref-lalo', nargs=2, type=float, default=[39.82087, 116.50944])
    ap.add_argument('--bbox', default=None,
                    help='LON_MIN LON_MAX LAT_MIN LAT_MAX -- default: tight fit around '
                         '--clip-districts\' union, with a small margin')
    ap.add_argument('--clip-districts', nargs='*', default=DEFAULT_AOI_DISTRICTS,
                    help='Chinese district names (as in --admin-json) to union into the '
                         'clip AOI. Mutually exclusive with --aoi-wkt. Pass nothing to '
                         'disable clipping.')
    ap.add_argument('--admin-json', default=None,
                    help='Path to a district-boundary GeoJSON with a "name" field. '
                         'Default: data/admin/beijing_districts.json if --clip-districts '
                         'is non-empty and this is unset; omit entirely for regions with '
                         'no admin boundary file (district lines/labels are then skipped).')
    ap.add_argument('--aoi-wkt', default=None,
                    help='WKT polygon to use directly as the clip AOI instead of a '
                         'district union (e.g. the raw AOI used for data download). '
                         'Mutually exclusive with --clip-districts.')
    ap.add_argument('--aoi-label', default='Clip AOI (district union)',
                    help='Legend text for the purple clip-AOI outline symbol.')
    ap.add_argument('--bin-edges', nargs='+', type=float, default=None,
                    help='Def. Rate bin edges in mm/yr, e.g. --bin-edges -90 -70 -50 '
                         '-30 -10 10 30. Default: the Beijing paper-derived bins.')
    ap.add_argument('--title', default=None,
                    help='Figure suptitle (use \\n for a second line). Default: a '
                         'Beijing IW1 PS+DS title, kept for backward compatibility.')
    ap.add_argument('--footer-text', default=None,
                    help='Footer note under the legend symbol key (use \\n for line '
                         'breaks). Default: a Beijing IW1 note, kept for backward compat.')
    ap.add_argument('--filter', type=int, default=3)
    ap.add_argument('--decimate', type=int, default=2)
    ap.add_argument('--outname', default='vlm_iw1_paper_style_panels.png')
    ap.add_argument('--outdir', default=str(REPO_ROOT / 'figures'))
    ap.add_argument('--dpi', type=int, default=250)
    ap.add_argument('--figsize', nargs=2, type=float, default=[11, 10.4],
                    help='Figure (width, height) in inches. Default (11, 10.4) suits '
                         "Beijing's narrower AOI; wider/shorter AOIs (e.g. Himalaya) "
                         'should pass a smaller height to avoid a large blank gap '
                         'between the suptitle and the panels.')
    args = ap.parse_args()

    if args.aoi_wkt:
        aoi_polygon = load_aoi_polygon(aoi_wkt=args.aoi_wkt)
        admin_json = Path(args.admin_json) if args.admin_json else None
    elif args.clip_districts:
        admin_json = Path(args.admin_json) if args.admin_json else ADMIN_JSON
        aoi_polygon = load_aoi_polygon(district_names=args.clip_districts, admin_json=admin_json)
    else:
        aoi_polygon = None
        admin_json = Path(args.admin_json) if args.admin_json else None

    if args.bbox:
        bbox = tuple(float(v) for v in args.bbox.split())
    elif aoi_polygon is not None:
        pad = 0.02
        lon_min, lat_min, lon_max, lat_max = aoi_polygon.bounds
        bbox = (lon_min - pad, lon_max + pad, lat_min - pad, lat_max + pad)
    else:
        bbox = (116.30, 117.10, 39.65, 40.10)
    print(f'  clip AOI: {args.aoi_wkt or args.clip_districts or "(none)"}')
    print(f'  display bbox: {bbox}')

    period_labels = args.period_labels or args.periods
    edir = Path(args.exports_dir)
    bin_edges = args.bin_edges or DEFAULT_BIN_EDGES
    bin_labels = make_bin_labels(bin_edges)

    cmap, norm = make_cmap_norm(bin_edges)
    fig, axes = plt.subplots(2, 2, figsize=tuple(args.figsize), dpi=args.dpi)
    panel_letters = ['a', 'b', 'c']

    for i, (period, label) in enumerate(zip(args.periods, period_labels)):
        ax = axes.flat[i]
        tif = edir / f'velocity_{period}.tif'
        if not tif.exists():
            raise SystemExit(f'Missing: {tif}')
        plot_panel(ax, tif, bbox, cmap, norm, tuple(args.ref_lalo),
                  panel_letters[i], label, show_scale=(i == 0), filt=args.filter,
                  decimate=args.decimate, aoi_polygon=aoi_polygon, admin_json=admin_json)
        print(f'  panel ({panel_letters[i]}) {label}: {tif.name}')

    district_keys = None
    if admin_json is not None and args.clip_districts and admin_json == ADMIN_JSON:
        district_keys = [(_DIST_NAMES.get(d, d)[:2].upper(), _DIST_NAMES.get(d, d))
                         for d in args.clip_districts]
    footer_text = args.footer_text or (
        "irp_insar · Sentinel-1 track 47 desc.\nIW1 · ISCE2 + MintPy · PS+DS\n"
        "Clip AOI: our own approximation (district union),\nnot the paper's published polygon")
    build_legend_panel(axes.flat[3], cmap, norm, bin_labels, district_keys=district_keys,
                       aoi_label=args.aoi_label, footer_text=footer_text,
                       show_district_boundary=(admin_json is not None))

    title = args.title or ('Vertical Land Motion — Beijing IW1 (Chaoyang / Tongzhou / Daxing)\n'
                           'PS + DS, Sentinel-1 track 47 descending')
    fig.suptitle(title, fontsize=14, y=0.965)
    plt.subplots_adjust(top=0.88, bottom=0.06, left=0.05, right=0.98,
                        hspace=0.22, wspace=0.12)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / args.outname
    plt.savefig(out, dpi=args.dpi, bbox_inches='tight', facecolor='white')
    print(f'Saved -> {out}')


if __name__ == '__main__':
    main()
