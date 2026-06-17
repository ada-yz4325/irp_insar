"""
Translate the project's INI-style topsStack config into a stackSentinel.py
CLI argument list. stackSentinel.py does not accept config files directly —
it is a pure CLI tool — so this bridges our [topsStack] cfg format to it.

Usage:
    python cfg_to_stacksentinel_args.py configs/isce2/topsStack_template.cfg
    (prints a space-separated argument string to stdout)
"""

import configparser
import glob
import os
import shlex
import sys


def find_dem_file(dem_dir: str) -> str:
    candidates = glob.glob(os.path.join(dem_dir, "*.dem"))
    if not candidates:
        sys.exit(f"No .dem file found in {dem_dir}. Run download_dem.py first.")
    return candidates[0]


def main():
    if len(sys.argv) != 2:
        sys.exit("Usage: cfg_to_stacksentinel_args.py <config.cfg>")

    cfg = configparser.ConfigParser(inline_comment_prefixes=("#",))
    cfg.read(sys.argv[1])
    c = cfg["topsStack"]

    dem_file = find_dem_file(c["demDir"])

    args = [
        "-s", c["slcDir"],
        "-o", c["orbitDir"],
        "-a", c["auxDir"],
        "-w", c["workDir"],
        "-d", dem_file,
        "-n", c.get("swathNum", "1 2 3").replace(",", " "),
        "-c", c.get("numConnections", "3"),
        "--num_proc", c.get("numProcess", "8"),
        "-f", c.get("filterStrength", "0.5"),
        "-u", c.get("unwMethod", "snaphu"),
        "-C", "NESD" if c.getboolean("doESD", True) else "geometry",
    ]

    master_date = c.get("masterDate", "").strip()
    if master_date:
        args += ["-m", master_date]

    if c.getboolean("useGPU", False):
        args += ["-useGPU"]

    # shlex.quote ensures multi-word values (e.g. "-n 1 2 3") survive
    # the bash `eval` in run_topsStack.sh as a single token
    print(" ".join(shlex.quote(a) for a in args))


if __name__ == "__main__":
    main()
