"""
Download Sentinel-1 SLC scenes from ASF via asf_search.

Usage:
    python download_s1.py --config download_config.yml

Config keys:
    aoi        : WKT polygon or bounding box [lon_min lat_min lon_max lat_max]
    start      : YYYY-MM-DD
    end        : YYYY-MM-DD
    track      : relative orbit number (int)
    pass_dir   : ASCENDING | DESCENDING
    out_dir    : local destination directory
    max_results: cap on number of scenes
"""

import argparse
import yaml
import asf_search as asf
from pathlib import Path


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def search_scenes(cfg: dict) -> list:
    aoi = cfg["aoi"]
    results = asf.search(
        platform=asf.PLATFORM.SENTINEL1,
        processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=asf.BEAMMODE.IW,
        intersectsWith=aoi,
        start=cfg["start"],
        end=cfg["end"],
        relativeOrbit=cfg.get("track"),
        flightDirection=cfg.get("pass_dir"),
        maxResults=cfg.get("max_results", 200),
    )
    return results


def download_scenes(results, out_dir: Path, session) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    results.download(path=str(out_dir), session=session, processes=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(cfg["out_dir"])

    print(f"Searching ASF for Sentinel-1 SLC scenes...")
    results = search_scenes(cfg)
    print(f"Found {len(results)} scenes")

    session = asf.ASFSession().auth_with_creds(
        cfg["earthdata_user"], cfg["earthdata_password"]
    )
    download_scenes(results, out_dir, session)
    print(f"Download complete → {out_dir}")


if __name__ == "__main__":
    main()
