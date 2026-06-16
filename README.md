# Himalayan InSAR Ground Deformation Forecasting

Imperial College London — MSc Individual Research Project

**Yuxi Zhang**

## Overview

End-to-end pipeline for Himalayan ground deformation monitoring and forecasting:

```
Sentinel-1 SLC  →  ISCE2  →  MintPy (SBAS)  →  ARIMA / LSTM / Transformer
```

## Quick Start

```bash
conda env create -f environment.yml
conda activate insar
```

See [docs/installation.md](docs/installation.md) for full setup and [docs/hpc_workflow.md](docs/hpc_workflow.md) for HPC processing.

## Repository Layout

```
irp_insar/
├── configs/
│   ├── isce2/          # topsStack configuration templates
│   └── mintpy/         # smallbaselineApp templates
├── scripts/
│   ├── download/       # Sentinel-1 ASF download
│   ├── preprocessing/  # orbit/DEM preparation utilities
│   ├── isce2/          # stack processing wrappers
│   ├── mintpy/         # time-series inversion + export
│   └── forecasting/    # ARIMA, LSTM, Transformer
├── notebooks/          # exploratory analysis
├── data/
│   ├── raw/            # SLC zips, orbits, DEM (git-ignored)
│   ├── processed/      # exported CSVs, masked arrays
│   └── mintpy_outputs/ # .h5 products (git-ignored)
├── results/
│   ├── interferograms/
│   ├── timeseries/
│   ├── velocity/
│   └── forecasts/
├── figures/
├── docs/
└── reports/
```

## Pipeline Stages

| Stage | Tool | Script |
|-------|------|--------|
| Data acquisition | asf-search | `scripts/download/download_s1.py` |
| Interferometric processing | ISCE2 topsStack | `scripts/isce2/run_topsStack.sh` |
| Time-series inversion | MintPy SBAS | `scripts/mintpy/run_mintpy.sh` |
| Time-series export | h5py / pandas | `scripts/mintpy/export_timeseries.py` |
| ARIMA baseline | statsmodels | `scripts/forecasting/arima_baseline.py` |
| LSTM / Transformer | PyTorch | `scripts/forecasting/` *(to be implemented)* |

## Key Outputs

- `data/mintpy_outputs/velocity.h5` — mean LOS velocity map
- `data/mintpy_outputs/timeseries.h5` — pixel-wise displacement time series
- `data/processed/timeseries.csv` — flattened CSV for ML models
- `results/forecasts/` — model predictions
