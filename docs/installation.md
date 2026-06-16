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
python -c "import isce; print(isce.__version__)"
stackSentinel.py --help
```

If ISCE2 is not available via conda-forge, install from source:

```bash
git clone https://github.com/isce-framework/isce2.git
cd isce2
conda install --file requirements.txt
python setup.py install --prefix=$CONDA_PREFIX
```

Set environment variables (add to `~/.bashrc`):

```bash
export ISCE_HOME=$CONDA_PREFIX/lib/python3.10/site-packages/isce
export PATH=$PATH:$ISCE_HOME/applications:$ISCE_HOME/bin
export PYTHONPATH=$PYTHONPATH:$ISCE_HOME
```

## 4. SNAPHU (phase unwrapping)

SNAPHU is included via conda-forge. Verify:

```bash
snaphu --version
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

## 6. ERA5 / GACOS for tropospheric correction (optional)

Install PyAPS:

```bash
pip install pyaps3
```

Configure `~/.pyaps/model.cfg` with your CDS API key.
