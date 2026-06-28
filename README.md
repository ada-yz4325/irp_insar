# Urban PS-Focused InSAR Processor

Imperial College London — MSc Individual Research Project

**Yuxi Zhang**

## Overview

Sentinel-1 InSAR pipeline validated on a small, urban, single-burst stack
before scaling up. Goal: persistent-scatterer-like (PS-like) stable urban
targets, deformation time series, and a velocity map -- not a large
full-frame deformation survey.

```
Sentinel-1 SLC  →  ISCE2 (single-burst stack)  →  MintPy (SBAS + PS-like mask)
                 →  pluggable atmospheric correction  →  velocity map  →  export
```

Validation stack: 57 Sentinel-1A scenes, track 69, ascending, IW1,
single burst, VV-only, covering a ~30×130 km swath through Beijing's
urban core (~39.7-40.0°N, 116.3-117.4°E). See `configs/dataset.yaml`.

## Quick Start

```bash
conda env create -f environment.yml
conda activate insar
```

See [docs/installation.md](docs/installation.md) for full setup and
[docs/hpc_workflow.md](docs/hpc_workflow.md) for HPC processing.

## Repository Layout

```
irp_insar/
├── configs/
│   ├── dataset.yaml              # verified stack geometry (track/direction/swath/pol)
│   ├── burst_subset.yaml         # Stage 2 burst/AOI subset declaration
│   ├── atmo_correction.yaml      # Stage 11 method selector
│   ├── isce2/                    # topsStack configuration template
│   └── mintpy/                   # smallbaselineApp template
├── scripts/
│   ├── download/                 # Sentinel-1 ASF download
│   ├── isce2/                    # stack processing, metadata/geometry/unwrap checks
│   ├── mintpy/                   # load, PS-like mask, inversion, velocity, export
│   ├── utils/                    # ISCE2 image I/O, plotting, consolidated validation
│   └── forecasting/              # ARIMA, LSTM (downstream of this pipeline's scope)
├── atmospheric_correction/       # Stage 11 pluggable interface (see its README)
├── notebooks/                    # exploratory analysis
├── data/                         # raw/processed/mintpy_outputs (git-ignored; lives on ephemeral)
├── metadata/                     # stack_inventory.csv, resolved_burst_subset.yaml (tracked)
├── figures/                      # quick-look PNGs (git-ignored except this README ref)
├── exports/                      # velocity.tif, timeseries_points.csv, ps_like_points.geojson
├── jobs/                         # PBS job scripts
├── docs/
└── reports/
```

## Pipeline Stages

| Stage | Script |
|---|---|
| 1. Stack metadata scan + validation | `scripts/isce2/check_stack_metadata.py` → `metadata/stack_inventory.csv` |
| 2. Burst/AOI subset declaration | `configs/burst_subset.yaml`, resolved by `scripts/isce2/record_burst_subset.py` |
| 3-6. ISCE2 stack: coregistration, interferograms, filtering | `scripts/isce2/run_topsStack.sh` (geometry coregistration -- see config comments on why NESD/ESD doesn't work for a single-burst stack) |
| 7. Unwrapping + quality masks | `scripts/isce2/build_unwrap_mask.py` |
| 8. Geometry validation | `scripts/isce2/check_geometry.py` |
| 9. MintPy load + validation | `scripts/mintpy/check_mintpy_load.py` |
| 10. PS-like stable-pixel mask | `scripts/mintpy/build_ps_like_mask.py` |
| 11. Pluggable atmospheric correction | `atmospheric_correction/apply_atmo_correction.py` (see its README) |
| 12-13. Time-series inversion, velocity, uncertainty | `scripts/mintpy/run_mintpy.sh`, `scripts/mintpy/export_velocity_products.py` |
| 14. Export + visualization | `scripts/mintpy/export_timeseries.py`, `export_ps_points_geojson.py`, `scripts/utils/plot_pipeline_results.py` |
| All-in-one validation | `scripts/utils/validate_pipeline.py` (12 checks) |
| Forecasting (downstream, optional) | `scripts/forecasting/arima_baseline.py`, `lstm_forecast.py` |

`scripts/isce2/run_topsStack.sh` and `scripts/mintpy/run_mintpy.sh` are the
two orchestration entry points -- everything else above is either called
from inside them or run standalone for validation.

## Key Outputs

- `data/mintpy_outputs/velocity.h5`, `velocity_std.h5` — mean LOS velocity + uncertainty
- `data/mintpy_outputs/timeseries.h5` — pixel-wise displacement time series
- `data/mintpy_outputs/masks/mask_ps_like.h5` — PS-like stable-pixel mask
- `data/mintpy_outputs/atmosphere/{corrected,uncorrected}_timeseries.h5` — Stage 11 outputs
- `exports/velocity.tif`, `timeseries_points.csv`, `ps_like_points.geojson`
- `figures/velocity_map.png`, `temporal_coherence.png`, `ps_like_mask.png`, `selected_point_timeseries.png`
