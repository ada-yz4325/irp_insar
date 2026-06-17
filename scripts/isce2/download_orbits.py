"""
Download Sentinel-1 precise orbit files (POEORB) for every SLC in a directory.

Wraps the `eof` CLI (sentineleof package). ASF precise orbits are now
public — no EarthData/CDSE login required.

Usage:
    python download_orbits.py --slc-dir /path/to/slc --out-dir /path/to/orbits
"""

import argparse
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slc-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    cmd = [
        "eof",
        "--search-path", args.slc_dir,
        "--save-dir", args.out_dir,
        "--force-asf",          # public ASF mirror, no auth needed
        "--max-workers", "6",
    ]
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
