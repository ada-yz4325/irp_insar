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

# stackSentinel.py's incremental-stack detection (checkCurrentStatus in
# stackSentinel.py) hard sys.exit(1)s if every secondary already has a
# coreg_secondarys/ entry, on the assumption that "all coregistered" means
# "the whole stack, through final unwrapping, was already finished" — it has
# no notion of "coregistration done but later steps aren't". That's exactly
# our case after manually repairing coregistration for a few dates. Hide
# coreg_secondarys/ during generation so it's treated as a fresh stack (full
# run_01-16 recipe, not an early sys.exit). The generated commands have no
# skip-if-output-exists logic of their own, so the execution loop below
# explicitly skips run_01..10 if every date is already fully coregistered.
HID_COREG=false
if [[ ! -d "$WORK_DIR/merged" ]] && [[ -d "$WORK_DIR/coreg_secondarys" ]]; then
    mv "$WORK_DIR/coreg_secondarys" "$WORK_DIR/.coreg_secondarys.hidden"
    HID_COREG=true
fi

echo "--- Generating run_files ---"
echo "stackSentinel.py $ARGS"
( cd "$WORK_DIR" && eval stackSentinel.py "$ARGS" )

if $HID_COREG; then
    mv "$WORK_DIR/.coreg_secondarys.hidden" "$WORK_DIR/coreg_secondarys"
fi

if $GENERATE_ONLY; then
    echo "=== --generate-only: run_files created, processing skipped ==="
    echo "Run files: $WORK_DIR/run_files/"
    ls "$WORK_DIR/run_files/"
    exit 0
fi

# Hiding coreg_secondarys/ above forces stackSentinel.py to emit the FULL
# run_01..run_N recipe covering every secondary date again, even though the
# scripts it generates have no skip-if-output-exists logic of their own —
# unlike the incremental recipe (fewer dates per command), this one will
# genuinely *redo* unpacking/geo2rdr/resampling for every date if executed
# as-is. If coregistration is already complete for every date, skip
# executing any run_file at or before fullBurst_resample (numbered <=10 in
# the fresh/full recipe) — there is nothing left for them to do.
SKIP_THROUGH_RESAMPLE=false
if [[ -d "$WORK_DIR/coreg_secondarys" ]] && [[ -n "$(ls -A "$WORK_DIR/coreg_secondarys" 2>/dev/null)" ]]; then
    incomplete=0
    for d in "$WORK_DIR"/coreg_secondarys/*/; do
        d=${d%/}
        # Checks whichever IW*.xml swaths are actually configured (this stack
        # is single-swath IW1-only; hardcoding IW1/IW2/IW3 here would always
        # report "incomplete" since IW2/IW3 never get produced).
        if [[ -z "$(ls "$d"/IW*.xml 2>/dev/null)" ]]; then
            incomplete=$((incomplete+1))
        fi
    done
    if [[ $incomplete -eq 0 ]]; then
        SKIP_THROUGH_RESAMPLE=true
        echo "--- All secondary dates already fully coregistered: will skip run_01..10 (unpack/baseline/overlap/misreg/geo2rdr/resample) ---"
    fi
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
    base=$(basename "$run_script")
    if $SKIP_THROUGH_RESAMPLE && [[ "$base" =~ ^run_([0-9]+)_ ]] && [[ "${BASH_REMATCH[1]#0}" -le 10 ]]; then
        echo "--- Skipping: $run_script (already complete) ---"
        continue
    fi
    n_lines=$(wc -l < "$run_script")
    echo "--- Running: $run_script ($n_lines lines) ---"
    bash "$run_script"
    sync
done

echo "=== topsStack complete: $(date) ==="
