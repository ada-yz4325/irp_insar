#!/usr/bin/env bash
# Run ISCE2 topsStack for a full Sentinel-1 SLC stack.
# Usage: bash run_topsStack.sh [config_file]
# Default config: ../../configs/isce2/topsStack_template.cfg

set -euo pipefail

CONFIG=${1:-../../configs/isce2/topsStack_template.cfg}

echo "=== ISCE2 topsStack ==="
echo "Config: $CONFIG"
echo "Start : $(date)"

# Step 1 — generate run files
stackSentinel.py -c "$CONFIG"

# Step 2 — execute all generated run scripts in order
RUN_DIR=$(grep -oP '(?<=workDir\s{0,20}=\s{0,5})\S+' "$CONFIG")/run_files
for run_script in "$RUN_DIR"/run_*.sh; do
    echo "--- Running: $run_script ---"
    bash "$run_script"
done

echo "=== topsStack complete: $(date) ==="
