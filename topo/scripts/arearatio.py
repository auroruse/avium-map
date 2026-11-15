import sys, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
meta = json.load(open(os.path.join(WORK, "ne_meta.json")))
lab = {}
for line in open(os.path.join(TOPO, "scripts", "labels.txt")):
    if line.startswith("#") or not line.strip(): continue
    p = line.split()
    for i in p[1:]: lab[int(i)] = p[0]
t = np.loadtxt(os.path.join(WORK, "blobs.tsv"), skiprows=1, dtype=int)
px = {}
for i, a, *_ in t:
    if i in lab: px[lab[i]] = px.get(lab[i], 0) + a
bad = [c for c in px if c not in meta["area_km2"]]
print("unknown codes:", bad)
rat = sorted(((px[c] * 22.2 / max(meta["area_km2"][c], 1), c) for c in px if c not in bad), reverse=True)
print("overlay/real area ratio, highest:", " ".join(f"{c}:{r:.2f}" for r, c in rat[:45]))
print("lowest:", " ".join(f"{c}:{r:.2f}" for r, c in rat[-30:]))
