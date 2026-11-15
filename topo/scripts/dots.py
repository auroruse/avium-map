"""Detect the overlay's city dots, push them through the current warps, compare with real cities.
An independent accuracy check, and a source of interior anchor points."""
import sys, json, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import shapefile
s = np.load(os.path.join(WORK, "pang3000.npy")).astype(np.int16)
dark = s.max(-1) < 95
lab, n = ndi.label(dark)
objs = ndi.find_objects(lab); area = np.bincount(lab.ravel())
dots = []
for i, sl in enumerate(objs, 1):
    h = sl[0].stop - sl[0].start; w = sl[1].stop - sl[1].start
    if not (2 <= h <= 11 and 2 <= w <= 11 and abs(h - w) <= 2): continue
    if area[i] < 0.62 * h * w or area[i] < 5: continue
    yy, xx = np.nonzero(lab[sl] == i)
    dots.append((xx.mean() + sl[1].start, yy.mean() + sl[0].start, area[i]))
dots = np.array(dots)
np.save(os.path.join(WORK, "dots.npy"), dots)
print("dots", len(dots), "| big (capitals):", int((dots[:, 2] >= 25).sum()))
if "--detect" in sys.argv: sys.exit()
region = np.load(os.path.join(WORK, "region.npy")); warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
r = shapefile.Reader(os.path.join(DATA, "ne_places", "ne_10m_populated_places"), encoding="utf-8")
f = [x[0] for x in r.fields[1:]]
ix = {k: f.index(k) for k in ("NAME", "ADM0_A3", "POP_MAX", "FEATURECLA", "SCALERANK", "LATITUDE", "LONGITUDE")}
P = [(rec[ix["NAME"]], rec[ix["ADM0_A3"]], rec[ix["POP_MAX"]], rec[ix["FEATURECLA"]], rec[ix["SCALERANK"]], rec[ix["LONGITUDE"]], rec[ix["LATITUDE"]]) for rec in r.records()]
major = [p for p in P if p[2] >= 250000 or "capital" in p[3].lower() or p[4] <= 3]
ll = np.array([[p[5], p[6]] for p in major])
def xyz(lon, lat):
    lo = np.radians(lon); la = np.radians(lat)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
tree = cKDTree(xyz(ll[:, 0], ll[:, 1]))
# nearest fitted region for each dot
fitted = np.isin(region, list(warps.keys()))
_, (iy, ix2) = ndi.distance_transform_edt(~fitted, return_indices=True)
out = []
for x, y, a in dots:
    yi, xi = int(round(y)), int(round(x))
    b = int(region[iy[yi, xi], ix2[yi, xi]])
    if np.hypot(iy[yi, xi] - yi, ix2[yi, xi] - xi) > 6: continue
    lon, lat = warps[b](np.array([2 * x + 1]), np.array([2 * y + 1]))
    d, k = tree.query(xyz(lon[0], lat[0]), k=2)
    km = 2 * np.arcsin(np.clip(d / 2, 0, 1)) * 6371
    out.append((x, y, a, b, lon[0], lat[0], km[0], km[1], k[0]))
out = np.array(out)
np.save(os.path.join(WORK, "dots_mapped.npy"), out)
km = out[:, 6]
print("dots on fitted land:", len(out), "| distance to nearest major real city, km: median", round(float(np.median(km))), "| <30:", int((km < 30).sum()), "| <60:", int((km < 60).sum()), "| <120:", int((km < 120).sum()), "| >300:", int((km > 300).sum()))
big = out[out[:, 2] >= 25]
print("capital-size dots:", len(big), "| median km", round(float(np.median(big[:, 6]))), "| <60:", int((big[:, 6] < 60).sum()))
json.dump([[major[int(o[8])][0], major[int(o[8])][1]] for o in out], open(os.path.join(WORK, "dots_names.json"), "w"))
