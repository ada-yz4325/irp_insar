# Imperial HPC Workflow

## 1. Connect to HPC

```bash
ssh USERNAME@login.hpc.ic.ac.uk
```

## 2. Clone the repository

```bash
git clone https://github.com/YOUR_GITHUB/irp_insar.git
cd irp_insar
```

## 3. Set up the conda environment

```bash
module load anaconda3/personal
conda env create -f environment.yml
conda activate insar
```

## 4. Transfer raw Sentinel-1 data

Option A — download directly on HPC (recommended):

```bash
cd scripts/download
cp download_config_template.yml download_config.yml
# Edit download_config.yml with your EarthData credentials and AOI
python download_s1.py --config download_config.yml
```

Option B — rsync from local machine:

```bash
rsync -avzP /local/path/to/data/raw/slc/ \
    USERNAME@login.hpc.ic.ac.uk:/rds/general/user/USERNAME/home/irp_insar/data/raw/slc/
```

## 5. Run ISCE2 via PBS job

Create `jobs/isce2_job.pbs`:

```pbs
#PBS -l select=1:ncpus=16:mem=64gb
#PBS -l walltime=24:00:00
#PBS -N isce2_topsStack

cd $PBS_O_WORKDIR
conda activate insar
bash scripts/isce2/run_topsStack.sh configs/isce2/topsStack_template.cfg
```

Submit:

```bash
qsub jobs/isce2_job.pbs
qstat -u $USER
```

## 6. Run MintPy via PBS job

```pbs
#PBS -l select=1:ncpus=8:mem=32gb
#PBS -l walltime=12:00:00
#PBS -N mintpy_sbas

cd $PBS_O_WORKDIR
conda activate insar
bash scripts/mintpy/run_mintpy.sh \
    configs/mintpy/smallbaselineApp_template.cfg \
    data/mintpy_outputs
```

## 7. Retrieve results

```bash
rsync -avzP \
    USERNAME@login.hpc.ic.ac.uk:/rds/general/user/USERNAME/home/irp_insar/data/mintpy_outputs/ \
    /local/path/to/data/mintpy_outputs/
```

## 8. Export time series and run forecasting locally

```bash
conda activate insar
python scripts/mintpy/export_timeseries.py \
    --ts  data/mintpy_outputs/timeseries.h5 \
    --coh data/mintpy_outputs/temporalCoherence.h5 \
    --out data/processed/timeseries.csv

python scripts/forecasting/arima_baseline.py \
    --input data/processed/timeseries.csv \
    --out   results/forecasts/arima_results.csv \
    --horizon 12
```
