"""
Extract and compare Sentinel-1 SLC quicklook thumbnails across dates.

Each SLC .zip contains a low-res preview PNG at:
    <SAFE>/preview/quick-look.png
This script pulls that image out (no need to unzip the whole archive)
for one or more scenes and arranges them side-by-side with date labels.

Usage:
    # Compare N scenes evenly spread across the available date range
    python scripts/utils/preview_slc.py --n 4

    # Compare specific scenes by index (see list_slc.sh for indices)
    python scripts/utils/preview_slc.py --index 1 20 46

    # Use a different SLC directory / output path
    python scripts/utils/preview_slc.py --slc-dir /path/to/slc --out figures/compare.png
"""

import argparse
import zipfile
from pathlib import Path

import matplotlib.pyplot as plt
from PIL import Image

DEFAULT_SLC_DIR = "/rds/general/user/yz4325/ephemeral/irp_insar/data/raw/slc"
DEFAULT_OUT = "figures/slc_preview_compare.png"


def extract_quicklook(zip_path: Path) -> Image.Image:
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith("preview/quick-look.png"))
        with zf.open(name) as f:
            return Image.open(f).convert("RGB").copy()


def scene_date(zip_path: Path) -> str:
    name = zip_path.name
    raw = name[17:25]  # YYYYMMDD
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slc-dir", default=DEFAULT_SLC_DIR)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--n", type=int, default=4,
                        help="Number of scenes to compare, evenly spaced by date")
    parser.add_argument("--index", type=int, nargs="+",
                        help="Specific 1-based scene indices to compare (overrides --n)")
    args = parser.parse_args()

    files = sorted(Path(args.slc_dir).glob("*.zip"))
    if not files:
        print(f"No SLC zips found in {args.slc_dir}")
        return

    if args.index:
        chosen = [files[i - 1] for i in args.index]
    else:
        n = min(args.n, len(files))
        step = (len(files) - 1) / max(n - 1, 1)
        chosen = [files[round(i * step)] for i in range(n)]

    print(f"Comparing {len(chosen)} scenes:")
    for f in chosen:
        print(f"  {scene_date(f)}  {f.name}")

    fig, axes = plt.subplots(1, len(chosen), figsize=(5 * len(chosen), 6))
    if len(chosen) == 1:
        axes = [axes]

    for ax, f in zip(axes, chosen):
        img = extract_quicklook(f)
        ax.imshow(img)
        ax.set_title(scene_date(f), fontsize=12)
        ax.axis("off")

    plt.tight_layout()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    print(f"\nSaved comparison → {out_path}")


if __name__ == "__main__":
    main()
