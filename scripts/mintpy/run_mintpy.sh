#!/usr/bin/env bash
# Run full MintPy SBAS time-series inversion.
# Usage: bash run_mintpy.sh [template_file] [work_dir]

set -euo pipefail

TEMPLATE=${1:-../../configs/mintpy/smallbaselineApp_template.cfg}
WORK_DIR=${2:-../../data/mintpy_outputs}

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

echo "=== MintPy smallbaselineApp ==="
echo "Template : $TEMPLATE"
echo "Work dir : $WORK_DIR"
echo "Start    : $(date)"

smallbaselineApp.py "$TEMPLATE" --dostep load_data
smallbaselineApp.py "$TEMPLATE" --dostep modify_network
smallbaselineApp.py "$TEMPLATE" --dostep invert_network
smallbaselineApp.py "$TEMPLATE" --dostep correct_LOD
smallbaselineApp.py "$TEMPLATE" --dostep correct_troposphere
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
