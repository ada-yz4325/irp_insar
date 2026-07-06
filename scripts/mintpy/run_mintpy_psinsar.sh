#!/usr/bin/env bash
# MintPy PS-InSAR pipeline — Beijing, star network, dual-condition PS mask.
#
# Key differences from run_mintpy.sh (SBAS):
#   Stage 0  : compute_adi_psinsar.py   — ADI map from ISCE2 merged SLCs
#   Stage 10 : build_ps_mask_psinsar.py — ADI<=0.56 AND temporalCoherence>=0.72
#              (replaces build_ps_like_mask.py which uses coherence only)
#   MintPy   : weightFunc=no, network.type=star  (set in template config)
#
# Reference: Zhou et al. 2024, Remote Sensing 16(9), 1528
#
# Usage:
#   bash run_mintpy_psinsar.sh [template] [work_dir] [atmo_config] [isce_work_dir] [exports_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISCE2_CFG="$SCRIPT_DIR/../../configs/isce2/topsStack_psinsar.cfg"
TEMPLATE=${1:-"$SCRIPT_DIR/../../configs/mintpy/smallbaselineApp_psinsar.cfg"}
WORK_DIR=${2:-"$SCRIPT_DIR/../../data/mintpy_outputs_psinsar"}
ATMO_CONFIG=${3:-"$SCRIPT_DIR/../../configs/atmo_correction.yaml"}
ISCE_WORK_DIR=${4:-$(python3 -c "
import configparser
c = configparser.ConfigParser(inline_comment_prefixes=('#',))
c.read('$ISCE2_CFG')
print(c['topsStack']['workDir'])
")}
EXPORTS_DIR=${5:-"$SCRIPT_DIR/../../exports_beijing_psinsar"}
ATMO_SCRIPT="$SCRIPT_DIR/../../atmospheric_correction/apply_atmo_correction.py"

to_abs() { [[ "$1" = /* ]] && echo "$1" || echo "$PWD/$1"; }
TEMPLATE=$(to_abs "$TEMPLATE")
WORK_DIR=$(to_abs "$WORK_DIR")
ATMO_CONFIG=$(to_abs "$ATMO_CONFIG")
ISCE_WORK_DIR=$(to_abs "$ISCE_WORK_DIR")
EXPORTS_DIR=$(to_abs "$EXPORTS_DIR")

mkdir -p "$WORK_DIR" "$EXPORTS_DIR"
cd "$WORK_DIR"

echo "=== MintPy PS-InSAR pipeline ==="
echo "Template    : $TEMPLATE"
echo "Work dir    : $WORK_DIR"
echo "ISCE2 dir   : $ISCE_WORK_DIR"
echo "Exports dir : $EXPORTS_DIR"
echo "Start       : $(date)"

# --- Stage 0: ADI map (reads ISCE2 merged SLCs before MintPy touches anything) ---
echo "--- Stage 0: compute ADI from merged SLCs ---"
python3 "$SCRIPT_DIR/../isce2/compute_adi_psinsar.py" \
    --workdir  "$ISCE_WORK_DIR" \
    --outdir   "$WORK_DIR" \
    --chunk-rows 256

# --- Stages 1–6: standard MintPy load + network + inversion ---
smallbaselineApp.py "$TEMPLATE" --dostep load_data
smallbaselineApp.py "$TEMPLATE" --dostep modify_network
smallbaselineApp.py "$TEMPLATE" --dostep reference_point
smallbaselineApp.py "$TEMPLATE" --dostep quick_overview
smallbaselineApp.py "$TEMPLATE" --dostep correct_unwrap_error
smallbaselineApp.py "$TEMPLATE" --dostep invert_network

# --- Stage 10: PS mask — ADI<=0.56 AND temporalCoherence>=0.72 ---
echo "--- Stage 10: PS-InSAR dual-condition mask (Zhou et al. 2024) ---"
python3 "$SCRIPT_DIR/build_ps_mask_psinsar.py" \
    --adi     "$WORK_DIR/adi_psinsar.npy" \
    --mintpy  "$WORK_DIR" \
    --adi-thr 0.56 \
    --acc-thr 0.72

# --- Stages 11+: corrections and velocity ---
smallbaselineApp.py "$TEMPLATE" --dostep correct_LOD
smallbaselineApp.py "$TEMPLATE" --dostep correct_SET
smallbaselineApp.py "$TEMPLATE" --dostep correct_ionosphere

echo "--- Stage 11: atmospheric correction ---"
python3 "$ATMO_SCRIPT" \
    --timeseries "$WORK_DIR/timeseries.h5" \
    --mintpy-dir "$WORK_DIR" \
    --config     "$ATMO_CONFIG"
cp "$WORK_DIR/atmosphere/corrected_timeseries.h5" "$WORK_DIR/timeseries.h5"

smallbaselineApp.py "$TEMPLATE" --dostep deramp
smallbaselineApp.py "$TEMPLATE" --dostep correct_topography
smallbaselineApp.py "$TEMPLATE" --dostep residual_RMS
smallbaselineApp.py "$TEMPLATE" --dostep reference_date
smallbaselineApp.py "$TEMPLATE" --dostep velocity
smallbaselineApp.py "$TEMPLATE" --dostep geocode

# --- Stage 12/13: LOS → vertical + exports ---
echo "--- Stage 12: LOS → vertical deformation ---"
python3 "$SCRIPT_DIR/project_los_to_vertical.py" \
    --mintpy-dir "$WORK_DIR"

echo "--- Stage 13: velocity GeoTIFF export ---"
python3 "$SCRIPT_DIR/export_velocity_products.py" \
    --mintpy-dir "$WORK_DIR" \
    --out-dir    "$EXPORTS_DIR" \
    --mask       "$WORK_DIR/mask_ps_psinsar.h5"

smallbaselineApp.py "$TEMPLATE" --dostep google_earth
smallbaselineApp.py "$TEMPLATE" --dostep hdfeos5

echo "--- Stage 14: time series + figures ---"
python3 "$SCRIPT_DIR/export_timeseries.py" \
    --ts   "$WORK_DIR/timeseries_vertical.h5" \
    --mask "$WORK_DIR/mask_ps_psinsar.h5" \
    --out  "$EXPORTS_DIR/timeseries_points.csv"
python3 "$SCRIPT_DIR/export_ps_points_geojson.py" \
    --mintpy-dir  "$WORK_DIR" \
    --mask        "$WORK_DIR/mask_ps_psinsar.h5" \
    --max-points  100000 \
    --out "$EXPORTS_DIR/ps_like_points.geojson"
python3 "$SCRIPT_DIR/../utils/plot_pipeline_results.py" \
    --mintpy-dir  "$WORK_DIR" \
    --exports-dir "$EXPORTS_DIR" \
    --mask        "$WORK_DIR/mask_ps_psinsar.h5" \
    --out-dir     "$SCRIPT_DIR/../../figures"

echo "=== PS-InSAR pipeline complete: $(date) ==="
echo "PS mask   : $WORK_DIR/mask_ps_psinsar.h5"
echo "Velocity  : $WORK_DIR/velocity_vertical.h5"
echo "GeoTIFF   : $EXPORTS_DIR/velocity.tif"
