"""spot.py Name [Name...] — what is under a city: elevation source, repairs, routed river extensions, river pieces"""
import sys, csv, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
rows = {c["NAME"]: c for c in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if c["X"]}
H = np.load(os.path.join(WORK, "height.npy"), mmap_mode="r"); Hr = np.load(os.path.join(WORK, "height_raw.npy"), mmap_mode="r")
has0 = np.load(os.path.join(WORK, "ehas_adj.npy"), mmap_mode="r"); E0 = np.load(os.path.join(WORK, "ereal_adj.npy"), mmap_mode="r")
paths = pickle.load(open(os.path.join(WORK, "river_paths.pkl"), "rb")); fin = pickle.load(open(os.path.join(WORK, "rivers_final.pkl"), "rb"))
for n in sys.argv[1:]:
    c = rows[n]; x, y = float(c["X"]), float(c["Y"]); R = 150
    sl = (slice(int(2 * y - 2 * R), int(2 * y + 2 * R)), slice(int(2 * x - 2 * R), int(2 * x + 2 * R)))
    h = np.asarray(H[sl]).astype(float); hr = np.asarray(Hr[sl]).astype(float); land = h > 0
    e0 = np.asarray(E0[sl]); hs = np.asarray(has0[sl])
    near = [(i, p) for i, p in paths if (np.hypot(p[:, 0] - x, p[:, 1] - y) < R).any()]
    plen = [float(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])).sum()) for i, p in near]
    pe = [(float(Hr[int(2 * p[0, 1]), int(2 * p[0, 0])]), float(Hr[int(2 * p[-1, 1]), int(2 * p[-1, 0])])) for i, p in near]
    print(f"{n} ({c['NATION']}) at {x:.0f},{y:.0f}: land {100*land.mean():.0f}% | no real elevation {100*(land & ~hs).sum()/max(land.sum(),1):.0f}% of land | landed on real sea (mirrored) {100*(land & hs & (e0 < 2)).sum()/max(land.sum(),1):.0f}% | elevation median {np.median(h[land]):.0f} m")
    print(f"   routed extensions within {R}px: {len(near)}, lengths px {[round(l) for l in plen]}, start/end elevation m {[(round(a), round(b)) for a, b in pe]} | deepest cut {float((hr - h).max()):.0f} m | river pieces nearby {sum(1 for r in fin if (np.hypot(r[2][:, 0] - x, r[2][:, 1] - y) < R).any())}")
