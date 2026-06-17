"""
Download a Copernicus GLO-30 DEM covering the study AOI and convert it
to ISCE2's expected .dem format.

Uses dem_stitcher (public AWS-hosted Copernicus DEM, no auth needed) —
ISCE2's bundled dem.py points at a defunct NASA LP DAAC URL.

Usage:
    python download_dem.py --bbox 30.4 30.9 103.8 104.4 --out-dir /path/to/dem

bbox order: south north west east
"""

import argparse
import os
import subprocess
import sys

import rasterio
from dem_stitcher import stitch_dem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", type=float, nargs=4, required=True,
                        metavar=("SOUTH", "NORTH", "WEST", "EAST"))
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--buffer", type=float, default=0.2,
                        help="Degrees of buffer to add beyond AOI (default 0.2)")
    args = parser.parse_args()

    south, north, west, east = args.bbox
    b = args.buffer
    bounds = [west - b, south - b, east + b, north + b]  # dem_stitcher: W S E N

    os.makedirs(args.out_dir, exist_ok=True)
    tif_path = os.path.join(args.out_dir, "dem_glo30.tif")
    dem_path = os.path.join(args.out_dir, "dem.dem")

    print(f"Fetching Copernicus GLO-30 DEM for bounds {bounds} ...")
    array, profile = stitch_dem(
        bounds,
        dem_name="glo_30",
        dst_ellipsoidal_height=True,   # ISCE2 needs WGS84 ellipsoidal height, not orthometric
        dst_area_or_point="Point",
    )

    with rasterio.open(tif_path, "w", **profile) as dst:
        dst.write(array, 1)
    print(f"Wrote GeoTIFF: {tif_path}")

    # Convert to ISCE2's native .dem format (raw binary + .xml + .vrt)
    subprocess.run(
        ["gdal_translate", "-of", "ISCE", tif_path, dem_path],
        check=True,
    )

    isce_home = os.environ.get("ISCE_HOME")
    fix_xml = os.path.join(isce_home, "applications", "fixImageXml.py") if isce_home else None
    if fix_xml and os.path.isfile(fix_xml):
        subprocess.run([sys.executable, fix_xml, "-i", dem_path, "-f"], check=True)

    print(f"\nISCE2-ready DEM: {dem_path}")
    print(f"  (.dem.xml and .dem.vrt generated alongside)")


if __name__ == "__main__":
    main()
