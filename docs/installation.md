# Installation Guide

## Prerequisites

- conda (Miniconda or Anaconda)
- NASA EarthData account (for Sentinel-1 download)
- ISCE2 licence acknowledgement (free, JPL)

## 1. Create the conda environment

```bash
conda env create -f environment.yml
conda activate insar
```

## 2. Verify MintPy

```bash
python -c "import mintpy; print(mintpy.__version__)"
smallbaselineApp.py --version
```

## 3. Verify ISCE2

```bash
python -c "import isce; print(isce.__file__)"
```

conda-forge's `isce2` package does **not** include `stackSentinel.py`
(the topsStack stack-processing tool) -- it must be pulled separately:

```bash
git clone https://github.com/isce-framework/isce2.git $HOME/isce2_contrib
```

Set environment variables (add to `~/.bashrc`, or export them at the top
of any PBS job script -- see `jobs/isce2_job.pbs` for the exact pattern):

```bash
export ISCE_HOME=$CONDA_PREFIX/lib/python3.10/site-packages/isce
export TOPSSTACK=$HOME/isce2_contrib/contrib/stack/topsStack
export STACK_CONTRIB=$HOME/isce2_contrib/contrib/stack
export PATH=$ISCE_HOME/bin:$ISCE_HOME/applications:$TOPSSTACK:$PATH
export PYTHONPATH=$ISCE_HOME:$STACK_CONTRIB:$PYTHONPATH
```

Verify:

```bash
stackSentinel.py --help
```

## 4. SNAPHU (phase unwrapping)

SNAPHU is included via conda-forge as a Python package (`snaphu`), not a
bare CLI binary on `$PATH` -- ISCE2's own `Snaphu.py` wrapper calls into
it directly, so nothing extra is needed. Verify:

```bash
python -c "import snaphu; print(snaphu.__file__)"
```

## 5. NASA EarthData credentials

Create `~/.netrc`:

```
machine urs.earthdata.nasa.gov
    login YOUR_USERNAME
    password YOUR_PASSWORD
```

```bash
chmod 600 ~/.netrc
```

## 6. ERA5 weather-model correction (Stage 11, optional)

Only needed if `configs/atmo_correction.yaml`'s `method` is set to
`weather_model`/`mintpy_default` -- the default for this project's first
validation pass is `none` (see `atmospheric_correction/README.md`).

```bash
pip install pyaps3
```

Configure `~/.cdsapirc` with your Copernicus Climate Data Store API key
(not `~/.pyaps/model.cfg` -- that's the legacy PyAPS convention; pyaps3
uses the `cdsapi` library's standard credential file):

```
url: https://cds.climate.copernicus.eu/api
key: YOUR_CDS_API_KEY
```
