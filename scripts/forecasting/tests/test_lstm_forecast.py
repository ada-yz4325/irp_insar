import numpy as np
import pandas as pd
import pytest
import torch

from lstm_forecast import (
    LSTMForecaster,
    WindowDataset,
    normalize_series,
    train_model,
    forecast_all_pixels,
    main as lstm_main,
)
from make_synthetic_timeseries import gen_pixel_series, make_dates


@pytest.fixture
def synthetic_df():
    rng = np.random.default_rng(0)
    dates = make_dates("2020-06-20", n_dates=46, interval_days=12)
    archetypes = ["stable", "subsidence", "uplift", "seasonal", "combined", "noisy", "outlier"]

    records = []
    for row, archetype in enumerate(archetypes):
        series = gen_pixel_series(dates, archetype, rng)
        for date, val in zip(dates, series):
            records.append({"row": row, "col": 0, "date": date, "displacement_mm": val})

    return pd.DataFrame(records), archetypes


def test_normalize_series_zero_mean_unit_std(synthetic_df):
    df, _ = synthetic_df
    series_by_pixel = normalize_series(df)
    for (row, col), (series, mean, std) in series_by_pixel.items():
        clean = series[~np.isnan(series)]
        assert abs(np.mean(clean)) < 1e-3
        assert abs(np.std(clean) - 1.0) < 1e-3 or std == 1.0  # std==1.0 fallback for degenerate case


def test_window_dataset_skips_nan_windows(synthetic_df):
    df, _ = synthetic_df
    series_by_pixel = normalize_series(df)
    dataset = WindowDataset(series_by_pixel, lookback=12, horizon=6)
    assert len(dataset) > 0
    for x, y in dataset:
        assert not torch.isnan(x).any()
        assert not torch.isnan(y).any()
        assert x.shape == (12, 1)
        assert y.shape == (6,)


def test_forecaster_forward_pass_shape():
    model = LSTMForecaster(hidden_size=8, horizon=6)
    x = torch.randn(4, 12, 1)  # batch=4, lookback=12, features=1
    out = model(x)
    assert out.shape == (4, 6)


def test_train_model_runs_without_crashing(synthetic_df):
    df, _ = synthetic_df
    series_by_pixel = normalize_series(df)
    dataset = WindowDataset(series_by_pixel, lookback=12, horizon=6)
    model = LSTMForecaster(hidden_size=8, horizon=6)
    train_model(model, dataset, epochs=2)  # just check it runs, not convergence


def test_train_model_raises_clear_error_on_empty_dataset():
    model = LSTMForecaster(hidden_size=8, horizon=6)
    empty_dataset = WindowDataset({}, lookback=12, horizon=6)
    with pytest.raises(ValueError):
        train_model(model, empty_dataset, epochs=1)


def test_forecast_all_pixels_shape_and_columns(synthetic_df):
    df, archetypes = synthetic_df
    series_by_pixel = normalize_series(df)
    dataset = WindowDataset(series_by_pixel, lookback=12, horizon=6)
    model = LSTMForecaster(hidden_size=8, horizon=6)
    train_model(model, dataset, epochs=2)

    results = forecast_all_pixels(model, series_by_pixel, lookback=12, horizon=6)
    results_df = pd.DataFrame(results)
    assert set(results_df.columns) == {"row", "col", "step", "forecast_mm"}
    assert len(results_df) == len(archetypes) * 6


def test_end_to_end_on_synthetic_stack(synthetic_df, tmp_path):
    df, archetypes = synthetic_df
    csv_path = tmp_path / "synthetic.csv"
    df_out = df.copy()
    df_out["date"] = df_out["date"].dt.strftime("%Y%m%d")
    df_out.to_csv(csv_path, index=False)

    out_path = tmp_path / "lstm_results.csv"

    import sys
    old_argv = sys.argv
    sys.argv = ["lstm_forecast.py", "--input", str(csv_path), "--out", str(out_path),
                "--lookback", "12", "--horizon", "6", "--epochs", "3"]
    try:
        lstm_main()
    finally:
        sys.argv = old_argv

    assert out_path.exists()
    results = pd.read_csv(out_path)
    assert set(results.columns) == {"row", "col", "step", "forecast_mm"}
    assert len(results) == len(archetypes) * 6
