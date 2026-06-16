"""
ARIMA baseline forecasting for pixel-wise InSAR displacement time series.

Usage:
    python arima_baseline.py \
        --input ../../data/processed/timeseries.csv \
        --out   ../../results/forecasts/arima_results.csv \
        --horizon 12
"""

import argparse
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from statsmodels.tsa.arima.model import ARIMA
from tqdm import tqdm

warnings.filterwarnings("ignore")


def forecast_pixel(series: pd.Series, horizon: int, order=(1, 1, 1)) -> np.ndarray:
    try:
        model = ARIMA(series.values, order=order)
        fit = model.fit()
        return fit.forecast(steps=horizon)
    except Exception:
        return np.full(horizon, np.nan)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",   required=True)
    parser.add_argument("--out",     required=True)
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--order",   default="1,1,1")
    args = parser.parse_args()

    order = tuple(int(x) for x in args.order.split(","))
    df = pd.read_csv(args.input, parse_dates=["date"])

    pixel_ids = df.groupby(["row", "col"])
    results = []

    for (row, col), group in tqdm(pixel_ids, desc="ARIMA pixels"):
        group = group.sort_values("date")
        forecasts = forecast_pixel(group["displacement_mm"], args.horizon, order)
        for step, val in enumerate(forecasts, 1):
            results.append({"row": row, "col": col, "step": step, "forecast_mm": val})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(out, index=False)
    print(f"Saved → {out}")


if __name__ == "__main__":
    main()
