# Atmospheric delay correction interface

Stage 11 of the urban PS-InSAR pipeline. MintPy's tropospheric correction
is **not** hard-coded as an always-on default step — `scripts/mintpy/run_mintpy.sh`
calls `apply_atmo_correction.py` instead of MintPy's `correct_troposphere`
dostep, driven entirely by `configs/atmo_correction.yaml`. This keeps the
door open for weather-model corrections, externally generated delay maps
(e.g. from a separate GACOS run, an InSAR atmospheric model, or a research
collaborator's product), or a fully custom correction function — without
editing pipeline code.

## Contract

```
python apply_atmo_correction.py \
    --timeseries <mintpy_dir>/timeseries.h5 \
    --mintpy-dir <mintpy_dir> \
    --config configs/atmo_correction.yaml
```

Always writes, regardless of method:

- `<mintpy_dir>/atmosphere/uncorrected_timeseries.h5` — untouched copy of the input
- `<mintpy_dir>/atmosphere/corrected_timeseries.h5` — output of the configured method
- `<mintpy_dir>/atmosphere/atmo_correction_log.json` — method, parameters, timestamp, file paths

Downstream steps (`deramp`, `correct_topography`, `velocity`, ...) read
`corrected_timeseries.h5` as their input.

## Methods (`method:` in `configs/atmo_correction.yaml`)

| Method | What it does | Requirements |
|---|---|---|
| `none` | Passthrough — `corrected_timeseries.h5` is identical to the uncorrected file | none |
| `mintpy_default` | Alias for `weather_model` | same as below |
| `weather_model` | MintPy's PyAPS3 ERA5 correction (`mintpy.cli.tropo_pyaps3`) | `pyaps3` (installed) + a valid `~/.cdsapirc` (already configured on this HPC account) |
| `external_delay` | Subtracts a user-supplied delay timeseries (`external_delay_path`, an HDF5 with the same `timeseries` dataset shape) | a delay file matching the stack's date list and dimensions |
| `custom` | Dynamically imports `custom_module_path` and calls `custom_func(timeseries_array, dates, attrs) -> corrected_array` | a Python module exposing that function signature |

The default for this first urban PS validation pass is `none`: the
priority for this milestone is the pipeline plumbing (PS-like masking,
time series, velocity), not tuning a weather-model correction for a
57-scene, single-burst stack. Switching to `weather_model` is a one-line
config change once that becomes the priority — the ERA5/PyAPS3 path is
fully wired and the CDS API credentials are already present.

## Adding a new method

1. Write a `method_<name>(in_file, out_file, ...)` function in
   `apply_atmo_correction.py` that produces `out_file` from `in_file`.
2. Add a branch for it in `main()`'s method dispatch.
3. Document any new config fields it needs in `config_atmo.yaml`.

No other pipeline code needs to change — `run_mintpy.sh` only knows about
`configs/atmo_correction.yaml` and the two fixed output filenames.
