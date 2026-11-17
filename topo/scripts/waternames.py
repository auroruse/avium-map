"""Where each water name sits on the Satellite map, and how much water it has there: src/data/water.json.

On the drawn maps a sea's name is spread across the sea and its hand-placed point is the middle of that spread. The
Satellite map sets the same names small (main.ts, satWater), and a small name has to sit inside its water: over a lake
it must not be printed across the shore, and it must not appear at all until the lake is big enough on screen to hold
it. Neither can be read off the hand-placed point or the hand-set span, so both are measured here against the land.

For every ocean and sea in labels.json this finds the widest box of the name's own shape (its lines as main.ts breaks
them, labelLines) that is water, allowing TOL of it to be shore, centred on the hand-placed point or on a point near
it. A wider berth has to pay for the move, and is worth nothing past what the name needs at the zoom it first appears,
so an open sea keeps the point it was given and a lake's name slides to the lake's broad end. Out: {NAME: [x, y, w]}
in px of the 6000 grid, w the width of that box. main.ts shows a name once it fits in w and grows it no wider than w.

Run after the coast or the water names change:  cd topo && .venv/bin/python -I scripts/waternames.py
With `check` it prints, for every name and user zoom, the share of the drawn name that lies on land."""
import json, math, os, re, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
ADV = 0.565 + 0.08        # ADVANCE.waterSat in main.ts
LINE = 1.22               # the line height of body.hybridmap .label-sea span in style.css
WRAP, WRAP_MAX = 9, 3     # SAT_WRAP_CHARS and WRAP_MAX in main.ts
MIN_FS = 10               # SAT_WATER.min in main.ts
TOL = 0.08                # the share of the name's box that may be shore
MOVE = 0.6                # px of width a px of movement has to buy

land = np.load(os.path.join(ROOT, "topo/work/land12k.npy"), mmap_mode="r")
N = land.shape[0]; K = N / 6000
SAT = np.pad(np.asarray(land, dtype=np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))

def landfrac(cx, cy, w, h):
    """Share of a box (6000-grid px) that is land; a box off the map counts as all land"""
    x0, x1 = int(round((cx - w / 2) * K)), int(round((cx + w / 2) * K)); y0, y1 = int(round((cy - h / 2) * K)), int(round((cy + h / 2) * K))
    if x0 < 0 or y0 < 0 or x1 > N or y1 > N: return 1.0
    x1, y1 = max(x1, x0 + 1), max(y1, y0 + 1)
    return (SAT[y1, x1] - SAT[y0, x1] - SAT[y1, x0] + SAT[y0, x0]) / ((x1 - x0) * (y1 - y0))

def lines(text):
    """labelLines' Satellite rule in main.ts: lines of WRAP characters at most, WRAP_MAX of them"""
    out = [""]
    for t in [t for t in re.split(r"(?<=-)|\s+", text) if t]:
        cur = out[-1]; j = cur + (" " if cur and not cur.endswith("-") else "") + t
        if cur and len(j) > WRAP and len(out) < WRAP_MAX: out.append(t)
        else: out[-1] = j
    return out

def cap(span):            # satWaterCap in main.ts
    return min(17, max(10.5, 9.5 + 1.25 * math.log2(span / 20)))

def widest(cx, cy, asp, hi):
    if landfrac(cx, cy, 1, 1) > 0: return 0.0
    lo = 0.0
    for _ in range(14):
        mid = (lo + hi) / 2
        if landfrac(cx, cy, mid, mid / asp) <= TOL: lo = mid
        else: hi = mid
    return lo

defs = [d for d in json.load(open(os.path.join(ROOT, "src/data/labels.json"), encoding="utf-8")) if d["type"] in ("sea", "ocean")]
out = {}
for d in defs:
    ls = lines(d["text"]); wid = max(len(l) for l in ls); span = d.get("span") or 45
    asp = (wid * ADV) / (len(ls) * LINE)
    # What the name is worth having: its full size at the zoom it first appears. More room than that buys nothing.
    enough = cap(span) * wid * ADV / (2 ** d["minZoom"] / 32)
    hi = min(4 * span + 60, 1500)
    worth = lambda w, r: min(w, enough) - MOVE * r
    bw, bx, by = widest(d["x"], d["y"], asp, hi), d["x"], d["y"]; bs = worth(bw, 0)
    R = min(max(span * 0.3, 8), 60); step = max(0.5, R / 30); n = int(R / step)
    if bw < enough:
        for iy in range(-n, n + 1):
            for ix in range(-n, n + 1):
                r = math.hypot(ix, iy) * step
                if r > R or r == 0: continue
                w = widest(d["x"] + ix * step, d["y"] + iy * step, asp, hi); s = worth(w, r)
                if s > bs + 1e-9: bs, bw, bx, by = s, w, d["x"] + ix * step, d["y"] + iy * step
    out[d["text"]] = [round(bx, 1), round(by, 1), round(bw, 1)]

if len(sys.argv) > 1 and sys.argv[1] == "check":
    print("land under the name, %, by user zoom 1..12 (. below its band, - no room yet); then the move in px")
    for d in defs:
        ls = lines(d["text"]); wid = max(len(l) for l in ls); x, y, w = out[d["text"]]; row = ""
        for uz in range(1, 13):
            z = 2 + uz / 2; sc = 2 ** z / 32
            fit = w * sc / (wid * ADV)
            if z < d["minZoom"]: row += "  . "; continue
            if fit < MIN_FS: row += "  - "; continue
            fs = min(fit, cap(d.get("span") or 45))
            row += "%3d " % round(100 * landfrac(x, y, wid * fs * ADV / sc, len(ls) * fs * LINE / sc))
        print("%-28s %s  %5.1f" % (d["text"], row, math.hypot(x - d["x"], y - d["y"])))
else:
    p = os.path.join(ROOT, "src/data/water.json")
    with open(p + ".tmp", "w", encoding="utf-8") as f: json.dump(out, f, ensure_ascii=False, indent=0)
    os.replace(p + ".tmp", p)
    print("water.json:", len(out), "names")
