#!/usr/bin/env bash
# Re-reference + deramp post-inversion rerun.
# Skips the expensive load_data / invert_network / ERA5 steps — those outputs
# are already correct. Only re-runs the steps that depend on the reference
# point or the new linear deramp setting.
#
# Steps executed:
#   reref_timeseries.py  — change spatial reference in-place (no re-inversion)
#   deramp               — remove linear orbital/atmospheric ramp
#   correct_topography   — re-estimate DEM error on deramped timeseries
#   residual_RMS         — update RMS stats
#   reference_date       — reset temporal baseline
#   velocity             — recompute velocity from updated timeseries_demErr.h5
#   geocode              — re-geocode updated products
#   Stage 12             — LOS → vertical
#   Stage 13             — velocity GeoTIFF + uncertainty export
#   Stage 14             — timeseries CSV, GeoJSON, figures
#
# Usage:
#   bash run_reref_psinsar.sh [template] [work_dir] [exports_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

TEMPLATE=${1:-"$REPO_ROOT/configs/mintpy/smallbaselineApp_psinsar.cfg"}
WORK_DIR=${2:-"$REPO_ROOT/data/mintpy_outputs_psinsar"}
EXPORTS_DIR=${3:-"$REPO_ROOT/exports_beijing_psinsar"}

to_abs() { [[ "$1" = /* ]] && echo "$1" || echo "$PWD/$1"; }
TEMPLATE=$(to_abs "$TEMPLATE")
WORK_DIR=$(to_abs "$WORK_DIR")
EXPORTS_DIR=$(to_abs "$EXPORTS_DIR")

mkdir -p "$EXPORTS_DIR"
cd "$WORK_DIR"

echo "=== reref + deramp rerun ==="
echo "Template  : $TEMPLATE"
echo "Work dir  : $WORK_DIR"
echo "Exports   : $EXPORTS_DIR"
echo "Start     : $(date)"

# ── Step 1: re-reference timeseries.h5 without re-inversion ─────────────────
echo "--- re-reference to Mentougou stable point ---"
python3 "$SCRIPT_DIR/reref_timeseries.py" \
    --mintpy-dir "$WORK_DIR" \
    --lat 40.0500 --lon 116.0500

# ── Steps 2–7: MintPy post-processing (cascade from deramp) ─────────────────
echo "--- deramp (linear) ---"
smallbaselineApp.py "$TEMPLATE" --dostep deramp

echo "--- correct_topography ---"
smallbaselineApp.py "$TEMPLATE" --dostep correct_topography

echo "--- residual_RMS ---"
smallbaselineApp.py "$TEMPLATE" --dostep residual_RMS

echo "--- reference_date ---"
smallbaselineApp.py "$TEMPLATE" --dostep reference_date

echo "--- velocity ---"
smallbaselineApp.py "$TEMPLATE" --dostep velocity

echo "--- geocode ---"
smallbaselineApp.py "$TEMPLATE" --dostep geocode

# ── Stage 12: LOS → vertical ─────────────────────────────────────────────────
echo "--- Stage 12: LOS → vertical ---"
python3 "$SCRIPT_DIR/project_los_to_vertical.py" --mintpy-dir "$WORK_DIR"

# ── Stage 13: velocity GeoTIFF export ────────────────────────────────────────
echo "--- Stage 13: velocity GeoTIFF export ---"
python3 "$SCRIPT_DIR/export_velocity_products.py" \
    --mintpy-dir "$WORK_DIR" \
    --out-dir    "$EXPORTS_DIR" \
    --mask       "$WORK_DIR/mask_ps_psinsar.h5"

# ── Stage 14: timeseries + figures ───────────────────────────────────────────
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
    --out-dir     "$REPO_ROOT/figures"

echo "=== reref done: $(date) ==="
echo "Velocity  : $WORK_DIR/velocity_vertical.h5"
echo "GeoTIFF   : $EXPORTS_DIR/velocity.tif"
