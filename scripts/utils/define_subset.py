#!/usr/bin/env python3
"""
Define a geographic subset bounding box for MintPy reprocessing.

Takes a named region (from configs/regions.yaml) or a raw lat/lon bounding box,
validates it against the actual data coverage (read from any GeoTIFF in EPSG:4326),
computes the exact intersection, and outputs a ready-to-use mintpy.subset.lalo line.
Optionally patches the config file in-place.

Usage:
    python define_subset.py --list
    python define_subset.py --region beijing_plain
    python define_subset.py --region beijing_plain --apply
    python define_subset.py --bbox "39.55 40.15 115.80 117.20" --label my_aoi
    python define_subset.py --region beijing_5ring \\
        --data exports_beijing_psinsar/velocity.tif \\
        --config configs/mintpy/smallbaselineApp_psinsar.cfg \\
        --apply
"""

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_REGIONS  = REPO_ROOT / "configs" / "regions.yaml"
DEFAULT_DATA     = REPO_ROOT / "exports_beijing_psinsar" / "velocity.tif"
DEFAULT_CONFIG   = REPO_ROOT / "configs" / "mintpy" / "smallbaselineApp_psinsar.cfg"


# ── I/O helpers ──────────────────────────────────────────────────────────────

def load_regions(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def data_extent(tif_path: Path) -> tuple[float, float, float, float]:
    """Return (lat_min, lat_max, lon_min, lon_max) from any EPSG:4326 GeoTIFF."""
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(str(tif_path))
    if ds is None:
        sys.exit(f"ERROR: cannot open {tif_path}")
    gt = ds.GetGeoTransform()   # (lon_origin, px_w, 0, lat_origin, 0, px_h)
    cols, rows = ds.RasterXSize, ds.RasterYSize
    lon_min = gt[0]
    lat_max = gt[3]
    lon_max = lon_min + cols * gt[1]
    lat_min = lat_max + rows * gt[5]   # gt[5] < 0
    return float(lat_min), float(lat_max), float(lon_min), float(lon_max)


def to_pixel_range(
    tif_path: Path,
    lat_min: float, lat_max: float,
    lon_min: float, lon_max: float,
) -> tuple[int, int, int, int]:
    """Convert geo bbox → (row_min, row_max, col_min, col_max) pixel indices."""
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(str(tif_path))
    gt = ds.GetGeoTransform()
    col0 = int((lon_min - gt[0]) / gt[1])
    col1 = int((lon_max - gt[0]) / gt[1])
    row0 = int((lat_max - gt[3]) / gt[5])   # gt[5] negative → row increases downward
    row1 = int((lat_min - gt[3]) / gt[5])
    col0 = max(0, col0); col1 = min(ds.RasterXSize,  col1)
    row0 = max(0, row0); row1 = min(ds.RasterYSize, row1)
    return row0, row1, col0, col1


# ── geometry ─────────────────────────────────────────────────────────────────

def intersect(
    region_lat: list[float], region_lon: list[float],
    d_lat_min: float, d_lat_max: float,
    d_lon_min: float, d_lon_max: float,
) -> tuple[float, float, float, float] | None:
    """Clip region bbox to data extent. Returns None if no overlap."""
    lat_min = max(region_lat[0], d_lat_min)
    lat_max = min(region_lat[1], d_lat_max)
    lon_min = max(region_lon[0], d_lon_min)
    lon_max = min(region_lon[1], d_lon_max)
    if lat_min >= lat_max or lon_min >= lon_max:
        return None
    return lat_min, lat_max, lon_min, lon_max


def coverage_pct(
    region_lat: list[float], region_lon: list[float],
    isect: tuple[float, float, float, float],
) -> float:
    region_area = (region_lat[1] - region_lat[0]) * (region_lon[1] - region_lon[0])
    isect_area  = (isect[1] - isect[0]) * (isect[3] - isect[2])
    return 100.0 * isect_area / region_area if region_area > 0 else 0.0


# ── config patch ─────────────────────────────────────────────────────────────

def patch_config(config_path: Path, lalo_line: str) -> str:
    """Insert or replace mintpy.subset.lalo in config. Returns 'updated'/'added'."""
    lines = config_path.read_text().splitlines(keepends=True)
    new_lines = []
    replaced = False
    for line in lines:
        if line.lstrip().startswith("mintpy.subset.lalo"):
            new_lines.append(lalo_line + "\n")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append("\n" + lalo_line + "\n")
    config_path.write_text("".join(new_lines))
    return "updated" if replaced else "added"


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region",       help="Named region from configs/regions.yaml")
    ap.add_argument("--bbox",         help="Custom bbox: 'lat_min lat_max lon_min lon_max'")
    ap.add_argument("--label",        help="Label for a custom --bbox region")
    ap.add_argument("--data",         default=str(DEFAULT_DATA),
                    help="Reference GeoTIFF (EPSG:4326) to read data extent from")
    ap.add_argument("--apply",        action="store_true",
                    help="Patch --config with the computed subset.lalo line")
    ap.add_argument("--config",       default=str(DEFAULT_CONFIG),
                    help="MintPy config file to patch (used with --apply)")
    ap.add_argument("--regions-file", default=str(DEFAULT_REGIONS),
                    help="Path to regions.yaml")
    ap.add_argument("--list",         action="store_true",
                    help="Print all predefined regions and exit")
    args = ap.parse_args()

    regions_file = Path(args.regions_file)
    regions = load_regions(regions_file) if regions_file.exists() else {}

    # ── --list ──
    if args.list:
        if not regions:
            print("No regions defined yet.")
            return
        col = max(len(k) for k in regions)
        print(f"{'Name':<{col}}  Lat [min, max]            Lon [min, max]")
        print("─" * (col + 54))
        for name, info in regions.items():
            lat, lon = info["lat"], info["lon"]
            row = f"{name:<{col}}  [{lat[0]:6.2f}, {lat[1]:6.2f}]°N   [{lon[0]:7.2f}, {lon[1]:7.2f}]°E"
            print(row)
            if "desc" in info:
                print(f"{'':>{col}}  {info['desc']}")
        return

    # ── resolve region ──
    if args.region:
        if args.region not in regions:
            sys.exit(f"Region '{args.region}' not found. Run --list to see options.")
        info  = regions[args.region]
        label = args.region
        r_lat, r_lon = info["lat"], info["lon"]
    elif args.bbox:
        parts = list(map(float, args.bbox.split()))
        if len(parts) != 4:
            sys.exit("--bbox needs exactly 4 values: lat_min lat_max lon_min lon_max")
        r_lat = [parts[0], parts[1]]
        r_lon = [parts[2], parts[3]]
        label = args.label or "custom"
        info  = {"desc": label}
    else:
        ap.print_help()
        return

    # ── data extent ──
    tif = Path(args.data)
    if not tif.exists():
        sys.exit(f"Data file not found: {tif}\n"
                 f"Pass a valid GeoTIFF via --data.")
    d_lat_min, d_lat_max, d_lon_min, d_lon_max = data_extent(tif)

    # ── intersection ──
    isect = intersect(r_lat, r_lon, d_lat_min, d_lat_max, d_lon_min, d_lon_max)
    if isect is None:
        sys.exit(f"Region '{label}' has no overlap with data extent.\n"
                 f"  Region : lat [{r_lat[0]}, {r_lat[1]}]  lon [{r_lon[0]}, {r_lon[1]}]\n"
                 f"  Data   : lat [{d_lat_min:.4f}, {d_lat_max:.4f}]  "
                 f"lon [{d_lon_min:.4f}, {d_lon_max:.4f}]")
    lat_min, lat_max, lon_min, lon_max = isect
    cov = coverage_pct(r_lat, r_lon, isect)

    # ── pixel range in reference tif ──
    r0, r1, c0, c1 = to_pixel_range(tif, lat_min, lat_max, lon_min, lon_max)

    # ── clipping report ──
    clipped = []
    if r_lat[0] < d_lat_min: clipped.append(f"south clipped  ({r_lat[0]:.2f}° → {d_lat_min:.4f}°)")
    if r_lat[1] > d_lat_max: clipped.append(f"north clipped  ({r_lat[1]:.2f}° → {d_lat_max:.4f}°)")
    if r_lon[0] < d_lon_min: clipped.append(f"west clipped   ({r_lon[0]:.2f}° → {d_lon_min:.4f}°)")
    if r_lon[1] > d_lon_max: clipped.append(f"east clipped   ({r_lon[1]:.2f}° → {d_lon_max:.4f}°)")

    # ── output ──
    print(f"\nRegion       : {label}")
    if "desc" in info:
        print(f"Description  : {info['desc']}")
    print(f"Requested    : lat [{r_lat[0]:.4f}, {r_lat[1]:.4f}]  "
          f"lon [{r_lon[0]:.4f}, {r_lon[1]:.4f}]")
    print(f"Data extent  : lat [{d_lat_min:.4f}, {d_lat_max:.4f}]  "
          f"lon [{d_lon_min:.4f}, {d_lon_max:.4f}]")
    if clipped:
        print("Clipping     :")
        for c in clipped:
            print(f"  ⚠  {c}")
    print(f"Intersection : lat [{lat_min:.4f}, {lat_max:.4f}]  "
          f"lon [{lon_min:.4f}, {lon_max:.4f}]")
    print(f"Coverage     : {cov:.1f}% of requested region lies within data")
    print(f"Pixel range  : rows [{r0}, {r1}] ({r1-r0} px)  "
          f"cols [{c0}, {c1}] ({c1-c0} px)")

    lalo_line = (f"mintpy.subset.lalo = "
                 f"{lat_min:.4f}:{lat_max:.4f},{lon_min:.4f}:{lon_max:.4f}")
    print(f"\n{lalo_line}\n")

    if args.apply:
        cfg = Path(args.config)
        if not cfg.exists():
            sys.exit(f"Config not found: {cfg}")
        action = patch_config(cfg, lalo_line)
        print(f"  {action.capitalize()} mintpy.subset.lalo in {cfg}")
        print("  Next: resubmit PBS job (qsub jobs/mintpy_job.pbs) to rerun from load_data.")
    else:
        print("  Add the line above to smallbaselineApp_psinsar.cfg, or re-run with --apply.")


if __name__ == "__main__":
    main()
