#!/usr/bin/env python3
"""
Generate an interactive HTML subset-picker for any VLM basemap figure.

Workflow:
  1. Run plot_vlm_basemap.py to generate the full-city PNG
  2. Run this script to wrap it in an interactive HTML picker
  3. Open the HTML, drag to select a region → copy the subset command

Usage:
  python generate_vlm_picker.py \\
      --image figures/vlm_over_basemap_chengdu.png \\
      --bbox "103.76 104.42 30.40 30.84" \\
      --input exports_chengdu/velocity.tif \\
      --label chengdu

  python generate_vlm_picker.py \\
      --image figures/vlm_over_basemap_beijing.png \\
      --bbox "116.10 116.80 39.60 40.20" \\
      --input exports_beijing/velocity.tif \\
      --label beijing
"""
import argparse, os, base64, io
from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--image',  required=True,
                   help='Full-city VLM basemap PNG (from plot_vlm_basemap.py)')
    p.add_argument('--bbox',   required=True,
                   help='Geographic extent of the image: LON_MIN LON_MAX LAT_MIN LAT_MAX')
    p.add_argument('--input',  required=True,
                   help='velocity.tif path (embedded in generated subset commands)')
    p.add_argument('--label',  required=True,
                   help='City/region label, e.g. chengdu')
    p.add_argument('--outdir', default=os.path.join(REPO_ROOT, 'figures'),
                   help='Directory for the output HTML file')
    p.add_argument('--preview-width', type=int, default=1100,
                   help='Preview image width in pixels (default: 1100)')
    return p.parse_args()

def encode_image(path, width):
    img = Image.open(path).convert('RGB')
    h = int(img.height * width / img.width)
    img = img.resize((width, h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=82)
    return base64.b64encode(buf.getvalue()).decode(), img.size

def build_html(b64_img, img_size, lon_min, lon_max, lat_min, lat_max,
               vel_input, label):
    img_w, img_h = img_size
    subset_script = f'scripts/mintpy/plot_vlm_subset.py'
    return f"""<title>VLM Subset Picker — {label}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 16px; }}
  h2 {{ font-size: 15px; font-weight: 600; margin-bottom: 10px; color: #a8c7fa; }}
  .container {{ display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap; }}
  .map-wrap {{
    position: relative; display: inline-block; cursor: crosshair;
    border: 2px solid #334; border-radius: 6px; overflow: hidden; flex-shrink: 0;
  }}
  #vlm-img {{ display: block; max-width: 100%; }}
  #sel-rect {{
    position: absolute; border: 2px solid #ff6b35;
    background: rgba(255,107,53,0.18); pointer-events: none; display: none;
  }}
  .panel {{
    background: #12122a; border: 1px solid #334; border-radius: 8px;
    padding: 16px; min-width: 280px; flex: 1;
  }}
  .coords {{ font-size: 13px; line-height: 2.0; }}
  .coords span {{ color: #ffd96a; font-weight: 600; font-family: monospace; }}
  .cmd-box {{
    margin-top: 14px; background: #0d1117; border-radius: 6px;
    padding: 10px 12px; font-family: monospace; font-size: 11px;
    color: #79c0ff; white-space: pre-wrap; word-break: break-all;
    border: 1px solid #30363d; min-height: 90px;
  }}
  button {{
    margin-top: 10px; padding: 7px 16px; background: #1f6feb;
    color: #fff; border: none; border-radius: 6px; cursor: pointer;
    font-size: 13px; font-weight: 600;
  }}
  button:hover {{ background: #388bfd; }}
  .reset-btn {{ background: #21262d; color: #c9d1d9; margin-left: 6px; }}
  .reset-btn:hover {{ background: #30363d; }}
  .tip {{ font-size: 11px; color: #8b949e; margin-top: 10px; line-height: 1.6; }}
  .badge {{ display:inline-block; background:#1f3a5f; color:#79c0ff;
            border-radius:4px; padding:1px 6px; font-size:11px; font-family:monospace; }}
  .region-tag {{ color:#aaa; font-size:12px; }}
</style>

<h2>VLM Subset Picker — <span style="color:#ffd96a">{label}</span>
  <span class="region-tag"> · lon [{lon_min}, {lon_max}] · lat [{lat_min}, {lat_max}]</span>
</h2>

<div class="container">
  <div class="map-wrap" id="map-wrap">
    <img id="vlm-img" src="data:image/jpeg;base64,{b64_img}" draggable="false" />
    <div id="sel-rect"></div>
  </div>

  <div class="panel">
    <div class="coords">
      <b>Cursor</b><br>
      Lon: <span id="lon-live">—</span>&nbsp; Lat: <span id="lat-live">—</span>
      <br><br>
      <b>Selection</b><br>
      LON_MIN: <span id="lon-min">—</span><br>
      LON_MAX: <span id="lon-max">—</span><br>
      LAT_MIN: <span id="lat-min">—</span><br>
      LAT_MAX: <span id="lat-max">—</span>
    </div>
    <div class="cmd-box" id="cmd-box">← Drag a rectangle on the map</div>
    <div>
      <button onclick="copyCmd()">Copy command</button>
      <button class="reset-btn" onclick="resetSel()">Clear</button>
    </div>
    <p class="tip">
      Drag on the map → copy the command → run on HPC.<br>
      Output: <span class="badge">figures/vlm_subset_&lt;label&gt;.png</span><br>
      To change colorbar range, edit <span class="badge">--vmin / --vmax</span> in the command.
    </p>
  </div>
</div>

<script>
const GEO_LON_MIN = {lon_min}, GEO_LON_MAX = {lon_max};
const GEO_LAT_MIN = {lat_min}, GEO_LAT_MAX = {lat_max};
const VEL_INPUT   = "{vel_input}";
const SUBSET_SCRIPT = "{subset_script}";

const img  = document.getElementById('vlm-img');
const rect = document.getElementById('sel-rect');
let dragging = false, startX, startY, startLon, startLat;
let selLon0, selLon1, selLat0, selLat1;

function pxToGeo(cx, cy) {{
  const r = img.getBoundingClientRect();
  const fx = (cx - r.left) / r.width;
  const fy = (cy - r.top)  / r.height;
  const lon = GEO_LON_MIN + fx * (GEO_LON_MAX - GEO_LON_MIN);
  const lat = GEO_LAT_MAX - fy * (GEO_LAT_MAX - GEO_LAT_MIN);
  return [lon, lat];
}}

img.addEventListener('mousemove', e => {{
  const [lon, lat] = pxToGeo(e.clientX, e.clientY);
  document.getElementById('lon-live').textContent = lon.toFixed(4) + '°E';
  document.getElementById('lat-live').textContent = lat.toFixed(4) + '°N';
  if (!dragging) return;
  const r   = img.getBoundingClientRect();
  const x0  = Math.min(startX, e.clientX) - r.left;
  const y0  = Math.min(startY, e.clientY) - r.top;
  rect.style.cssText = `display:block;left:${{x0}}px;top:${{y0}}px;`
    + `width:${{Math.abs(e.clientX-startX)}}px;height:${{Math.abs(e.clientY-startY)}}px;`;
  const [cLon, cLat] = pxToGeo(e.clientX, e.clientY);
  selLon0 = Math.min(startLon, cLon); selLon1 = Math.max(startLon, cLon);
  selLat0 = Math.min(startLat, cLat); selLat1 = Math.max(startLat, cLat);
  updatePanel();
}});

img.addEventListener('mousedown', e => {{
  e.preventDefault(); dragging = true;
  startX = e.clientX; startY = e.clientY;
  [startLon, startLat] = pxToGeo(e.clientX, e.clientY);
}});
window.addEventListener('mouseup', () => {{ dragging = false; }});
img.addEventListener('mouseleave', () => {{
  document.getElementById('lon-live').textContent = '—';
  document.getElementById('lat-live').textContent = '—';
}});

function updatePanel() {{
  if (selLon0 == null) return;
  document.getElementById('lon-min').textContent = selLon0.toFixed(4);
  document.getElementById('lon-max').textContent = selLon1.toFixed(4);
  document.getElementById('lat-min').textContent = selLat0.toFixed(4);
  document.getElementById('lat-max').textContent = selLat1.toFixed(4);
  const cmd = `python ${{SUBSET_SCRIPT}} \\\\\\n`
    + `  --input "${{VEL_INPUT}}" \\\\\\n`
    + `  --bbox "${{selLon0.toFixed(4)}} ${{selLon1.toFixed(4)}} ${{selLat0.toFixed(4)}} ${{selLat1.toFixed(4)}}" \\\\\\n`
    + `  --label "{label}_subset" \\\\\\n`
    + `  --vmin -20 --vmax 20`;
  document.getElementById('cmd-box').textContent = cmd;
}}

function copyCmd() {{
  navigator.clipboard.writeText(document.getElementById('cmd-box').textContent)
    .then(() => {{ const b = event.target; b.textContent='Copied ✓';
                   setTimeout(()=>b.textContent='Copy command', 1500); }});
}}
function resetSel() {{
  rect.style.display = 'none';
  selLon0=selLon1=selLat0=selLat1=null;
  ['lon-min','lon-max','lat-min','lat-max'].forEach(id=>
    document.getElementById(id).textContent='—');
  document.getElementById('cmd-box').textContent='← Drag a rectangle on the map';
}}
</script>"""

def main():
    args = parse_args()
    lon_min, lon_max, lat_min, lat_max = map(float, args.bbox.split())

    print(f"Encoding image: {args.image} …")
    b64, size = encode_image(args.image, args.preview_width)
    print(f"  Preview: {size[0]}×{size[1]} px, {len(b64)//1024}KB base64")

    html = build_html(b64, size, lon_min, lon_max, lat_min, lat_max,
                      args.input, args.label)

    os.makedirs(args.outdir, exist_ok=True)
    out = os.path.join(args.outdir, f'vlm_picker_{args.label}.html')
    with open(out, 'w') as f:
        f.write(html)
    print(f"Saved → {out}")
    print(f"\nOpen in a browser, drag to select a region, copy the command, run on HPC.")

if __name__ == '__main__':
    main()
