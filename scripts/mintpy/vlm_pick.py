#!/usr/bin/env python3
"""
One-command VLM subset picker launcher.

Generates the interactive HTML picker (if not already done) and starts
a local HTTP server. VS Code SSH auto-detects the URL and offers to open
it in your local browser.

Usage:
  python scripts/mintpy/vlm_pick.py --label chengdu
  python scripts/mintpy/vlm_pick.py --label beijing --bbox "116.1 116.8 39.6 40.2"
  python scripts/mintpy/vlm_pick.py --label chengdu --port 8800 --regen

Conventions (auto-resolved from --label):
  velocity.tif  →  exports_<label>/velocity.tif
  basemap PNG   →  figures/vlm_over_basemap_<label>.png
  picker HTML   →  figures/vlm_picker_<label>.html
"""
import argparse, os, sys, subprocess, http.server, threading, socket, webbrowser

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS = os.path.join(REPO, 'scripts', 'mintpy')

BBOX_DEFAULTS = {
    'chengdu': '103.76 104.42 30.40 30.84',
    'beijing': '115.90 117.00 39.50 40.30',
}

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--label', required=True,
                   help='City label, e.g. chengdu or beijing')
    p.add_argument('--bbox', default=None,
                   help='LON_MIN LON_MAX LAT_MIN LAT_MAX — required if not in built-in defaults')
    p.add_argument('--port', type=int, default=8787,
                   help='HTTP server port (default: 8787)')
    p.add_argument('--regen', action='store_true',
                   help='Force regenerate picker HTML even if it already exists')
    return p.parse_args()

def find_free_port(preferred):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('localhost', preferred)) != 0:
            return preferred
    # preferred in use — find another
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def main():
    args = parse_args()
    label = args.label

    vel_tif  = os.path.join(REPO, f'exports_{label}', 'velocity.tif')
    base_png = os.path.join(REPO, 'figures', f'vlm_over_basemap_{label}.png')
    html_out = os.path.join(REPO, 'figures', f'vlm_picker_{label}.html')

    # --- resolve bbox ---
    bbox = args.bbox or BBOX_DEFAULTS.get(label)
    if bbox is None:
        sys.exit(f"ERROR: no --bbox given and '{label}' not in built-in defaults.\n"
                 f"       Pass --bbox \"LON_MIN LON_MAX LAT_MIN LAT_MAX\"")

    # --- check velocity.tif ---
    if not os.path.exists(vel_tif):
        sys.exit(f"ERROR: velocity.tif not found at {vel_tif}\n"
                 f"       Run MintPy pipeline for '{label}' first.")

    # --- generate basemap PNG if missing ---
    if not os.path.exists(base_png):
        print(f"[1/2] Generating full-city basemap PNG for '{label}' …")
        subprocess.run([
            sys.executable,
            os.path.join(SCRIPTS, 'plot_vlm_basemap.py'),
            '--input', vel_tif,
            '--label', label,
            '--bbox', bbox,
        ], check=True)
    else:
        print(f"[1/2] Basemap PNG found: {base_png}")

    # --- generate picker HTML if missing or --regen ---
    if not os.path.exists(html_out) or args.regen:
        print(f"[2/2] Generating interactive picker HTML …")
        subprocess.run([
            sys.executable,
            os.path.join(SCRIPTS, 'generate_vlm_picker.py'),
            '--image', base_png,
            '--bbox', bbox,
            '--input', vel_tif,
            '--label', label,
        ], check=True)
    else:
        print(f"[2/2] Picker HTML found: {html_out}")

    # --- serve ---
    port = find_free_port(args.port)
    fig_dir = os.path.join(REPO, 'figures')
    url = f"http://localhost:{port}/vlm_picker_{label}.html"

    handler = http.server.SimpleHTTPRequestHandler
    handler.log_message = lambda *a: None  # suppress request logs

    server = http.server.HTTPServer(('', port), handler)

    print()
    print("=" * 60)
    print(f"  VLM Subset Picker ready — {label}")
    print(f"  {url}")
    print("=" * 60)
    print("  VS Code SSH: click the URL above (auto port-forwarded)")
    print("  Manual:  ssh -L {port}:localhost:{port} <hpc-host>".format(port=port))
    print("           then open the URL in your local browser")
    print()
    print("  Drag on the map to select a region.")
    print("  Copy the generated command and run it in a new terminal.")
    print()
    print("  Ctrl+C to stop the server.")
    print()

    os.chdir(fig_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

if __name__ == '__main__':
    main()
