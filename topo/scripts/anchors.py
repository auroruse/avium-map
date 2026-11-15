"""work/landmarks.npy = the overlay's city dots as named in cities.txt + the few hand points in landmarks.txt.
rows: region, x6000, y6000, lon, lat, trust"""
import sys, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
region = np.load(os.path.join(WORK, "region.npy")); reg2u = np.load(os.path.join(WORK, "reg2u.npy"))
dots = np.load(os.path.join(WORK, "dots.npy")); img = np.load(os.path.join(WORK, "pang3000.npy")).max(-1)
meta = json.load(open(os.path.join(WORK, "ne_meta.json"))); codes = meta["codes"]; idx = {c: i + 1 for i, c in enumerate(codes)}
ALIAS = {"SAH": "MAR", "AFG": "IRN", "EST": "FIN", "SVK": "HUN"}
area = np.bincount(region[region > 0]); okreg = np.zeros(len(area), bool); okreg[1:] = area[1:] >= 150
def snap(x, y, r=5):
    """centre of the dark ink within r px of where the dot was read off the crop"""
    xi, yi = int(round(x)), int(round(y))
    yy, xx = np.mgrid[yi - r:yi + r + 1, xi - r:xi + r + 1]
    m = (img[yi - r:yi + r + 1, xi - r:xi + r + 1] < 90) & (np.hypot(xx - x, yy - y) <= r)
    if m.sum() < 3: return x, y, False
    return float(xx[m].mean()), float(yy[m].mean()), True
def region_for(x, y, unit=None, reach=14):
    xi, yi = int(round(x)), int(round(y))
    w = region[max(yi - reach, 0):yi + reach + 1, max(xi - reach, 0):xi + reach + 1]
    yy, xx = np.nonzero((w > 0) & okreg[np.clip(w, 0, None)] & ((reg2u[np.clip(w, 0, None)] == unit) if unit else True))
    if not len(yy): return 0
    k = np.hypot(xx - min(xi, reach), yy - min(yi, reach)).argmin()
    return int(w[yy[k], xx[k]])
rows = []; miss = []; unsnapped = []
for line in open(os.path.join(TOPO, "scripts", "cities.txt")):
    t = line.split("#")[0].split() if not line.lstrip().startswith("#") else []
    raw = line.split()
    if not raw or raw[0].startswith("#"): continue
    lon, lat = float(raw[0]), float(raw[1]); code = raw[-1]; name = raw[-2]
    if raw[2].startswith("#"): x, y = dots[int(raw[2][1:]), :2]
    else:
        x, y, ok = snap(float(raw[2]), float(raw[3]))
        if not ok: unsnapped.append(name)
    u = idx.get(ALIAS.get(code, code))
    b = region_for(x, y, u) if u else 0
    if b: rows.append((b, 2 * x + 1, 2 * y + 1, lon, lat, 1))
    else: miss.append(f"{name}({code})")
nc = len(rows)
for line in open(os.path.join(TOPO, "scripts", "landmarks.txt")):
    t = line.split("#")[0].split()
    if not t: continue
    lon, lat, x, y = map(float, t[:4]); b = region_for(x, y, None, 8)
    if b: rows.append((b, 2 * x + 1, 2 * y + 1, lon, lat, 1))
np.save(os.path.join(WORK, "landmarks.npy"), np.array(rows))
print(f"city anchors {nc}, other hand points {len(rows) - nc} | regions anchored: {len({r[0] for r in rows})}")
if miss: print("no region of that country at the dot:", ", ".join(miss))
if unsnapped: print("no ink found to snap to (position used as read):", ", ".join(unsnapped))
