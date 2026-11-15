"""Whole-map check: push every overlay land pixel through its region's warp, look up the real unit there.
agree.png: green = real unit equals overlay unit, red = different unit, blue = real water, grey = unfitted."""
import sys, json, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
region = np.load(os.path.join(WORK, "region.npy")); reg2u = np.load(os.path.join(WORK, "reg2u.npy"))
real = np.load(os.path.join(WORK, "real_unit.npy"))
warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
img = np.zeros(region.shape + (3,), np.uint8); img[:] = (25, 35, 55); img[region != 0] = (120, 120, 120)
tot = ok = wat = 0; per = []
from scipy import ndimage as ndi
objs = ndi.find_objects(np.clip(region, 0, None))
for b, W in warps.items():
    sl = objs[b - 1]; m = region[sl] == b
    yy, xx = np.nonzero(m); X = 2 * (xx + sl[1].start) + 1; Y = 2 * (yy + sl[0].start) + 1
    lon, lat = W(X, Y)
    j = np.clip(((lon + 180) * 60).astype(int), 0, 21599); i = np.clip(((90 - lat) * 60).astype(int), 0, 10799)
    ru = real[i, j]; u = reg2u[b]
    good = ru == u; water = ru == 0
    c = np.zeros((len(ru), 3), np.uint8); c[:] = (215, 60, 60); c[water] = (70, 120, 220); c[good] = (70, 170, 90)
    sub = img[sl]; sub[yy, xx] = c
    tot += len(ru); ok += good.sum(); wat += water.sum()
    per.append((1 - good.mean(), b, len(ru), float(water.mean())))
e = np.zeros(region.shape, bool); e[1:] |= region[1:] != region[:-1]; e[:, 1:] |= region[:, 1:] != region[:, :-1]
img[e] = (img[e] * 0.45).astype(np.uint8)
write_png(os.path.join(WORK, "agree.png"), img[::2, ::2])
write_png(os.path.join(WORK, "agree_full.png"), img)
meta = json.load(open(os.path.join(WORK, "ne_meta.json"))); codes = meta["codes"]
print(f"fitted land px {tot}: same unit {100*ok/tot:.1f}%, real water {100*wat/tot:.1f}%, other unit {100*(tot-ok-wat)/tot:.1f}%")
per.sort(reverse=True)
print("worst regions (mismatch share, region, unit, px, water share):")
print("  " + "; ".join(f"{p[0]:.2f} #{p[1]} {codes[reg2u[p[1]]-1]} {p[2]}px w{p[3]:.2f}" for p in per[:24]))
