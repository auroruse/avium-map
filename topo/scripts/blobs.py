"""Clean the class map (drop rivers/text), build blobs, write blob table."""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
cls = np.load(os.path.join(WORK, "cls.npy")); cent = np.load(os.path.join(WORK, "cent.npy"))
land = cls > 0
K = cent.shape[0]
dark = int(np.argmin(cent.sum(1))) + 1
core = np.zeros(cls.shape, bool)
st = ndi.generate_binary_structure(2, 2)
for k in range(1, K + 1):
    if k == dark: continue
    core |= ndi.binary_erosion(cls == k, st, iterations=3)
_, (iy, ix) = ndi.distance_transform_edt(~core, return_indices=True)
cls2 = np.where(land, cls[iy, ix], 0).astype(np.int16)
lab = np.zeros(cls.shape, np.int32); n = 0
for k in range(1, K + 1):
    l, m = ndi.label(cls2 == k)
    l[l > 0] += n; lab += l; n += m
areas = np.bincount(lab.ravel(), minlength=n + 1)
# relabel by descending area
order = np.argsort(-areas[1:]) + 1
remap = np.zeros(n + 1, np.int32); remap[order] = np.arange(1, n + 1)
lab = remap[lab]; areas = np.bincount(lab.ravel(), minlength=n + 1)
print("blobs", n, "| >=400:", int((areas[1:] >= 400).sum()), "| >=100:", int((areas[1:] >= 100).sum()), "| >=30:", int((areas[1:] >= 30).sum()))
np.save(os.path.join(WORK, "blob.npy"), lab); np.save(os.path.join(WORK, "cls2.npy"), cls2)
# label anchor = deepest interior point
objs = ndi.find_objects(lab)
rows = []
for i, sl in enumerate(objs, 1):
    if areas[i] < 30: break
    m = lab[sl] == i
    d = ndi.distance_transform_edt(np.pad(m, 1))[1:-1, 1:-1]
    y, x = np.unravel_index(d.argmax(), d.shape)
    rows.append((i, areas[i], x + sl[1].start, y + sl[0].start, int(cls2[y + sl[0].start, x + sl[1].start])))
np.savetxt(os.path.join(WORK, "blobs.tsv"), np.array(rows), fmt="%d", delimiter="\t", header="id\tarea\tx\ty\tcls", comments="")
print(len(rows), "blobs tabulated")
