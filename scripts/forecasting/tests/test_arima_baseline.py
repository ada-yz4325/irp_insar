import numpy as np
import pandas as pd
import pytest

from arima_baseline import forecast_pixel, main as arima_main
from make_synthetic_timeseries import gen_pixel_series, make_dates


@pytest.fixture
def synthetic_csv(tmp_path):
    rng = np.random.default_rng(0)
    dates = make_dates("2020-06-20", n_dates=46, interval_days=12)
    archetypes = ["stable", "subsidence", "uplift", "seasonal", "combined", "noisy", "outlier"]

    records = []
    for row, archetype in enumerate(archetypes):
        series = gen_pixel_series(dates, archetype, rng)
        for date, val in zip(dates, series):
            records.append({"row": row, "col": 0, "date": date.strftime("%Y%m%d"),
                             "displacement_mm": val})

    path = tmp_path / "synthetic.csv"
    pd.DataFrame(records).to_csv(path, index=False)
    return path, archetypes


def test_forecast_pixel_shape_on_clean_series():
    series = pd.Series(np.linspace(0, 10, 46) + np.random.default_rng(1).normal(0, 0.5, 46))
    forecast = forecast_pixel(series, horizon=12)
    assert forecast.shape == (12,)
    assert not np.isnan(forecast).any()


def test_forecast_pixel_handles_degenerate_series_without_crashing():
    # Too short / constant series can make ARIMA fail to converge — must not raise.
    series = pd.Series([5.0, 5.0, 5.0])
    forecast = forecast_pixel(series, horizon=4)
    assert forecast.shape == (4,)  # either real values or NaN fallback, never a crash


def test_forecast_pixel_handles_series_with_outlier_jump():
    rng = np.random.default_rng(2)
    series = pd.Series(np.concatenate([
        np.linspace(0, -5, 23) + rng.normal(0, 1, 23),
        np.linspace(35, 40, 23) + rng.normal(0, 1, 23),  # simulated unwrap jump
    ]))
    forecast = forecast_pixel(series, horizon=6)
    assert forecast.shape == (6,)


def test_end_to_end_on_synthetic_stack(synthetic_csv, tmp_path):
    csv_path, archetypes = synthetic_csv
    out_path = tmp_path / "arima_results.csv"

    import sys
    old_argv = sys.argv
    sys.argv = ["arima_baseline.py", "--input", str(csv_path),
                "--out", str(out_path), "--horizon", "8"]
    try:
        arima_main()
    finally:
        sys.argv = old_argv

    assert out_path.exists()
    results = pd.read_csv(out_path)
    assert set(results.columns) == {"row", "col", "step", "forecast_mm"}
    # one row per (pixel, forecast step)
    assert len(results) == len(archetypes) * 8
    assert results["step"].max() == 8
    assert results["step"].min() == 1
