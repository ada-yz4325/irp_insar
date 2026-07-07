"""
Generate three VLM basemaps from sub-period velocity GeoTIFFs.

Expected inputs in EXPORTS_DIR:
    velocity_2016-2019.tif
    velocity_2020-2021.tif
    velocity_2016-2021.tif

Usage:
    python generate_three_vlm_maps.py \\
        --exports-dir exports_beijing_iw2_2016_2021 \\
        --bbox "115.80 116.52 39.65 40.10" \\
        --outdir figures \\
        --dpi 200
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLOT_SCRIPT = REPO_ROOT / 'scripts' / 'mintpy' / 'plot_vlm_basemap.py'


PERIODS = [
    ('2016-2019', 'Oct 2016 – Dec 2019', -40, 5),
    ('2020-2021', 'Jan 2020 – Nov 2021', -40, 5),
    ('2016-2021', 'Oct 2016 – Nov 2021', -40, 5),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--exports-dir', required=True)
    ap.add_argument('--bbox',        default='115.80 116.52 39.65 40.10')
    ap.add_argument('--outdir',      default=str(REPO_ROOT / 'figures'))
    ap.add_argument('--dpi',         type=int, default=200)
    args = ap.parse_args()

    edir = Path(args.exports_dir)

    for label, period_str, vmin, vmax in PERIODS:
        tif = edir / f'velocity_{label}.tif'
        if not tif.exists():
            print(f'WARNING: {tif} not found — skipping', file=sys.stderr)
            continue

        outname = f'vlm_beijing_iw2_{label}.png'
        print(f'\n--- {label} ({period_str}) ---')
        subprocess.run([
            sys.executable, str(PLOT_SCRIPT),
            '--input',   str(tif),
            '--label',   f'Beijing IW2',
            '--outname', outname,
            '--bbox',    args.bbox,
            '--period',  period_str,
            '--vmin',    str(vmin),
            '--vmax',    str(vmax),
            '--dpi',     str(args.dpi),
            '--outdir',  args.outdir,
        ], check=True)
        print(f'  → figures/{outname}')

    print('\n=== Three VLM maps complete ===')
    print(f'figures/vlm_beijing_iw2_2016-2019.png')
    print(f'figures/vlm_beijing_iw2_2020-2021.png')
    print(f'figures/vlm_beijing_iw2_2016-2021.png')


if __name__ == '__main__':
    main()
