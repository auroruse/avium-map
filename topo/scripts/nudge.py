"""Calibrate the rivers on the cities that stand on them.
Avium's cities were placed on the hand-drawn rivers, so a city on one is an exact point its river must pass through.
The shift needed at each such city is spread into a smooth field and applied to rivers and elevation alike,
so a valley moves with its river.  -> work/river_lines_adj.pkl, ereal_adj.npy, ehas_adj.npy, nudge_report.json"""
import sys, pickle, csv, json, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
t0 = time.time()
SIGMA, REACH, ON, CAP = 45.0, 25.0, 4.0, 30.0        # all in px on the 6000 grid
src = "rivers-drawn.PNG" if os.path.exists(os.path.join(LAYERS, "rivers-drawn.PNG")) else "rivers.PNG"
old = read_png(os.path.join(LAYERS, src))[..., 3] > 0
do = ndi.distance_transform_edt(~old)
rows = [r for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if r["KIND"] == "city" and r["X"]]
cxy = np.array([[float(r["X"]), float(r["Y"])] for r in rows])
d = do[np.clip(cxy[:, 1].round().astype(int), 0, 5999), np.clip(cxy[:, 0].round().astype(int), 0, 5999)]
on = (d <= ON) & np.array([r["NATION"] != "Eivorie" for r in rows])
lines = pickle.load(open(os.path.join(WORK, "river_lines.pkl"), "rb"))
def dense(p):
    k = int(max(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])).sum() * 2, 2)); t = np.linspace(0, len(p) - 1, k)
    return np.stack([np.interp(t, np.arange(len(p)), p[:, 0]), np.interp(t, np.arange(len(p)), p[:, 1])], 1)
def nearest(lines_, pts):
    P = np.concatenate([dense(l[2]) for l in lines_]); dd, ii = cKDTree(P).query(pts); return dd, P[ii]
C = cxy[on]; names = [f'{r["NAME"]} ({r["NATION"]})' for r, o in zip(rows, on) if o]
dd, near = nearest(lines, C)
use = dd <= REACH
src_pts = near[use]; vec = C[use] - near[use]
print("river cities", int(on.sum()), "| matched to a new river within", REACH, "px:", int(use.sum()), "| before: median %.1f px" % np.median(dd[use]))
# Gaussian RBF fields through the shifts, fading to nothing away from any river city: a broad pass, then a tight one
def phi(a, b, sg): return np.exp(-((a[:, None, 0] - b[None, :, 0]) ** 2 + (a[:, None, 1] - b[None, :, 1]) ** 2) / (2 * sg ** 2))
passes = []; adj = lines
def field(q):
    q = np.array(q, float)
    for sp, Wt, sg in passes:
        out = np.empty((len(q), 2))
        for i in range(0, len(q), 20000): out[i:i + 20000] = phi(q[i:i + 20000], sp, sg) @ Wt
        n = np.hypot(out[:, 0], out[:, 1]); q = q + out * np.minimum(1, CAP / np.maximum(n, 1e-9))[:, None]
    return q
for sg, reg in ((SIGMA, 0.05), (18.0, 0.02), (8.0, 0.01)):
    ddk, neark = nearest(adj, C[use])
    passes.append((neark, np.linalg.solve(phi(neark, neark, sg) + reg * np.eye(len(neark)), C[use] - neark), sg))
    adj = [(rank, name, field(p)) for rank, name, p in lines]
pickle.dump(adj, open(os.path.join(WORK, "river_lines_adj.pkl"), "wb"))
np.save(os.path.join(WORK, "river_cities.npy"), C[use])
dd2, _ = nearest(adj, C)
print("after: median %.2f px | within 1.5px: %d of %d | within 3px: %d" % (np.median(dd2[use]), (dd2[use] <= 1.5).sum(), use.sum(), (dd2[use] <= 3).sum()))
# the same field, backwards, on the elevation grid
g = np.arange(4, 6000, 8.0); GX, GY = np.meshgrid(g, g)
G0 = np.stack([GX.ravel(), GY.ravel()], 1); F = (field(G0) - G0).reshape(750, 750, 2).astype(np.float32)
np.save(os.path.join(WORK, "nudge_field.npy"), F)                  # colour.py carries the imagery through the same shift
print("field: max shift %.1f px, area moved by more than 1px: %.1f%% of the map" % (np.hypot(F[..., 0], F[..., 1]).max(), 100 * (np.hypot(F[..., 0], F[..., 1]) > 1).mean()))
E = np.load(os.path.join(WORK, "ereal.npy")); has = np.load(os.path.join(WORK, "ehas.npy"))
Eo = np.empty_like(E); Ho = np.empty_like(has)
for r0 in range(0, 12000, 1500):
    yy, xx = np.meshgrid(np.arange(r0, r0 + 1500, dtype=np.float32), np.arange(12000, dtype=np.float32), indexing="ij")
    gy = ((yy + 0.5) / 2 - 4) / 8; gx = ((xx + 0.5) / 2 - 4) / 8
    fx = ndi.map_coordinates(F[..., 0], [gy, gx], order=1, mode="nearest"); fy = ndi.map_coordinates(F[..., 1], [gy, gx], order=1, mode="nearest")
    sy = yy - 2 * fy; sx = xx - 2 * fx
    Eo[r0:r0 + 1500] = ndi.map_coordinates(E, [sy, sx], order=1, mode="nearest")
    Ho[r0:r0 + 1500] = ndi.map_coordinates(has.view(np.uint8), [sy, sx], order=0, mode="nearest") > 0
np.save(os.path.join(WORK, "ereal_adj.npy"), Eo); np.save(os.path.join(WORK, "ehas_adj.npy"), Ho)
miss = [n for n, u in zip(names, use) if not u]
json.dump({"river_cities": int(on.sum()), "calibrated": int(use.sum()), "median_before_px": float(np.median(dd[use])), "median_after_px": float(np.median(dd2[use])),
           "no_real_river_within_reach": miss}, open(os.path.join(WORK, "nudge_report.json"), "w"), ensure_ascii=False, indent=1)
print("cities with no real river within reach:", len(miss), "|", round(time.time() - t0), "s")
