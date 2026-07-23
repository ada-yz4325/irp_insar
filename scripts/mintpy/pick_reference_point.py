"""
Pick a MintPy reference point that is guaranteed valid for bridging/phase-
closure unwrap-error correction across the WHOLE stack, not just "looks
coherent on average."

Why this exists: MintPy's own reference_point.py auto-pick (method=
maxCoherence) validates candidates against a much weaker mask -- pixels
with non-NaN, non-zero temporal-average phase -- explicitly NOT
maskConnComp.h5 (see reference_point.py's reference_file(), comment: "did
not use maskConnComp.h5 because not all input dataset has connectComponent
info"). That is not strong enough to guarantee the point survives bridging,
which needs the reference pixel to have a valid (nonzero) connectComponent
in EVERY SINGLE interferogram -- exactly what maskConnComp.h5 encodes.
Discovered the hard way on the Beijing IW1 stack (4 attempts before this
method: naive auto-pick, paper's published coordinate, coherence-argmax
alone all failed downstream in bridging/reference_point).

Method: intersect maskConnComp.h5 (bool, nonzero connectComponent in ALL
interferograms) with avgSpatialCoh.h5 (mean coherence), take argmax
coherence among qualifying pixels, convert to lat/lon via the geometry
lookup tables (lat.rdr/lon.rdr, or geometryRadar.h5 if already loaded).

Usage:
    python pick_reference_point.py --mintpy-dir DIR --lookup-lat FILE --lookup-lon FILE
    python pick_reference_point.py --mintpy-dir DIR   # uses inputs/geometryRadar.h5
"""
import argparse

import h5py
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mintpy-dir", required=True)
    ap.add_argument("--sub-box", type=float, nargs=4, default=None,
                     metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"),
                     help="restrict the search to this lat/lon sub-box (optional)")
    args = ap.parse_args()

    mask_file = f"{args.mintpy_dir}/maskConnComp.h5"
    coh_file = f"{args.mintpy_dir}/avgSpatialCoh.h5"
    geom_file = f"{args.mintpy_dir}/inputs/geometryRadar.h5"

    with h5py.File(mask_file) as f:
        mask = f["mask"][:]
    with h5py.File(coh_file) as f:
        coh = f["coherence"][:] if "coherence" in f else f[list(f.keys())[0]][:]

    print(f"maskConnComp: {mask.sum()} / {mask.size} pixels ({100*mask.sum()/mask.size:.2f}%) connected in ALL interferograms")

    valid = mask.copy()

    lat = lon = None
    with h5py.File(geom_file) as f:
        if "latitude" in f and "longitude" in f:
            lat = f["latitude"][:]
            lon = f["longitude"][:]

    if args.sub_box is not None and lat is not None:
        lat_min, lat_max, lon_min, lon_max = args.sub_box
        in_box = (lat >= lat_min) & (lat <= lat_max) & (lon >= lon_min) & (lon <= lon_max)
        valid = valid & in_box
        print(f"restricted to sub-box: {valid.sum()} candidate pixels remain")

    coh_masked = np.where(valid, coh, -1)
    y, x = np.unravel_index(np.argmax(coh_masked), coh_masked.shape)
    best_coh = coh[y, x]

    print(f"\nBest reference pixel: Y={y}, X={x}, coherence={best_coh:.4f}")
    print(f"maskConnComp[{y},{x}] = {mask[y, x]}")

    if lat is not None:
        ref_lat, ref_lon = lat[y, x], lon[y, x]
        print(f"REF_LAT={ref_lat:.6f}, REF_LON={ref_lon:.6f}")
        print(f"\nmintpy.reference.lalo = {ref_lat:.5f}, {ref_lon:.5f}")
    else:
        print("No geometryRadar.h5 lat/lon found -- report Y/X only:")
        print(f"mintpy.reference.yx = {y}, {x}")


if __name__ == "__main__":
    main()
