"""Merge adjacent blobs whose fill colours are nearly identical (JPEG noise splits). blob2 -> blob3"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
T = float(sys.argv[1])
lab = np.load(os.path.join(WORK, "blob2.npy"))
s = np.load(os.path.join(WORK, "pang3000.npy")).astype(np.float32)
med = np.stack([ndi.median_filter(s[..., i], size=9) for i in range(3)], -1)
n = lab.max(); idx = np.arange(1, n + 1)
# colour = median over blob interior
inner = ndi.binary_erosion(lab > 0, iterations=1)
col = np.zeros((n + 1, 3), np.float32)
for c in range(3):
    col[1:, c] = ndi.median(med[..., c], lab, idx)
areas = np.bincount(lab.ravel(), minlength=n + 1)
pairs = set()
for a, b in ((lab[1:], lab[:-1]), (lab[:, 1:], lab[:, :-1])):
    m = (a != b) & (a > 0) & (b > 0)
    k = np.unique(np.minimum(a[m], b[m]).astype(np.int64) * (n + 1) + np.maximum(a[m], b[m]))
    pairs.update(k.tolist())
parent = list(range(n + 1))
def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x
cnt = 0
for k in sorted(pairs):
    a, b = k // (n + 1), k % (n + 1)
    d = float(np.abs(col[a] - col[b]).max())
    if d < T:
        ra, rb = find(a), find(b)
        if ra != rb: parent[rb] = ra; cnt += 1
remap = np.array([find(i) for i in range(n + 1)], np.int32)
lab = remap[lab]
areas = np.bincount(lab.ravel()); ids = np.nonzero(areas)[0]; ids = ids[ids > 0]
order = ids[np.argsort(-areas[ids])]
remap = np.zeros(areas.size, np.int32); remap[order] = np.arange(1, len(order) + 1)
lab = remap[lab]; areas = np.bincount(lab.ravel()); n = lab.max()
print("merged", cnt, "-> blobs", n, "| >=150:", int((areas[1:] >= 150).sum()), "| >=60:", int((areas[1:] >= 60).sum()))
np.save(os.path.join(WORK, "blob3.npy"), lab)
objs = ndi.find_objects(lab); rows = []
for i, sl in enumerate(objs, 1):
    m = lab[sl] == i
    d = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
    y, x = np.unravel_index(d.argmax(), d.shape)
    rows.append((i, areas[i], x + sl[1].start, y + sl[0].start, 0))
np.savetxt(os.path.join(WORK, "blobs.tsv"), np.array(rows), fmt="%d", delimiter="\t", header="id\tarea\tx\ty\tcls", comments="")
