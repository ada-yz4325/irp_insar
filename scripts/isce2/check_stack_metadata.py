"""
Stage 1 — scan a Sentinel-1 SLC stack and validate geometric consistency.

Every scene in the stack must share the same relative orbit, pass direction,
acquisition mode and polarization, and must overlap the reference scene's
footprint above a minimum fraction (proxy for "same burst coverage" — IW SLC
manifests don't carry a discrete ASF frame number, so footprint overlap is
the practical consistency check at this stage; exact burst-level agreement
is confirmed later once stackSentinel.py builds the stack, see
scripts/isce2/record_burst_subset.py).

Fails loudly (non-zero exit) on the first set of mismatches found, rather
than silently stacking inconsistent geometries.

Usage:
    python check_stack_metadata.py --slc-dir <dir> --out metadata/stack_inventory.csv
"""

import argparse
import csv
import re
import sys
import zipfile
from pathlib import Path

# S1A_IW_SLC__1SSV_20240701T100607_20240701T100607_054566_06A43B_C0A4.zip
FNAME_RE = re.compile(
    r"^(?P<mission>S1[AB])_(?P<mode>\w{2})_SLC__"
    r"(?P<level>\d)(?P<prod_class>S)(?P<pol>\w{2})_"
    r"(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})_"
    r"(?P<abs_orbit>\d{6})_(?P<datatake>[0-9A-F]{6})_(?P<uid>[0-9A-F]{4})"
)

POL_CODE = {"SV": "VV", "SH": "HH", "DV": "VV+VH", "DH": "HH+HV"}


def parse_filename(zip_path: Path) -> dict:
    m = FNAME_RE.match(zip_path.stem)
    if not m:
        sys.exit(f"Filename does not match Sentinel-1 SLC naming convention: {zip_path.name}")
    g = m.groupdict()
    return {
        "scene": zip_path.stem,
        "mission": g["mission"],
        "mode": g["mode"],
        "polarization": POL_CODE.get(g["pol"], g["pol"]),
        "acquisition_date": g["start"][:8],
        "abs_orbit": int(g["abs_orbit"]),
    }


def parse_manifest(zip_path: Path) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        manifest_name = next(n for n in zf.namelist() if n.endswith("manifest.safe"))
        text = zf.read(manifest_name).decode("utf-8", errors="ignore")

    pass_dir_m = re.search(r"<s1:pass>([A-Z]+)</s1:pass>", text)
    rel_orbit_m = re.search(r'relativeOrbitNumber type="start">(\d+)', text)
    coords_m = re.search(r"<gml:coordinates>([^<]+)</gml:coordinates>", text)

    if not (pass_dir_m and rel_orbit_m and coords_m):
        sys.exit(f"Could not parse required fields from manifest.safe in {zip_path.name}")

    coords = [tuple(map(float, pair.split(","))) for pair in coords_m.group(1).split()]
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]

    return {
        "pass_direction": pass_dir_m.group(1),
        "relative_orbit": int(rel_orbit_m.group(1)),
        "bbox_snwe": (min(lats), max(lats), min(lons), max(lons)),
    }


def bbox_overlap_fraction(a: tuple, b: tuple) -> float:
    """Fraction of bbox `a`'s area that overlaps with bbox `b`."""
    s, n = max(a[0], b[0]), min(a[1], b[1])
    w, e = max(a[2], b[2]), min(a[3], b[3])
    if n <= s or e <= w:
        return 0.0
    inter = (n - s) * (e - w)
    area_a = (a[1] - a[0]) * (a[3] - a[2])
    return inter / area_a if area_a > 0 else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slc-dir", required=True)
    ap.add_argument("--out", required=True, help="Output stack_inventory.csv path")
    ap.add_argument(
        "--min-overlap", type=float, default=0.5,
        help="Minimum fractional footprint overlap vs the reference scene (default 0.5)",
    )
    args = ap.parse_args()

    slc_dir = Path(args.slc_dir)
    zips = sorted(slc_dir.glob("*.zip"))
    if not zips:
        sys.exit(f"No SLC zips found in {slc_dir}")

    rows = []
    for z in zips:
        meta = parse_filename(z)
        meta.update(parse_manifest(z))
        rows.append(meta)
    rows.sort(key=lambda r: r["acquisition_date"])

    ref = rows[0]
    errors = []
    for r in rows[1:]:
        for field in ("relative_orbit", "pass_direction", "polarization", "mode"):
            if r[field] != ref[field]:
                errors.append(
                    f"{r['scene']}: {field}={r[field]!r} != reference {field}={ref[field]!r}"
                )
        overlap = bbox_overlap_fraction(r["bbox_snwe"], ref["bbox_snwe"])
        r["footprint_overlap_vs_reference"] = round(overlap, 4)
        if overlap < args.min_overlap:
            errors.append(
                f"{r['scene']}: footprint overlap {overlap:.2f} < min {args.min_overlap} "
                f"vs reference scene {ref['scene']} -- inconsistent burst coverage"
            )
    ref["footprint_overlap_vs_reference"] = 1.0

    if errors:
        print(f"STACK METADATA VALIDATION FAILED ({len(errors)} issue(s)):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scene", "acquisition_date", "mission", "mode", "polarization",
        "relative_orbit", "pass_direction", "abs_orbit",
        "bbox_snwe", "footprint_overlap_vs_reference",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"OK: {len(rows)} scenes validated consistent "
        f"(track {ref['relative_orbit']}, {ref['pass_direction']}, {ref['polarization']}, "
        f"{ref['mode']}). Wrote {out_path}"
    )


if __name__ == "__main__":
    main()
