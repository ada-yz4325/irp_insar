#!/bin/bash
# Quick summary of downloaded Sentinel-1 SLC scenes.
#
# Usage:
#   bash scripts/utils/list_slc.sh [slc_dir]
#
# Defaults to the ephemeral raw SLC directory if no path is given.

SLC_DIR="${1:-/rds/general/user/yz4325/ephemeral/irp_insar/data/raw/slc}"

if [ ! -d "$SLC_DIR" ]; then
    echo "Directory not found: $SLC_DIR"
    exit 1
fi

shopt -s nullglob
files=("$SLC_DIR"/*.zip)
shopt -u nullglob

if [ ${#files[@]} -eq 0 ]; then
    echo "No SLC zip files found in: $SLC_DIR"
    exit 0
fi

echo "SLC directory: $SLC_DIR"
echo ""
printf "%-5s %-12s %-12s %-9s %-7s %s\n" "#" "Date" "Satellite" "AbsOrbit" "Size" "Filename"
printf '%s\n' "------------------------------------------------------------------------------------------------"

i=0
for f in "${files[@]}"; do
    i=$((i + 1))
    name=$(basename "$f")
    sat=${name:0:3}
    date=${name:17:8}
    date_fmt="${date:0:4}-${date:4:2}-${date:6:2}"
    orbit=$(echo "$name" | grep -oP '(?<=_)\d{6}(?=_[0-9A-F]{6}_[0-9A-F]{4}\.zip)')
    size=$(du -h "$f" | cut -f1)
    printf "%-5s %-12s %-12s %-9s %-7s %s\n" "$i" "$date_fmt" "$sat" "${orbit:-?}" "$size" "$name"
done

echo ""
echo "Summary:"
echo "  Total scenes : ${#files[@]}"
echo "  Total size   : $(du -ch "${files[@]}" 2>/dev/null | tail -1 | cut -f1)"
echo "  Date range   : $(basename "${files[0]}" | cut -c18-25) -> $(basename "${files[-1]}" | cut -c18-25)"
echo "  By satellite :"
for f in "${files[@]}"; do basename "$f" | cut -c1-3; done | sort | uniq -c | awk '{printf "    %s : %s\n", $2, $1}'
