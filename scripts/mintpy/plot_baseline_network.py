#!/usr/bin/env python3
"""
Interferogram network diagram — perpendicular baseline vs. acquisition time,
pairs colored by average spatial coherence.

Plain dark circular nodes (one per SAR acquisition, network-adjusted perp
baseline from MintPy's own least-squares baseline history) connected by
lines colored on a jet colormap by that pair's mean spatial coherence
(from coherenceSpatialAvg.txt). Deliberately minimal styling — no split/
truncated colormap, no marker coloring — to match a plain dots-and-lines
reference figure rather than MintPy's own plot_network.py defaults.

Usage:
    python plot_baseline_network.py \\
        --mintpy-dir /path/to/mintpy_outputs_iw1_2016_2021 \\
        --label iw1_2016-2021 \\
        --outdir figures
"""
import argparse
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mintpy-dir', required=True,
                   help='MintPy work dir (contains inputs/ifgramStack.h5 and coherenceSpatialAvg.txt)')
    p.add_argument('--label',   default='network',
                   help='Used in the output filename: network_<label>.png')
    p.add_argument('--outdir',  default=str(REPO_ROOT / 'figures'))
    p.add_argument('--vlim',    type=float, nargs=2, default=[0.2, 1.0],
                   help='Coherence color-scale limits (default: 0.2 1.0)')
    p.add_argument('--dpi',     type=int, default=200)
    return p.parse_args()


def main():
    args = parse_args()
    from mintpy.objects.stack import ifgramStack

    mdir = Path(args.mintpy_dir)
    stack_file = mdir / 'inputs' / 'ifgramStack.h5'
    coh_file = mdir / 'coherenceSpatialAvg.txt'
    for f in (stack_file, coh_file):
        if not f.exists():
            raise SystemExit(f'Required file missing: {f}')

    stack = ifgramStack(str(stack_file))
    stack.open(print_msg=False)
    date_list = stack.dateList
    pbase_list = stack.get_perp_baseline_timeseries(dropIfgram=True)
    pbase_of = dict(zip(date_list, pbase_list))
    dt_of = {d: datetime.strptime(d, '%Y%m%d') for d in date_list}

    pairs = []
    with open(coh_file) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.split()
            d1, d2 = parts[0].split('_')
            pairs.append((d1, d2, float(parts[1])))
    print(f'{len(date_list)} acquisitions, {len(pairs)} pairs')

    fig, ax = plt.subplots(figsize=(9, 5), dpi=args.dpi)
    cmap = plt.get_cmap('jet')
    vmin, vmax = args.vlim
    norm = matplotlib.colors.Normalize(vmin=vmin, vmax=vmax)

    for d1, d2, coh in sorted(pairs, key=lambda p: p[2]):
        if d1 not in dt_of or d2 not in dt_of:
            continue
        ax.plot([dt_of[d1], dt_of[d2]], [pbase_of[d1], pbase_of[d2]],
                '-', color=cmap(norm(coh)), linewidth=0.7, alpha=0.85, zorder=2)

    xs = [dt_of[d] for d in date_list]
    ys = [pbase_of[d] for d in date_list]
    ax.scatter(xs, ys, s=36, facecolor='#2b2b2b', edgecolor='black', linewidth=0.6, zorder=3)

    # Tight x-limits with a small, honest margin -- matplotlib's default 5%
    # autoscale margin was stretching the axis visibly past the real
    # first/last acquisition dates (e.g. into the next year).
    from datetime import timedelta
    pad = timedelta(days=15)
    ax.set_xlim(min(xs) - pad, max(xs) + pad)

    ax.set_ylabel('Perp Baseline [m]', fontsize=12)
    ax.set_xlabel('Acquisition Period', fontsize=12)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.tick_params(labelsize=11)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    ax.grid(False)

    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02)
    cbar.set_label('Average Spatial Coherence', fontsize=11)

    plt.tight_layout()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f'network_{args.label}.png'
    plt.savefig(out, dpi=args.dpi, facecolor='white')
    print(f'Saved -> {out}')


if __name__ == '__main__':
    main()
