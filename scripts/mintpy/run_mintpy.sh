#!/usr/bin/env bash
# Run full MintPy SBAS time-series inversion, with the urban-PS pipeline's
# extra stages spliced in: PS-like masking (Stage 10) right after network
# inversion, and a pluggable atmospheric correction (Stage 11) in place of
# MintPy's hard-coded correct_troposphere dostep.
#
# Usage: bash run_mintpy.sh [template_file] [work_dir] [atmo_config] [isce_work_dir]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ISCE2_CFG="$SCRIPT_DIR/../../configs/isce2/topsStack_template.cfg"
TEMPLATE=${1:-"$SCRIPT_DIR/../../configs/mintpy/smallbaselineApp_template.cfg"}
WORK_DIR=${2:-"$SCRIPT_DIR/../../data/mintpy_outputs"}
ATMO_CONFIG=${3:-"$SCRIPT_DIR/../../configs/atmo_correction.yaml"}
# Default ISCE_WORK_DIR to the real workDir from the ISCE2 config (ephemeral
# storage) rather than a relative guess -- the project's data/ tree under
# the repo itself is just a gitignored placeholder, the actual stack output
# lives wherever configs/isce2/topsStack_template.cfg's workDir points.
ISCE_WORK_DIR=${4:-$(python -c "
import configparser
c = configparser.ConfigParser(inline_comment_prefixes=('#',))
c.read('$ISCE2_CFG')
print(c['topsStack']['workDir'])
")}
EXPORTS_DIR=${5:-"$SCRIPT_DIR/../../exports"}
ATMO_SCRIPT="$SCRIPT_DIR/../../atmospheric_correction/apply_atmo_correction.py"

# Canonicalize every path arg to absolute BEFORE the `cd "$WORK_DIR"` below --
# a caller-supplied relative path (e.g. jobs/mintpy_job.pbs passes
# "configs/mintpy/smallbaselineApp_template.cfg" relative to $PBS_O_WORKDIR)
# would otherwise silently stop resolving once the cwd changes, and
# smallbaselineApp.py would fail with FileNotFoundError on its own template.
to_abs() { [[ "$1" = /* ]] && echo "$1" || echo "$PWD/$1"; }
TEMPLATE=$(to_abs "$TEMPLATE")
WORK_DIR=$(to_abs "$WORK_DIR")
ATMO_CONFIG=$(to_abs "$ATMO_CONFIG")
ISCE_WORK_DIR=$(to_abs "$ISCE_WORK_DIR")
EXPORTS_DIR=$(to_abs "$EXPORTS_DIR")

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== MintPy smallbaselineApp ==="
echo "Template : $TEMPLATE"
echo "Work dir : $WORK_DIR"
echo "Start    : $(date)"

smallbaselineApp.py "$TEMPLATE" --dostep load_data
smallbaselineApp.py "$TEMPLATE" --dostep modify_network
smallbaselineApp.py "$TEMPLATE" --dostep reference_point
smallbaselineApp.py "$TEMPLATE" --dostep quick_overview
# Required because configs/mintpy/smallbaselineApp_template.cfg sets
# mintpy.unwrapError.method = bridging+phase_closure -- invert_network then
# expects the "unwrapPhase_bridging_phaseClosure" dataset this step writes
# into ifgramStack.h5; skipping it crashes invert_network with ValueError
# (confirmed live: job 3128109.pbs-7).
smallbaselineApp.py "$TEMPLATE" --dostep correct_unwrap_error
smallbaselineApp.py "$TEMPLATE" --dostep invert_network

echo "--- Stage 10: PS-like stable-pixel mask ---"
python "$SCRIPT_DIR/build_ps_like_mask.py" \
    --mintpy-dir "$WORK_DIR" \
    --isce-work-dir "$ISCE_WORK_DIR"

smallbaselineApp.py "$TEMPLATE" --dostep correct_LOD
# Both default to "no" in this project's config (no SET/ionosphere params
# set) -- included for completeness with MintPy's canonical step order
# rather than silently skipped.
smallbaselineApp.py "$TEMPLATE" --dostep correct_SET
smallbaselineApp.py "$TEMPLATE" --dostep correct_ionosphere

echo "--- Stage 11: pluggable atmospheric correction (see atmospheric_correction/README.md) ---"
python "$ATMO_SCRIPT" \
    --timeseries "$WORK_DIR/timeseries.h5" \
    --mintpy-dir "$WORK_DIR" \
    --config "$ATMO_CONFIG"
# MintPy's remaining dosteps (deramp, correct_topography, velocity, ...) all
# read/write the canonical timeseries.h5 path -- overwrite it with whichever
# correction was selected (identical content for method=none) so the rest
# of the chain needs no awareness of the atmo step happening outside MintPy.
cp "$WORK_DIR/atmosphere/corrected_timeseries.h5" "$WORK_DIR/timeseries.h5"

smallbaselineApp.py "$TEMPLATE" --dostep deramp
smallbaselineApp.py "$TEMPLATE" --dostep correct_topography
smallbaselineApp.py "$TEMPLATE" --dostep residual_RMS
smallbaselineApp.py "$TEMPLATE" --dostep reference_date
smallbaselineApp.py "$TEMPLATE" --dostep velocity
smallbaselineApp.py "$TEMPLATE" --dostep geocode

echo "--- Stage 13: velocity uncertainty export + GeoTIFF ---"
python "$SCRIPT_DIR/export_velocity_products.py" \
    --mintpy-dir "$WORK_DIR" \
    --out-dir "$EXPORTS_DIR"

smallbaselineApp.py "$TEMPLATE" --dostep google_earth
smallbaselineApp.py "$TEMPLATE" --dostep hdfeos5

echo "--- Stage 14: export and quick-look figures ---"
python "$SCRIPT_DIR/export_timeseries.py" \
    --ts   "$WORK_DIR/timeseries.h5" \
    --mask "$WORK_DIR/masks/mask_ps_like.h5" \
    --out  "$EXPORTS_DIR/timeseries_points.csv"
python "$SCRIPT_DIR/export_ps_points_geojson.py" \
    --mintpy-dir "$WORK_DIR" \
    --out "$EXPORTS_DIR/ps_like_points.geojson"
python "$SCRIPT_DIR/../utils/plot_pipeline_results.py" \
    --mintpy-dir "$WORK_DIR" \
    --exports-dir "$EXPORTS_DIR" \
    --out-dir "$SCRIPT_DIR/../../figures"

echo "=== MintPy complete: $(date) ==="
echo "Key outputs:"
echo "  $WORK_DIR/velocity.h5"
echo "  $WORK_DIR/velocity_std.h5"
echo "  $WORK_DIR/timeseries.h5"
echo "  $WORK_DIR/temporalCoherence.h5"
echo "  $WORK_DIR/masks/mask_ps_like.h5"
echo "  $WORK_DIR/atmosphere/corrected_timeseries.h5"
echo "  $EXPORTS_DIR/velocity.tif"
echo "  $EXPORTS_DIR/timeseries_points.csv"
echo "  $EXPORTS_DIR/ps_like_points.geojson"
echo "  figures/velocity_map.png, temporal_coherence.png, ps_like_mask.png, selected_point_timeseries.png"
