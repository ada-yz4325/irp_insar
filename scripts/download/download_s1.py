"""
Download Sentinel-1 SLC scenes from ASF via asf_search.

Usage:
    python download_s1.py --config download_config.yml           # download
    python download_s1.py --config download_config.yml --dry-run # search only, no download

Authentication: uses ~/.netrc (machine urs.earthdata.nasa.gov)
"""

import argparse
import netrc
import yaml
import asf_search as asf
from pathlib import Path
from datetime import datetime


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def search_scenes(cfg: dict) -> asf.ASFSearchResults:
    polarization_map = {
        "VV+VH": asf.POLARIZATION.VV_VH,
        "VV":    asf.POLARIZATION.VV,
        "HH+HV": asf.POLARIZATION.HH_HV,
        "HH":    asf.POLARIZATION.HH,
    }
    pol = polarization_map.get(cfg.get("polarization", "VV+VH"), asf.POLARIZATION.VV_VH)

    results = asf.search(
        platform=asf.PLATFORM.SENTINEL1,
        processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=asf.BEAMMODE.IW,
        polarization=pol,
        intersectsWith=cfg["aoi"],
        start=cfg["start"],
        end=cfg["end"],
        relativeOrbit=cfg.get("track"),
        asfFrame=cfg.get("frame"),
        flightDirection=cfg.get("pass_dir"),
        maxResults=cfg.get("max_results", 300),
    )
    return results


def print_scene_table(results: asf.ASFSearchResults) -> None:
    print(f"\n{'#':<5} {'Scene name':<65} {'Date':<12} {'Track':<7} {'Direction'}")
    print("-" * 110)
    for i, r in enumerate(results, 1):
        p = r.properties
        date = p.get("startTime", "")[:10]
        track = p.get("pathNumber", "?")
        direction = p.get("flightDirection", "?")
        name = p.get("sceneName", "?")
        print(f"{i:<5} {name:<65} {date:<12} {track:<7} {direction}")
    print(f"\nTotal: {len(results)} scenes\n")


def main():
    parser = argparse.ArgumentParser(description="Download Sentinel-1 SLC from ASF")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Search and list scenes only, do not download")
    args = parser.parse_args()

    cfg = load_config(args.config)

    print(f"Searching ASF for Sentinel-1 IW SLC scenes...")
    print(f"  AOI       : {cfg['aoi'][:60]}...")
    print(f"  Date range: {cfg['start']} → {cfg['end']}")
    print(f"  Track     : {cfg.get('track', 'any')}")
    print(f"  Direction : {cfg.get('pass_dir', 'any')}")
    print(f"  Polar.    : {cfg.get('polarization', 'VV+VH')}")

    results = search_scenes(cfg)
    print_scene_table(results)

    if args.dry_run:
        print("Dry-run mode: no files downloaded.")
        return

    if len(results) == 0:
        print("No scenes found. Check your AOI, track, and date range.")
        return

    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Downloading {len(results)} scenes to: {out_dir}")
    creds = netrc.netrc().authenticators("urs.earthdata.nasa.gov")
    session = asf.ASFSession().auth_with_creds(creds[0], creds[2])
    results.download(path=str(out_dir), session=session, processes=4)
    print(f"\nDownload complete → {out_dir}")


if __name__ == "__main__":
    main()
