"""
Resumable Sentinel-1 SLC download — like download_s1.py, but:
  - skips scenes already present at a plausible complete size (>=3GB for
    dual-pol IW SLC; catches truncated partial downloads from a dropped
    connection, not just fully-missing files)
  - retries the remaining scenes in rounds with backoff, since asf_search's
    own results.download() has no retry and a single transient SSL error
    (observed: "ssl.SSLError: record layer failure") kills the whole batch

Usage:
    python resume_download_s1.py --config download_config.yml [--rounds 5]
"""
import argparse
import netrc
import time
from pathlib import Path

import asf_search as asf
import yaml


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


def search_scenes(cfg):
    pol_map = {
        "VV+VH": asf.POLARIZATION.VV_VH, "VV": asf.POLARIZATION.VV,
        "HH+HV": asf.POLARIZATION.HH_HV, "HH": asf.POLARIZATION.HH,
    }
    pol = pol_map.get(cfg.get("polarization", "VV+VH"), asf.POLARIZATION.VV_VH)
    return asf.search(
        platform=asf.PLATFORM.SENTINEL1, processingLevel=asf.PRODUCT_TYPE.SLC,
        beamMode=asf.BEAMMODE.IW, polarization=pol, intersectsWith=cfg["aoi"],
        start=cfg["start"], end=cfg["end"], relativeOrbit=cfg.get("track"),
        asfFrame=cfg.get("frame"), flightDirection=cfg.get("pass_dir"),
        maxResults=cfg.get("max_results", 300),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--min-complete-bytes", type=int, default=3_000_000_000)
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(cfg["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Searching ASF for full expected scene list...")
    results = search_scenes(cfg)
    print(f"Expected: {len(results)} scenes")

    creds = netrc.netrc().authenticators("urs.earthdata.nasa.gov")
    session = asf.ASFSession().auth_with_creds(creds[0], creds[2])

    for rnd in range(1, args.rounds + 1):
        missing = []
        for r in results:
            fname = out_dir / (r.properties["fileName"])
            if not fname.exists() or fname.stat().st_size < args.min_complete_bytes:
                if fname.exists():
                    print(f"  incomplete, removing: {fname.name} ({fname.stat().st_size/1e9:.2f} GB)")
                    fname.unlink()
                missing.append(r)

        print(f"\n=== Round {rnd}/{args.rounds}: {len(missing)} scenes missing/incomplete ===")
        if not missing:
            print("All scenes present and complete.")
            break

        try:
            asf.ASFSearchResults(missing).download(path=str(out_dir), session=session, processes=4)
        except Exception as e:
            wait = min(60 * rnd, 300)
            print(f"  Round {rnd} hit an error: {e!r}")
            print(f"  Waiting {wait}s before next round...")
            time.sleep(wait)
            continue

    # final check
    still_missing = []
    for r in results:
        fname = out_dir / (r.properties["fileName"])
        if not fname.exists() or fname.stat().st_size < args.min_complete_bytes:
            still_missing.append(r.properties["sceneName"])
    if still_missing:
        print(f"\nWARNING: {len(still_missing)} scenes still missing/incomplete after {args.rounds} rounds:")
        for s in still_missing:
            print(f"  {s}")
        raise SystemExit(1)
    else:
        print(f"\nSUCCESS: all {len(results)} scenes present and >= {args.min_complete_bytes/1e9:.1f} GB")


if __name__ == "__main__":
    main()
