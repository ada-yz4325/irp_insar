#!/usr/bin/env python3
"""
Temporal baseline vs. perpendicular baseline scatter — one point per
interferogram pair, colored by that pair's average spatial coherence.
Complements plot_baseline_network.py: the network diagram puts acquisition
date on the x-axis (temporal baseline is only implicit as the horizontal
span between two connected nodes); this plot puts temporal baseline (Btemp,
days) directly on its own axis so the network's temporal-baseline
distribution is explicit rather than implied.

Usage:
    python plot_baseline_scatter.py \\
        --mintpy-dir /path/to/mintpy_outputs_iw1_2016_2021 \\
        --label iw1_2016-2021 \\
        --outdir figures
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mintpy-dir', required=True,
                   help='MintPy work dir (contains coherenceSpatialAvg.txt)')
    p.add_argument('--label',  default='network')
    p.add_argument('--outdir', default=str(REPO_ROOT / 'figures'))
    p.add_argument('--vlim',   type=float, nargs=2, default=[0.2, 1.0])
    p.add_argument('--dpi',    type=int, default=200)
    return p.parse_args()


def main():
    args = parse_args()
    coh_file = Path(args.mintpy_dir) / 'coherenceSpatialAvg.txt'
    if not coh_file.exists():
        raise SystemExit(f'Missing: {coh_file}')

    btemp, bperp, coh = [], [], []
    with open(coh_file) as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.split()
            coh.append(float(parts[1]))
            btemp.append(float(parts[2]))
            bperp.append(float(parts[3]))
    btemp, bperp, coh = np.array(btemp), np.array(bperp), np.array(coh)
    print(f'{len(btemp)} pairs  |  Btemp: {btemp.min():.0f}-{btemp.max():.0f} days'
          f'  |  Bperp: {bperp.min():.1f}-{bperp.max():.1f} m')

    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=args.dpi)
    vmin, vmax = args.vlim
    sc = ax.scatter(btemp, bperp, c=coh, cmap='jet', vmin=vmin, vmax=vmax,
                    s=26, edgecolor='black', linewidth=0.3, alpha=0.85, zorder=3)

    ax.axhline(0, color='#999999', linewidth=0.8, zorder=1)
    ax.set_xlabel('Temporal Baseline [days]', fontsize=12)
    ax.set_ylabel('Perpendicular Baseline [m]', fontsize=12)
    ax.set_xlim(left=0)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    ax.tick_params(labelsize=11)

    # unique Btemp values actually present, as a light rug on the x-axis --
    # makes the sequential-network cadence (12/24/36... day steps) legible
    uniq = sorted(set(btemp.tolist()))
    ax.set_xticks(uniq[::max(1, len(uniq) // 12)])

    cbar = fig.colorbar(sc, ax=ax, pad=0.02)
    cbar.set_label('Average Spatial Coherence', fontsize=11)

    ax.set_title(f'Interferogram Pairs — Temporal vs. Perpendicular Baseline\n'
                f'n={len(btemp)} pairs', fontsize=12)

    plt.tight_layout()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    out = outdir / f'baseline_scatter_{args.label}.png'
    plt.savefig(out, dpi=args.dpi, facecolor='white')
    print(f'Saved -> {out}')


if __name__ == '__main__':
    main()
