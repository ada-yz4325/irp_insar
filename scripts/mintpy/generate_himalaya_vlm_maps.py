"""
Generate the six PS-only vs PS+DS comparison VLM maps for the Himalaya /
Everest AOI (3 periods x 2 mask types), mirroring the Beijing IW1
generate_three_vlm_maps.py pattern but for this region's own period split
and value range.

Expected inputs:
    exports_himalaya_everest_ps_only/velocity_<period>.tif
    exports_himalaya_everest_ps_ds/velocity_<period>.tif

vmin/vmax are shared between the PS-only and PS+DS map of the SAME period
(so the color scale doesn't shift when comparing the two side by side --
that's the whole point of the comparison), but differ across periods to
match each period's own value spread (2020-2022, 2022-2024, 2024-2026:
p2/p98 of -42/+12, -37/+22, -64/+25 mm/yr respectively -- period 3 has a
notably larger negative tail).

Usage:
    python generate_himalaya_vlm_maps.py \\
        --ps-only-dir exports_himalaya_everest_ps_only \\
        --ps-ds-dir   exports_himalaya_everest_ps_ds \\
        --bbox "83.6967 84.9545 28.2255 29.0051" \\
        --outdir figures/himalaya_everest
"""
import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLOT_SCRIPT = REPO_ROOT / 'scripts' / 'mintpy' / 'plot_vlm_basemap.py'

# (label, period_str, vmin, vmax)
PERIODS = [
    ('2020-2022', 'Mar 2020 – Apr 2022', -45, 15),
    ('2022-2024', 'Apr 2022 – Apr 2024', -40, 25),
    ('2024-2026', 'Apr 2024 – Jun 2026', -65, 30),
]

REF_DESC = 'maskConnComp-validated point, 29.005N 84.606E (bare rock, 5065m)'


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ps-only-dir', required=True)
    ap.add_argument('--ps-ds-dir', required=True)
    ap.add_argument('--bbox', default='83.6967 84.9545 28.2255 29.0051')
    ap.add_argument('--outdir', default=str(REPO_ROOT / 'figures' / 'himalaya_everest'))
    ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--filter', type=int, default=3)
    args = ap.parse_args()

    for mask_type, edir, subtitle in [
        ('ps_only', Path(args.ps_only_dir), 'Sentinel-1 IW2+IW3 PS-only'),
        ('ps_ds',   Path(args.ps_ds_dir),   'Sentinel-1 IW2+IW3 PS+DS'),
    ]:
        for label, period_str, vmin, vmax in PERIODS:
            tif = edir / f'velocity_{label}.tif'
            if not tif.exists():
                print(f'WARNING: {tif} not found — skipping', file=sys.stderr)
                continue

            outname = f'vlm_himalaya_{mask_type}_{label}.png'
            print(f'\n--- {mask_type} {label} ({period_str}) ---')
            cmd = [
                sys.executable, str(PLOT_SCRIPT),
                '--input',    str(tif),
                '--label',    'Himalaya (Everest AOI)',
                '--outname',  outname,
                '--bbox',     args.bbox,
                '--period',   period_str,
                '--vmin',     str(vmin),
                '--vmax',     str(vmax),
                '--cmap',     'RdYlBu',
                '--filter',   str(args.filter),
                '--dpi',      str(args.dpi),
                '--outdir',   args.outdir,
                '--no-admin',
                '--subtitle', subtitle,
                '--ref-desc', REF_DESC,
            ]
            subprocess.run(cmd, check=True)
            print(f'  -> {args.outdir}/{outname}')

    print('\n=== Six Himalaya VLM maps complete ===')


if __name__ == '__main__':
    main()
