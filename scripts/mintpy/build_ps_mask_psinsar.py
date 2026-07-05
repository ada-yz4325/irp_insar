#!/usr/bin/env python3
"""
Build PS mask from dual-condition selection (matches Zhou et al. 2024 paper):
    ADI  <= 0.56   (from compute_adi_psinsar.py)
    ACC  >= 0.72   (temporalCoherence from MintPy, equivalent to paper's ACC)

Saves mask_ps_psinsar.h5 in the MintPy working directory.

Usage:
    python build_ps_mask_psinsar.py \\
        --adi      data/mintpy_outputs_psinsar/adi_psinsar.npy \\
        --mintpy   data/mintpy_outputs_psinsar \\
        --adi-thr  0.56 \\
        --acc-thr  0.72
"""
import argparse, os, sys
import numpy as np
import h5py

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--adi',     required=True,
                   help='ADI .npy file from compute_adi_psinsar.py')
    p.add_argument('--mintpy',  required=True,
                   help='MintPy output directory (contains temporalCoherence.h5)')
    p.add_argument('--adi-thr', type=float, default=0.56,
                   help='ADI threshold — keep pixels ≤ this (default: 0.56)')
    p.add_argument('--acc-thr', type=float, default=0.72,
                   help='Temporal coherence threshold — keep pixels ≥ this (default: 0.72)')
    p.add_argument('--outdir',  default=None,
                   help='Output directory (default: same as --mintpy)')
    return p.parse_args()


def main():
    args = parse_args()
    outdir = args.outdir or args.mintpy

    # --- Load ADI ---
    print(f"Loading ADI: {args.adi}")
    adi = np.load(args.adi)
    print(f"  shape: {adi.shape}  ADI ≤ {args.adi_thr}: "
          f"{np.sum(adi <= args.adi_thr):,} pixels")

    # --- Load temporal coherence from MintPy ---
    tc_path = os.path.join(args.mintpy, 'temporalCoherence.h5')
    if not os.path.exists(tc_path):
        sys.exit(f"ERROR: temporalCoherence.h5 not found at {tc_path}\n"
                 f"       Run MintPy invert_network step first.")
    print(f"Loading temporalCoherence: {tc_path}")
    with h5py.File(tc_path, 'r') as f:
        tc = f['temporalCoherence'][:]
    print(f"  shape: {tc.shape}  ACC ≥ {args.acc_thr}: "
          f"{np.sum(tc >= args.acc_thr):,} pixels")

    # --- Spatial alignment check ---
    if adi.shape != tc.shape:
        sys.exit(f"ERROR: Shape mismatch — ADI {adi.shape} vs temporalCoherence {tc.shape}\n"
                 f"       Ensure compute_adi_psinsar.py and MintPy used the same ISCE2 workdir.")

    # --- Build dual-condition mask ---
    mask_adi = (adi <= args.adi_thr)
    mask_acc = (tc  >= args.acc_thr)
    mask_ps  = mask_adi & mask_acc & ~np.isnan(adi)

    total   = adi.size
    n_adi   = mask_adi.sum()
    n_acc   = mask_acc.sum()
    n_ps    = mask_ps.sum()
    density = n_ps / (total * (20e-3 * 20e-3))  # approx: 20m pixel → per km²
    print(f"\nPS selection results:")
    print(f"  ADI ≤ {args.adi_thr}          : {n_adi:>10,}  ({100*n_adi/total:.1f}%)")
    print(f"  ACC ≥ {args.acc_thr}          : {n_acc:>10,}  ({100*n_acc/total:.1f}%)")
    print(f"  Both (PS mask)       : {n_ps:>10,}  ({100*n_ps/total:.1f}%)")
    print(f"  Approx PS density    : {density:.0f} pts/km²  "
          f"(paper achieved 838 pts/km²)")

    # --- Save mask as MintPy-compatible HDF5 ---
    out_path = os.path.join(outdir, 'mask_ps_psinsar.h5')
    with h5py.File(tc_path, 'r') as src, h5py.File(out_path, 'w') as dst:
        # Copy metadata from temporalCoherence.h5
        for key, val in src.attrs.items():
            dst.attrs[key] = val
        dst.create_dataset('mask', data=mask_ps.astype(np.uint8),
                           chunks=True, compression='gzip')
        dst['mask'].attrs['description'] = (
            f'PS mask: ADI<={args.adi_thr} AND temporalCoherence>={args.acc_thr}  '
            f'(Zhou et al. 2024 RS 16(9) 1528)'
        )

    print(f"\nSaved → {out_path}")
    print(f"\nNext: use this mask in run_mintpy_psinsar.sh via:")
    print(f"  maskpy.py -f velocity.h5 -m {out_path}")


if __name__ == '__main__':
    main()
