"""
Generate three paper-quality VLM basemaps from sub-period velocity GeoTIFFs.

Expected inputs in EXPORTS_DIR:
    velocity_2016-2019.tif
    velocity_2020-2021.tif
    velocity_2016-2021.tif

Usage:
    python generate_three_vlm_maps.py \\
        --exports-dir exports_beijing_iw2_2016_2021 \\
        --bbox "115.80 116.52 39.65 40.10" \\
        --outdir figures \\
        --dpi 300
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLOT_SCRIPT = REPO_ROOT / 'scripts' / 'mintpy' / 'plot_vlm_basemap.py'


# Per-period settings: (label, period_str, vmin, vmax, std_max_mm)
# vmin/vmax tuned to the actual data distributions:
#   2016-2019: p2=-36.8 med=-0.8 p98=5.3 → show -15 to +5 (highlights urban gradient)
#   2020-2021: p2=-57.1 med=-23.4 p98=-10.6 → show -60 to 0 (heavy subsidence period)
#   2016-2021: p2=-42.0 med=-8.6 p98=-3.3 → show -40 to +5 (full-period summary)
PERIODS = [
    ('2016-2019', 'Oct 2016 – Dec 2019', -15,  5, 6.0),
    ('2020-2021', 'Jan 2020 – Nov 2021', -60,  5, 20.0),
    ('2016-2021', 'Oct 2016 – Nov 2021', -40,  5, 5.0),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--exports-dir', required=True)
    ap.add_argument('--bbox',   default='115.80 116.52 39.65 40.10')
    ap.add_argument('--outdir', default=str(REPO_ROOT / 'figures'))
    ap.add_argument('--dpi',    type=int, default=300)
    ap.add_argument('--filter', type=int, default=3,
                    help='Spatial median-filter size (default 3)')
    args = ap.parse_args()

    edir = Path(args.exports_dir)

    for label, period_str, vmin, vmax, std_max in PERIODS:
        tif = edir / f'velocity_{label}.tif'
        if not tif.exists():
            print(f'WARNING: {tif} not found — skipping', file=sys.stderr)
            continue

        outname = f'vlm_beijing_iw2_{label}.png'
        print(f'\n--- {label} ({period_str}) ---')
        cmd = [
            sys.executable, str(PLOT_SCRIPT),
            '--input',   str(tif),
            '--label',   'Beijing IW2',
            '--outname', outname,
            '--bbox',    args.bbox,
            '--period',  period_str,
            '--vmin',    str(vmin),
            '--vmax',    str(vmax),
            '--cmap',    'RdYlBu',
            '--filter',  str(args.filter),
            '--dpi',     str(args.dpi),
            '--outdir',  args.outdir,
        ]
        subprocess.run(cmd, check=True)
        print(f'  → figures/{outname}')

    print('\n=== Three VLM maps complete ===')


if __name__ == '__main__':
    main()
