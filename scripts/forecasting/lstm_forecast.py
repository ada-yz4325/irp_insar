"""
LSTM baseline forecasting for pixel-wise InSAR displacement time series.

Unlike per-pixel ARIMA, a single LSTM is trained jointly across all pixels'
sliding windows (each pixel has too few points, ~30-100, to train a network
on its own). At inference, each pixel's most recent window is forecast
forward independently.

Input is the Stage 14 export (scripts/mintpy/export_timeseries.py), schema
row,col,date,displacement_mm -- one row per pixel per acquisition date.

Usage:
    python lstm_forecast.py \
        --input ../../exports/timeseries_points.csv \
        --out   ../../results/forecasts/lstm_results.csv \
        --lookback 12 --horizon 12 --epochs 50
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


class LSTMForecaster(nn.Module):
    def __init__(self, hidden_size: int = 32, num_layers: int = 1, horizon: int = 12):
        super().__init__()
        self.lstm = nn.LSTM(input_size=1, hidden_size=hidden_size,
                             num_layers=num_layers, batch_first=True)
        self.head = nn.Linear(hidden_size, horizon)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, lookback, 1)
        _, (h_n, _) = self.lstm(x)
        last_hidden = h_n[-1]               # (batch, hidden_size)
        return self.head(last_hidden)       # (batch, horizon)


class WindowDataset(Dataset):
    """Sliding (lookback -> horizon) windows pooled from all pixel series."""

    def __init__(self, series_by_pixel: dict, lookback: int, horizon: int):
        self.samples = []
        for (row, col), (series, mean, std) in series_by_pixel.items():
            n = len(series)
            for start in range(0, n - lookback - horizon + 1):
                x = series[start: start + lookback]
                y = series[start + lookback: start + lookback + horizon]
                if np.isnan(x).any() or np.isnan(y).any():
                    continue
                self.samples.append((x.astype(np.float32), y.astype(np.float32)))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        x, y = self.samples[idx]
        return torch.from_numpy(x).unsqueeze(-1), torch.from_numpy(y)


def normalize_series(df: pd.DataFrame) -> dict:
    """Per-pixel z-score normalization; returns {(row,col): (norm_series, mean, std)}."""
    out = {}
    for (row, col), group in df.groupby(["row", "col"]):
        group = group.sort_values("date")
        vals = group["displacement_mm"].values.astype(np.float32)
        mean, std = np.nanmean(vals), np.nanstd(vals)
        std = std if std > 1e-6 else 1.0
        out[(row, col)] = ((vals - mean) / std, mean, std)
    return out


def train_model(model: LSTMForecaster, dataset: WindowDataset, epochs: int, lr: float = 1e-3) -> None:
    if len(dataset) == 0:
        raise ValueError("No training windows could be built — series too short for "
                          "the requested lookback + horizon, or too many NaNs.")
    loader = DataLoader(dataset, batch_size=16, shuffle=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    model.train()
    for epoch in range(epochs):
        total_loss = 0.0
        for x, y in loader:
            optimizer.zero_grad()
            pred = model(x)
            loss = loss_fn(pred, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)
        if (epoch + 1) % max(1, epochs // 5) == 0 or epoch == epochs - 1:
            print(f"  epoch {epoch + 1}/{epochs}  loss={total_loss / len(dataset):.4f}")


def forecast_all_pixels(model: LSTMForecaster, series_by_pixel: dict, lookback: int, horizon: int) -> list:
    model.eval()
    results = []
    with torch.no_grad():
        for (row, col), (series, mean, std) in series_by_pixel.items():
            tail = series[-lookback:]
            if len(tail) < lookback or np.isnan(tail).any():
                forecast = np.full(horizon, np.nan)
            else:
                x = torch.from_numpy(tail.astype(np.float32)).reshape(1, lookback, 1)
                pred_norm = model(x).squeeze(0).numpy()
                forecast = pred_norm * std + mean  # back to mm
            for step, val in enumerate(forecast, 1):
                results.append({"row": row, "col": col, "step": step, "forecast_mm": val})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",    required=True)
    parser.add_argument("--out",      required=True)
    parser.add_argument("--lookback", type=int, default=12)
    parser.add_argument("--horizon",  type=int, default=12)
    parser.add_argument("--epochs",   type=int, default=50)
    parser.add_argument("--hidden-size", type=int, default=32)
    args = parser.parse_args()

    df = pd.read_csv(args.input, parse_dates=["date"])
    series_by_pixel = normalize_series(df)

    dataset = WindowDataset(series_by_pixel, args.lookback, args.horizon)
    print(f"Training windows: {len(dataset)} (from {len(series_by_pixel)} pixels)")

    model = LSTMForecaster(hidden_size=args.hidden_size, horizon=args.horizon)
    train_model(model, dataset, epochs=args.epochs)

    results = forecast_all_pixels(model, series_by_pixel, args.lookback, args.horizon)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
