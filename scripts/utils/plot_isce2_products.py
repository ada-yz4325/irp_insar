"""
Visualization checkpoints for ISCE2 topsStack outputs.

Plots coherence, wrapped interferogram phase, or unwrapped phase for a
single interferogram pair so progress can be sanity-checked without
waiting for the full stack / MintPy to finish.

Usage:
    python plot_isce2_products.py --product coherence \
        --file /path/to/isce2/merged/interferograms/20200620_20200702/filt_fine.cor

    python plot_isce2_products.py --product unwrapped \
        --file /path/to/isce2/merged/interferograms/20200620_20200702/filt_fine.unw

    python plot_isce2_products.py --product wrapped \
        --file /path/to/isce2/merged/interferograms/20200620_20200702/filt_fine.int
"""

import argparse
from pathlib import Path

import isce
import isceobj
import matplotlib.pyplot as plt
import numpy as np


def load_isce_image(path: str) -> np.ndarray:
    img = isceobj.createImage()
    img.load(path + ".xml")
    width = img.getWidth()
    length = img.getLength()
    dtype = {
        "FLOAT": np.float32,
        "CFLOAT": np.complex64,
        "DOUBLE": np.float64,
    }.get(img.dataType.upper(), np.float32)
    data = np.fromfile(path, dtype=dtype).reshape(length, width)
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to ISCE binary product (no .xml suffix)")
    parser.add_argument("--product", required=True,
                        choices=["coherence", "wrapped", "unwrapped"])
    parser.add_argument("--out", default=None, help="Output PNG path (default: figures/<name>_<product>.png)")
    args = parser.parse_args()

    data = load_isce_image(args.file)

    fig, ax = plt.subplots(figsize=(8, 6))
    if args.product == "coherence":
        im = ax.imshow(data, cmap="gray", vmin=0, vmax=1)
        plt.colorbar(im, label="Coherence")
        title = "Coherence"
    elif args.product == "wrapped":
        im = ax.imshow(np.angle(data), cmap="hsv", vmin=-np.pi, vmax=np.pi)
        plt.colorbar(im, label="Wrapped phase (rad)")
        title = "Wrapped interferogram"
    else:  # unwrapped — band 2 of .unw is phase, band 1 is amplitude
        phase = data[1::2] if data.ndim == 1 else data
        im = ax.imshow(data, cmap="jet")
        plt.colorbar(im, label="Unwrapped phase (rad)")
        title = "Unwrapped phase"

    ax.set_title(f"{title}\n{Path(args.file).name}")
    plt.tight_layout()

    out_path = Path(args.out) if args.out else Path("figures") / f"{Path(args.file).stem}_{args.product}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"Saved → {out_path}")


if __name__ == "__main__":
    main()
