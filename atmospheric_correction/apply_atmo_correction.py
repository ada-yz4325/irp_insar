"""
Stage 11 — pluggable atmospheric delay correction interface.

MintPy's tropospheric correction must not be a hard-coded default: this
module dispatches on configs/atmo_correction.yaml's `method` field and
always writes both atmosphere/uncorrected_timeseries.h5 (untouched copy
of the input) and atmosphere/corrected_timeseries.h5 (output of whichever
method ran), plus atmosphere/atmo_correction_log.json recording which
method/parameters were used. See README.md for the method contract.

Usage:
    python apply_atmo_correction.py --timeseries <timeseries.h5> \
        --mintpy-dir <mintpy work dir> --config configs/atmo_correction.yaml
"""

import argparse
import importlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import h5py
import yaml


def method_none(in_file: Path, out_file: Path) -> dict:
    shutil.copy(in_file, out_file)
    return {"method": "none", "note": "passthrough, no correction applied"}


def method_weather_model(in_file: Path, out_file: Path, geom_file: Path, model: str, weather_dir: Path) -> dict:
    if not geom_file.exists():
        sys.exit(f"weather_model correction needs {geom_file} (Stage 9 load_data output)")
    weather_dir.mkdir(parents=True, exist_ok=True)
    import mintpy.cli.tropo_pyaps3 as tropo_pyaps3

    iargs = ["-f", str(in_file), "-m", model, "-g", str(geom_file), "-w", str(weather_dir), "-o", str(out_file)]
    tropo_pyaps3.main(iargs)
    return {"method": "weather_model", "model": model, "weather_dir": str(weather_dir)}


def _read_timeseries(path: Path):
    with h5py.File(path, "r") as f:
        ts = f["timeseries"][:]
        dates = f["date"][:]
        atr = dict(f.attrs)
    return ts, dates, atr


def _write_timeseries(path: Path, data, dates, atr):
    with h5py.File(path, "w") as f:
        f.create_dataset("timeseries", data=data)
        f.create_dataset("date", data=dates)
        for k, v in atr.items():
            f.attrs[k] = v


def method_external_delay(in_file: Path, out_file: Path, delay_file: str) -> dict:
    ts, dates, atr = _read_timeseries(in_file)
    with h5py.File(delay_file, "r") as f:
        dset = "timeseries" if "timeseries" in f else list(f.keys())[0]
        delay = f[dset][:]
    if delay.shape != ts.shape:
        sys.exit(f"external delay shape {delay.shape} != timeseries shape {ts.shape}")
    _write_timeseries(out_file, ts - delay, dates, atr)
    return {"method": "external_delay", "delay_file": str(delay_file)}


def method_custom(in_file: Path, out_file: Path, module_path: str, func_name: str) -> dict:
    sys.path.insert(0, str(Path(module_path).parent))
    mod = importlib.import_module(Path(module_path).stem)
    func = getattr(mod, func_name)
    ts, dates, atr = _read_timeseries(in_file)
    corrected = func(ts, dates, atr)
    _write_timeseries(out_file, corrected, dates, atr)
    return {"method": "custom", "module": module_path, "func": func_name}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--timeseries", required=True, help="Input timeseries.h5 (pre-correction)")
    ap.add_argument("--mintpy-dir", required=True, help="MintPy work dir")
    ap.add_argument("--config", required=True, help="Path to atmo_correction.yaml")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f) or {}
    method = cfg.get("method", "none")

    mintpy_dir = Path(args.mintpy_dir)
    atmo_dir = mintpy_dir / "atmosphere"
    atmo_dir.mkdir(parents=True, exist_ok=True)

    in_file = Path(args.timeseries)
    if not in_file.exists():
        sys.exit(f"Input timeseries not found: {in_file}")

    uncorrected_file = atmo_dir / "uncorrected_timeseries.h5"
    corrected_file = atmo_dir / "corrected_timeseries.h5"
    shutil.copy(in_file, uncorrected_file)

    if method == "none":
        info = method_none(in_file, corrected_file)
    elif method in ("mintpy_default", "weather_model"):
        geom_file = mintpy_dir / "inputs" / "geometryRadar.h5"
        model = cfg.get("weather_model", "ERA5")
        weather_dir = Path(cfg.get("weather_dir") or (atmo_dir / "weather_data"))
        info = method_weather_model(in_file, corrected_file, geom_file, model, weather_dir)
    elif method == "external_delay":
        if not cfg.get("external_delay_path"):
            sys.exit("method=external_delay requires external_delay_path in config")
        info = method_external_delay(in_file, corrected_file, cfg["external_delay_path"])
    elif method == "custom":
        if not cfg.get("custom_module_path"):
            sys.exit("method=custom requires custom_module_path (and optionally custom_func) in config")
        info = method_custom(in_file, corrected_file, cfg["custom_module_path"], cfg.get("custom_func", "correct"))
    else:
        sys.exit(f"Unknown atmospheric correction method: {method!r}")

    log = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_timeseries": str(in_file),
        "uncorrected_timeseries": str(uncorrected_file),
        "corrected_timeseries": str(corrected_file),
        **info,
    }
    log_path = atmo_dir / "atmo_correction_log.json"
    with open(log_path, "w") as f:
        json.dump(log, f, indent=2)

    print(f"OK: atmospheric correction method={method!r} applied. Log: {log_path}")


if __name__ == "__main__":
    main()
