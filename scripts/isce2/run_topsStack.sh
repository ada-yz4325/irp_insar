#!/usr/bin/env bash
# Run ISCE2 topsStack for a full Sentinel-1 SLC stack.
# Usage: bash run_topsStack.sh [config_file] [--generate-only]
#
#   --generate-only   only run stackSentinel.py to produce run_files/,
#                      do not execute the (multi-hour) processing steps.
#
# Default config: ../../configs/isce2/topsStack_template.cfg

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG=${1:-"$SCRIPT_DIR/../../configs/isce2/topsStack_template.cfg"}
GENERATE_ONLY=false
[[ "${2:-}" == "--generate-only" ]] && GENERATE_ONLY=true

echo "=== ISCE2 topsStack ==="
echo "Config: $CONFIG"
echo "Start : $(date)"

# stackSentinel.py takes CLI flags only (no config file) — translate ours
ARGS=$(python "$SCRIPT_DIR/cfg_to_stacksentinel_args.py" "$CONFIG")
WORK_DIR=$(python -c "
import configparser, sys
c = configparser.ConfigParser(inline_comment_prefixes=('#',))
c.read('$CONFIG')
print(c['topsStack']['workDir'])
")
mkdir -p "$WORK_DIR"

# stackSentinel.py refuses to run if run_files/configs already exist from a
# previous (e.g. --generate-only) invocation. Safe to clear since these are
# just the generated recipe, not processing output — only remove them if no
# actual processing has started yet (merged/ is the first heavy-output dir).
if [[ ! -d "$WORK_DIR/merged" ]]; then
    rm -rf "$WORK_DIR/run_files" "$WORK_DIR/configs" "$WORK_DIR/SAFE_files.txt"
fi

echo "--- Generating run_files ---"
echo "stackSentinel.py $ARGS"
( cd "$WORK_DIR" && eval stackSentinel.py "$ARGS" )

if $GENERATE_ONLY; then
    echo "=== --generate-only: run_files created, processing skipped ==="
    echo "Run files: $WORK_DIR/run_files/"
    ls "$WORK_DIR/run_files/"
    exit 0
fi

# stackSentinel.py's --num_proc already bakes its own parallelism directly
# into multi-line run_files: commands are batched in groups ending with `&`,
# each batch followed by a `wait` line. Running each line independently
# through `xargs -P` (as this script used to) breaks that batching — `wait`
# becomes a no-op in its own subshell, and each `bash -c "CMD &"` exits the
# instant it backgrounds CMD instead of waiting for it. That caused two
# different failures (FileNotFoundError, then IndexError on empty output)
# in earlier runs. Just run the file directly and let its own &/wait
# structure do the parallelism.
echo "--- Executing run_files in order ---"
for run_script in "$WORK_DIR"/run_files/run_*; do
    n_lines=$(wc -l < "$run_script")
    echo "--- Running: $run_script ($n_lines lines) ---"
    bash "$run_script"
    sync
done

echo "=== topsStack complete: $(date) ==="
