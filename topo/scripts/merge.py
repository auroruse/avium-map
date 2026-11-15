"""Merge enclosed artifact blobs into the blob that surrounds them; write blob2.npy + blobs.tsv."""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
lab = np.load(os.path.join(WORK, "blob.npy")).copy()
for rnd in range(6):
    n = lab.max()
    areas = np.bincount(lab.ravel(), minlength=n + 1)
    # adjacency counts between labels (4-neigh), sea = 0
    pairs = []
    for a, b in ((lab[1:], lab[:-1]), (lab[:, 1:], lab[:, :-1])):
        m = a != b
        pairs.append(np.stack([a[m], b[m]], 1)); pairs.append(np.stack([b[m], a[m]], 1))
    p = np.concatenate(pairs)
    key = p[:, 0].astype(np.int64) * (n + 1) + p[:, 1]
    u, c = np.unique(key, return_counts=True)
    A = u // (n + 1); B = u % (n + 1)
    tot = np.bincount(A, weights=c, minlength=n + 1)
    remap = np.arange(n + 1)
    merged = 0
    order = np.lexsort((-c, A))
    seen = set()
    for i in order:
        a, b = int(A[i]), int(B[i])
        if a == 0 or a in seen: continue
        seen.add(a)  # first hit for a = its dominant neighbour
        if b == 0: continue
        if areas[a] < 600 and c[i] >= 0.8 * tot[a] and areas[b] > 2 * areas[a]:
            remap[a] = b; merged += 1
    # resolve chains
    for _ in range(5): remap = remap[remap]
    lab = remap[lab]
    print("round", rnd, "merged", merged)
    if merged == 0: break
# compact ids by area
areas = np.bincount(lab.ravel()); ids = np.nonzero(areas)[0]; ids = ids[ids > 0]
order = ids[np.argsort(-areas[ids])]
remap = np.zeros(areas.size, np.int32); remap[order] = np.arange(1, len(order) + 1)
lab = remap[lab]; areas = np.bincount(lab.ravel())
n = lab.max()
print("blobs", n, "| >=400:", int((areas[1:] >= 400).sum()), "| >=150:", int((areas[1:] >= 150).sum()), "| >=60:", int((areas[1:] >= 60).sum()))
np.save(os.path.join(WORK, "blob2.npy"), lab)
objs = ndi.find_objects(lab); rows = []
for i, sl in enumerate(objs, 1):
    m = lab[sl] == i
    d = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
    y, x = np.unravel_index(d.argmax(), d.shape)
    rows.append((i, areas[i], x + sl[1].start, y + sl[0].start, 0))
np.savetxt(os.path.join(WORK, "blobs.tsv"), np.array(rows), fmt="%d", delimiter="\t", header="id\tarea\tx\ty\tcls", comments="")
