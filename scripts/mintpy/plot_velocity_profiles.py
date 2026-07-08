"""
Extract and plot N-S and E-W velocity profiles from VLM GeoTIFFs.

For each profile line, samples all valid pixels within a half-width band,
then plots median + IQR envelope vs distance. Compares all three periods
on the same axes for easy period-to-period comparison.

Usage:
    python plot_velocity_profiles.py \\
        --exports-dir exports_beijing_iw2_2016_2021 \\
        --outdir      figures \\
        --dpi         250
"""
import argparse
import os
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import rasterio
import rasterio.transform

REPO_ROOT = Path(__file__).resolve().parents[2]


# ─── Profile definitions (centre-lon, centre-lat, orientation) ───────────────
PROFILES = {
    'NS': {
        'lon': 116.25,          # N-S profile along 116.25°E (central Beijing)
        'half_width_deg': 0.05, # ±0.05° longitude band (~5 km)
        'axis': 'lat',
    },
    'EW': {
        'lat': 39.90,           # E-W profile along 39.90°N (through city centre)
        'half_width_deg': 0.03, # ±0.03° latitude band (~3 km)
        'axis': 'lon',
    },
}

PERIOD_STYLES = {
    '2016-2021': dict(color='#2166ac', lw=2.0, zorder=4, label='2016–2021 (5 yr)'),
    '2016-2019': dict(color='#4dac26', lw=1.5, zorder=3, label='2016–2019'),
    '2020-2021': dict(color='#d01c8b', lw=1.5, zorder=3, label='2020–2021'),
}


def load_tif_as_scatter(path):
    """Return (lons, lats, vel_mm) arrays for all valid pixels."""
    with rasterio.open(path) as src:
        vel = src.read(1).astype(np.float64)
        nodata = src.nodata
        tf = src.transform

    if nodata is not None:
        vel[vel == nodata] = np.nan
    vel[vel == 0] = np.nan
    vel_mm = vel * 1000.0

    ri, ci = np.where(np.isfinite(vel_mm))
    xs, ys = rasterio.transform.xy(tf, ri.tolist(), ci.tolist())
    lons = np.array(xs, np.float32)
    lats = np.array(ys, np.float32)
    vals = vel_mm[ri, ci].astype(np.float32)
    return lons, lats, vals


def extract_profile(lons, lats, vals, profile_def, n_bins=40):
    """Return (dist_km, medians, q25, q75) along the profile."""
    from pyproj import Geod
    geod = Geod(ellps='WGS84')

    if profile_def['axis'] == 'lat':
        centre_lon = profile_def['lon']
        hw = profile_def['half_width_deg']
        inbox = (lons >= centre_lon - hw) & (lons <= centre_lon + hw) & np.isfinite(vals)
        axis_vals = lats[inbox]
        vv = vals[inbox]
        # Convert latitude to km distance from southern end
        lat_ref = axis_vals.min()
        _, _, dist = geod.inv(
            np.full_like(axis_vals, centre_lon), np.full_like(axis_vals, lat_ref),
            np.full_like(axis_vals, centre_lon), axis_vals)
        dist_km = dist / 1000.0
        xlabel = 'Latitude (°N)'
    else:
        centre_lat = profile_def['lat']
        hw = profile_def['half_width_deg']
        inbox = (lats >= centre_lat - hw) & (lats <= centre_lat + hw) & np.isfinite(vals)
        axis_vals = lons[inbox]
        vv = vals[inbox]
        lon_ref = axis_vals.min()
        _, _, dist = geod.inv(
            np.full_like(axis_vals, lon_ref), np.full_like(axis_vals, centre_lat),
            axis_vals,                         np.full_like(axis_vals, centre_lat))
        dist_km = dist / 1000.0
        xlabel = 'Longitude (°E)'

    if len(vv) < 10:
        return None, None, None, None, xlabel

    # Bin the profile
    bin_edges = np.linspace(dist_km.min(), dist_km.max(), n_bins + 1)
    bin_mid = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    medians = np.full(n_bins, np.nan)
    q25     = np.full(n_bins, np.nan)
    q75     = np.full(n_bins, np.nan)

    for i in range(n_bins):
        m = (dist_km >= bin_edges[i]) & (dist_km < bin_edges[i+1])
        if m.sum() >= 3:
            medians[i] = np.median(vv[m])
            q25[i]     = np.percentile(vv[m], 25)
            q75[i]     = np.percentile(vv[m], 75)

    return bin_mid, medians, q25, q75, xlabel


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--exports-dir', required=True)
    ap.add_argument('--outdir',  default=str(REPO_ROOT / 'figures'))
    ap.add_argument('--dpi',     type=int, default=250)
    args = ap.parse_args()

    edir = Path(args.exports_dir)
    os.makedirs(args.outdir, exist_ok=True)

    # Load all three period TIFs
    data = {}
    for label in ['2016-2021', '2016-2019', '2020-2021']:
        tif = edir / f'velocity_{label}.tif'
        if not tif.exists():
            print(f'WARNING: {tif} not found — skipping {label}')
            continue
        print(f'Loading {tif.name} …')
        data[label] = load_tif_as_scatter(tif)

    if not data:
        print('No TIFs found — exiting')
        return

    # One figure with 2 rows (NS / EW), columns for each profile
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=args.dpi)
    fig.suptitle('VLM Velocity Profiles — Beijing IW2 (Sentinel-1)',
                 fontsize=13, fontweight='bold', y=1.01)

    for ax, (pname, pdef) in zip(axes, PROFILES.items()):
        has_data = False
        for label, (lons, lats, vals) in data.items():
            dist, med, q25, q75, xlabel = extract_profile(lons, lats, vals, pdef)
            if dist is None:
                continue
            sty = PERIOD_STYLES.get(label, {})
            valid = np.isfinite(med)
            ax.plot(dist[valid], med[valid], **sty)
            ax.fill_between(dist[valid], q25[valid], q75[valid],
                            alpha=0.15, color=sty['color'])
            has_data = True

        ax.axhline(0, color='k', lw=0.8, ls='--', alpha=0.5)
        ax.set_xlabel(f'Distance along profile (km)\n({xlabel})', fontsize=10)
        ax.set_ylabel('Vertical velocity (mm/yr)', fontsize=10)
        ax.tick_params(labelsize=9)
        ax.grid(True, alpha=0.3, linestyle='--')

        if pname == 'NS':
            title = f'N–S Profile  (lon ≈ {pdef["lon"]:.2f}°E ± {pdef["half_width_deg"]:.2f}°)'
            ax.set_title(title, fontsize=10, pad=6)
        else:
            title = f'E–W Profile  (lat ≈ {pdef["lat"]:.2f}°N ± {pdef["half_width_deg"]:.2f}°)'
            ax.set_title(title, fontsize=10, pad=6)

        if has_data:
            ax.legend(fontsize=8.5, loc='lower right', framealpha=0.8)

    plt.tight_layout()
    out = os.path.join(args.outdir, 'vlm_profiles_beijing_iw2.png')
    plt.savefig(out, dpi=args.dpi, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved → {out}')


if __name__ == '__main__':
    main()
