"""The traced rivers that sit worst on the ground: name, where, and the raw ground along them.  netprof.py [how many]"""
import sys, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
net = pickle.load(open(os.path.join(WORK, "river_net.pkl"), "rb"))["paths"]; H = np.load(os.path.join(WORK, "height_raw.npy"), mmap_mode="r")
land = np.load(os.path.join(WORK, "land12k.npy"), mmap_mode="r"); lev = np.load(os.path.join(WORK, "waterlevel.npy"), mmap_mode="r"); rows = []
for i, p in enumerate(net):
    c = p["cells"]; o = np.argsort(c[:, 0] * 12000 + c[:, 1]); h = np.empty(len(c), np.float32); h[o] = np.where(land[c[o, 0], c[o, 1]], H[c[o, 0], c[o, 1]], lev[c[o, 0], c[o, 1]])
    bar = np.maximum.accumulate(h[::-1])[::-1] - h; rows.append((float(bar.max()), i, h))
rows.sort(key=lambda r: -r[0]); n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
print("rivers with a barrier over 100 m: %d, over 300 m: %d, over 600 m: %d (of %d)" % (sum(r[0] > 100 for r in rows), sum(r[0] > 300 for r in rows), sum(r[0] > 600 for r in rows), len(rows)))
for b, i, h in rows[:n]:
    p = net[i]; c = p["cells"]; st = max(len(h) // 24, 1)
    print("%-14s rank %d, %4d cells | (%d,%d)->(%d,%d) on the 6000 grid | barrier %4d m | %s" % (p["name"][:14], p["rank"], len(c), c[0, 1] // 2, c[0, 0] // 2, c[-1, 1] // 2, c[-1, 0] // 2, b, " ".join("%d" % v for v in h[::st])))
