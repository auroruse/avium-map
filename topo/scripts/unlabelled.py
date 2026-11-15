import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
lab = {}
for line in open(os.path.join(TOPO, "scripts", "labels.txt")):
    if line.startswith("#") or not line.strip(): continue
    p = line.split()
    for i in p[1:]:
        assert int(i) not in lab, i
        lab[int(i)] = p[0]
t = np.loadtxt(os.path.join(WORK, "blobs.tsv"), skiprows=1, dtype=int)
tot = t[:, 1].sum(); done = sum(a for i, a, *_ in t if i in lab)
print(f"labelled {len(lab)} blobs, {100*done/tot:.1f}% of overlay land area")
print("unlabelled >= 250px (id area x y):")
print("; ".join(f"{i} {a} {x},{y}" for i, a, x, y, _ in t if i not in lab and a >= 250))
