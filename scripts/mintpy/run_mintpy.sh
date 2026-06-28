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
ATMO_SCRIPT="$SCRIPT_DIR/../../atmospheric_correction/apply_atmo_correction.py"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== MintPy smallbaselineApp ==="
echo "Template : $TEMPLATE"
echo "Work dir : $WORK_DIR"
echo "Start    : $(date)"

smallbaselineApp.py "$TEMPLATE" --dostep load_data
smallbaselineApp.py "$TEMPLATE" --dostep modify_network
smallbaselineApp.py "$TEMPLATE" --dostep invert_network

echo "--- Stage 10: PS-like stable-pixel mask ---"
python "$SCRIPT_DIR/build_ps_like_mask.py" \
    --mintpy-dir "$WORK_DIR" \
    --isce-work-dir "$ISCE_WORK_DIR"

smallbaselineApp.py "$TEMPLATE" --dostep correct_LOD

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
smallbaselineApp.py "$TEMPLATE" --dostep google_earth
smallbaselineApp.py "$TEMPLATE" --dostep hdfeos5

echo "=== MintPy complete: $(date) ==="
echo "Key outputs:"
echo "  $WORK_DIR/velocity.h5"
echo "  $WORK_DIR/timeseries.h5"
echo "  $WORK_DIR/temporalCoherence.h5"
echo "  $WORK_DIR/masks/mask_ps_like.h5"
echo "  $WORK_DIR/atmosphere/corrected_timeseries.h5"
