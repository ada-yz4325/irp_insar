# Imperial HPC Workflow

## 1. Connect to HPC

```bash
ssh USERNAME@login.hpc.ic.ac.uk
```

## 2. Clone the repository

```bash
git clone https://github.com/ada-yz4325/irp_insar.git
cd irp_insar
```

## 3. Set up the conda environment

```bash
module load anaconda3/personal
conda env create -f environment.yml
conda activate insar
```

ISCE2's `stackSentinel.py` (topsStack) isn't bundled with conda-forge's
`isce2` package and must be pulled separately from GitHub; SNAPHU and
PyAPS3/CDS API credentials (for Stage 11's weather-model correction) are
covered in [installation.md](installation.md).

## 4. Transfer raw Sentinel-1 data

All large data goes to **ephemeral** storage (no quota, auto-deleted after
30 days) -- never home, which has a 1TB/10M-file quota.

```bash
cd scripts/download
cp download_config_template.yml download_config.yml
# Edit download_config.yml: AOI WKT, track/frame, pass direction, VV-only
python download_s1.py --config download_config.yml
```

This pipeline's validation stack: 57 Sentinel-1A scenes, track 69,
ascending, IW1, single burst, VV-only, covering a Beijing urban-core AOI.
**Same AOI, path, frame, orbit direction, swath and polarization for every
scene** -- `scripts/isce2/check_stack_metadata.py` (Stage 1) fails loudly
if any scene's geometry doesn't match.

## 5. Validate stack metadata (Stage 1)

```bash
python scripts/isce2/check_stack_metadata.py \
    --slc-dir <ephemeral>/data/raw/slc \
    --out metadata/stack_inventory.csv
```

## 6. Run ISCE2 via PBS job (Stages 3-8)

```bash
qsub jobs/isce2_job.pbs
qstat -u $USER
```

`jobs/isce2_job.pbs` calls `scripts/isce2/run_topsStack.sh`, which
translates `configs/isce2/topsStack_template.cfg` into `stackSentinel.py`
CLI args and runs the generated `run_files/` in order.

**Important**: this stack uses `doESD = False` (geometry coregistration,
not NESD). NESD/ESD needs a burst-overlap region between adjacent bursts
to estimate azimuth misregistration -- with exactly 1 burst per swath
(this stack's intentionally small validation AOI), there is no second
burst to overlap with, and NESD always crashes with an empty pair list in
the `pairs_misreg`/`timeseries_misreg` steps. Re-enable `doESD = True`
only once scaling to an AOI spanning 2+ bursts per swath.

After it completes:

```bash
python scripts/isce2/build_unwrap_mask.py --work-dir <ephemeral>/data/processed/isce2   # Stage 7
python scripts/isce2/check_geometry.py    --work-dir <ephemeral>/data/processed/isce2   # Stage 8
python scripts/isce2/record_burst_subset.py \
    --work-dir <ephemeral>/data/processed/isce2 --out metadata/resolved_burst_subset.yaml
```

## 7. Run MintPy via PBS job (Stages 9-14)

```bash
qsub jobs/mintpy_job.pbs
```

`jobs/mintpy_job.pbs` calls `scripts/mintpy/run_mintpy.sh`, which chains:
`load_data` → `modify_network` → `invert_network` →
**Stage 10 PS-like mask** (`build_ps_like_mask.py`) → `correct_LOD` →
**Stage 11 atmospheric correction** (`atmospheric_correction/apply_atmo_correction.py`,
method from `configs/atmo_correction.yaml` -- *not* MintPy's hard-coded
`correct_troposphere` dostep) → `deramp` → `correct_topography` →
`residual_RMS` → `reference_date` → `velocity` → `geocode` →
**Stage 13 velocity export** (`export_velocity_products.py`) →
`google_earth`/`hdfeos5` → **Stage 14 export + figures**
(`export_timeseries.py`, `export_ps_points_geojson.py`,
`plot_pipeline_results.py`).

## 8. Validate everything in one pass

```bash
python scripts/utils/validate_pipeline.py \
    --slc-dir       <ephemeral>/data/raw/slc \
    --dem-dir       <ephemeral>/data/raw/dem \
    --isce-work-dir <ephemeral>/data/processed/isce2 \
    --mintpy-dir    <ephemeral>/data/mintpy_outputs \
    --exports-dir   exports
```

Runs all 12 validation checks from the task spec independently and
reports a pass/fail summary -- useful both mid-run (to see how far the
pipeline got) and as a final acceptance check.

## 9. Retrieve results

```bash
rsync -avzP \
    USERNAME@login.hpc.ic.ac.uk:/rds/general/user/USERNAME/home/irp_insar/exports/ \
    /local/path/to/exports/
rsync -avzP \
    USERNAME@login.hpc.ic.ac.uk:/rds/general/user/USERNAME/home/irp_insar/figures/ \
    /local/path/to/figures/
```

## 10. Forecasting (optional, downstream of this pipeline's scope)

```bash
conda activate insar
python scripts/forecasting/arima_baseline.py \
    --input exports/timeseries_points.csv \
    --out   results/forecasts/arima_results.csv \
    --horizon 12
```
