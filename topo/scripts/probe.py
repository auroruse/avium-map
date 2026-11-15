import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
lab = np.load(os.path.join(WORK, "blob3.npy"))
names = {}
for line in open(os.path.join(TOPO, "scripts", "labels.txt")):
    if line.startswith("#") or not line.strip(): continue
    p = line.split()
    for i in p[1:]: names[int(i)] = p[0]
for a in sys.argv[1:]:
    tag, x, y = a.split(":"); x, y = int(x), int(y)
    b = int(lab[y, x]); print(tag, (x, y), "blob", b, names.get(b, "-"), "area", int((lab == b).sum()))
if len(sys.argv) == 1:
    img = np.zeros(lab.shape + (3,), np.uint8); img[:] = (30, 45, 70)
    known = np.zeros(lab.max() + 1, bool); known[list(names)] = True
    rng = np.random.default_rng(5); codes = sorted(set(names.values()))
    col = {c: rng.integers(90, 235, 3) for c in codes}
    lut = np.zeros((lab.max() + 1, 3), np.uint8); lut[:] = (255, 0, 255); lut[0] = (30, 45, 70)
    for i, c in names.items(): lut[i] = col[c]
    img = lut[lab]
    e = np.zeros(lab.shape, bool); e[1:] |= lab[1:] != lab[:-1]; e[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    img[e & (lab > 0)] //= 2
    write_png(os.path.join(WORK, "labelled.png"), img[::2, ::2])
