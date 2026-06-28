"""
Consolidated end-to-end validation -- the 12 checks listed in the task
spec, run as one script instead of twelve. Each check is independent;
a failure in an earlier stage doesn't block later ones from reporting
their own status, so a single run shows how far the pipeline got.

Usage:
    python validate_pipeline.py \
        --slc-dir <ephemeral>/data/raw/slc \
        --dem-dir <ephemeral>/data/raw/dem \
        --isce-work-dir <ephemeral>/data/processed/isce2 \
        --mintpy-dir <ephemeral>/data/mintpy_outputs \
        --exports-dir exports
"""

import argparse
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np

SCRIPT_DIR = Path(__file__).parent


def run_check(name: str, fn):
    try:
        ok, msg = fn()
    except Exception as e:  # noqa: BLE001 -- want every check to report, not crash the run
        ok, msg = False, f"exception: {e}"
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {msg}")
    return ok


def run_subprocess_check(cmd: list) -> tuple:
    result = subprocess.run(cmd, capture_output=True, text=True)
    msg = (result.stdout or result.stderr).strip().splitlines()
    msg = msg[-1] if msg else f"exit code {result.returncode}"
    return result.returncode == 0, msg


def check_slc_consistency(slc_dir: Path) -> tuple:
    return run_subprocess_check([
        sys.executable, str(SCRIPT_DIR.parent / "isce2" / "check_stack_metadata.py"),
        "--slc-dir", str(slc_dir), "--out", "/tmp/stack_inventory_check.csv",
    ])


def check_burst_coverage(isce_work_dir: Path) -> tuple:
    reference_dir = isce_work_dir / "reference"
    if not reference_dir.is_dir():
        return False, f"no {reference_dir}"
    # dirs only -- reference/ also has a sibling IW1.xml file alongside the
    # IW1/ directory, which glob("IW*") would otherwise double-count
    swaths = [s for s in reference_dir.glob("IW*") if s.is_dir()]
    n_bursts = sum(len(list(s.glob("burst_*.slc.xml"))) for s in swaths)
    return n_bursts > 0, f"{n_bursts} burst(s) across {len(swaths)} swath(s)"


def check_dem_coverage(dem_dir: Path) -> tuple:
    dem_files = list(dem_dir.glob("*.dem"))
    if not dem_files:
        return False, f"no .dem file in {dem_dir}"
    xml = dem_files[0].with_suffix(dem_files[0].suffix + ".xml")
    return xml.exists(), f"{dem_files[0].name} ({'has' if xml.exists() else 'missing'} .xml metadata)"


def check_coregistration_exists(isce_work_dir: Path) -> tuple:
    coreg_dir = isce_work_dir / "coreg_secondarys"
    if not coreg_dir.is_dir():
        return False, f"no {coreg_dir}"
    n = len(list(coreg_dir.iterdir()))
    return n > 0, f"{n} coregistered secondary date(s)"


def check_ifgram_count(isce_work_dir: Path) -> tuple:
    ifg_dir = isce_work_dir / "merged" / "interferograms"
    if not ifg_dir.is_dir():
        return False, f"no {ifg_dir}"
    n = len([d for d in ifg_dir.iterdir() if d.is_dir()])
    return n > 0, f"{n} interferogram pair(s)"


def check_coherence_maps(isce_work_dir: Path) -> tuple:
    ifg_dir = isce_work_dir / "merged" / "interferograms"
    if not ifg_dir.is_dir():
        return False, f"no {ifg_dir}"
    n = len(list(ifg_dir.glob("*/filt_fine.cor")))
    return n > 0, f"{n} coherence map(s)"


def check_unwrapped_phase(isce_work_dir: Path) -> tuple:
    ifg_dir = isce_work_dir / "merged" / "interferograms"
    if not ifg_dir.is_dir():
        return False, f"no {ifg_dir}"
    n = len(list(ifg_dir.glob("*/filt_fine.unw")))
    return n > 0, f"{n} unwrapped phase file(s)"


def check_geometry_dims(isce_work_dir: Path) -> tuple:
    return run_subprocess_check([
        sys.executable, str(SCRIPT_DIR.parent / "isce2" / "check_geometry.py"),
        "--work-dir", str(isce_work_dir),
    ])


def check_mintpy_loads(mintpy_dir: Path) -> tuple:
    return run_subprocess_check([
        sys.executable, str(SCRIPT_DIR.parent / "mintpy" / "check_mintpy_load.py"),
        "--mintpy-dir", str(mintpy_dir),
    ])


def check_ps_mask_valid(mintpy_dir: Path) -> tuple:
    mask_file = mintpy_dir / "masks" / "mask_ps_like.h5"
    if not mask_file.exists():
        return False, f"no {mask_file}"
    with h5py.File(mask_file, "r") as f:
        mask = f["mask"][:]
    frac = mask.mean()
    return frac > 0.001, f"{int(mask.sum())}/{mask.size} valid pixels ({frac:.2%})"


def check_velocity_nonempty(mintpy_dir: Path) -> tuple:
    velocity_file = mintpy_dir / "velocity.h5"
    if not velocity_file.exists():
        return False, f"no {velocity_file}"
    with h5py.File(velocity_file, "r") as f:
        vel = f["velocity"][:]
    finite = np.isfinite(vel) & (vel != 0)
    return bool(finite.any()), f"{int(finite.sum())}/{vel.size} non-zero finite pixels"


def check_timeseries_extraction(exports_dir: Path) -> tuple:
    csv_path = exports_dir / "timeseries_points.csv"
    if not csv_path.exists():
        return False, f"no {csv_path}"
    import pandas as pd
    df = pd.read_csv(csv_path)
    required_cols = {"row", "col", "date", "displacement_mm"}
    if not required_cols.issubset(df.columns):
        return False, f"missing columns, has {set(df.columns)}"
    n_pixels = df[["row", "col"]].drop_duplicates().shape[0]
    return len(df) > 0 and n_pixels > 0, f"{n_pixels} pixel(s), {len(df)} row(s)"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slc-dir", required=True)
    ap.add_argument("--dem-dir", required=True)
    ap.add_argument("--isce-work-dir", required=True)
    ap.add_argument("--mintpy-dir", required=True)
    ap.add_argument("--exports-dir", required=True)
    args = ap.parse_args()

    slc_dir, dem_dir = Path(args.slc_dir), Path(args.dem_dir)
    isce_work_dir, mintpy_dir, exports_dir = Path(args.isce_work_dir), Path(args.mintpy_dir), Path(args.exports_dir)

    checks = [
        ("1. SLC consistency", lambda: check_slc_consistency(slc_dir)),
        ("2. Burst coverage", lambda: check_burst_coverage(isce_work_dir)),
        ("3. DEM coverage", lambda: check_dem_coverage(dem_dir)),
        ("4. Coregistration output exists", lambda: check_coregistration_exists(isce_work_dir)),
        ("5. Interferogram count reasonable", lambda: check_ifgram_count(isce_work_dir)),
        ("6. Coherence maps exist", lambda: check_coherence_maps(isce_work_dir)),
        ("7. Unwrapped phase exists", lambda: check_unwrapped_phase(isce_work_dir)),
        ("8. Geometry dims match interferograms", lambda: check_geometry_dims(isce_work_dir)),
        ("9. MintPy HDF5 files load", lambda: check_mintpy_loads(mintpy_dir)),
        ("10. PS-like mask has enough valid pixels", lambda: check_ps_mask_valid(mintpy_dir)),
        ("11. Velocity map is not empty", lambda: check_velocity_nonempty(mintpy_dir)),
        ("12. Time-series extraction works", lambda: check_timeseries_extraction(exports_dir)),
    ]

    results = [run_check(name, fn) for name, fn in checks]
    n_pass = sum(results)
    print(f"\n{n_pass}/{len(results)} checks passed")
    sys.exit(0 if n_pass == len(results) else 1)


if __name__ == "__main__":
    main()
