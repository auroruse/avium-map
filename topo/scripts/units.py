"""Unit map -> regions (one warp each) + typed boundary samples for overlay regions and the real world."""
import sys, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
ALIAS = {"SAH": "MAR", "AFG": "IRN", "EST": "FIN", "SVK": "HUN"}     # drawn as one colour on the overlay
meta = json.load(open(os.path.join(WORK, "ne_meta.json")))
codes = meta["codes"]; idx = {c: i + 1 for i, c in enumerate(codes)}
blob = np.load(os.path.join(WORK, "blob3.npy"))
b2u = np.full(blob.max() + 1, -1, np.int16); b2u[0] = 0
for line in open(os.path.join(TOPO, "scripts", "labels.txt")):
    if line.startswith("#") or not line.strip(): continue
    p = line.split()
    for i in p[1:]: b2u[int(i)] = idx[p[0]]

# absorb unlabelled artefact blobs (text, rivers) that sit inside one unit
areas = np.bincount(blob.ravel())
for rnd in range(3):
    n = blob.max(); cnt = {}
    for a, b in ((blob[:, :-1], blob[:, 1:]), (blob[:-1], blob[1:])):
        m = a != b
        for x, y in ((a[m], b[m]), (b[m], a[m])):
            k, c = np.unique(x.astype(np.int64) * (n + 1) + y, return_counts=True)
            for kk, cc in zip(k, c): cnt[int(kk)] = cnt.get(int(kk), 0) + int(cc)
    per = {}
    for kk, cc in cnt.items():
        a, b = kk // (n + 1), kk % (n + 1)
        if b2u[a] != -1: continue
        u = int(b2u[b])
        if u == -1: continue
        per.setdefault(a, {}); per[a][u] = per[a].get(u, 0) + cc
    ch = 0
    for a, d in per.items():
        land = {u: c for u, c in d.items() if u > 0}
        if not land: continue
        u, c = max(land.items(), key=lambda kv: kv[1])
        tot = sum(d.values()); lt = sum(land.values())
        # mostly one unit among its land neighbours, and genuinely attached to land (not lettering out at sea)
        if c >= 0.6 * lt and lt >= 0.3 * tot and areas[a] < 1500: b2u[a] = u; ch += 1
    print("absorbed", ch)
    if not ch: break
unit = b2u[blob]

# regions: same-unit pieces closer than ~12 px share one warp
region = np.where(unit == -1, -1, 0).astype(np.int32); reg2u = [0]; nreg = 0
st = ndi.generate_binary_structure(2, 2)
objs = ndi.find_objects(np.clip(unit, 0, None))
for u, sl in enumerate(objs, 1):
    if sl is None: continue
    sl = (slice(max(sl[0].start - 8, 0), sl[0].stop + 8), slice(max(sl[1].start - 8, 0), sl[1].stop + 8))
    m = unit[sl] == u
    l, k = ndi.label(ndi.binary_dilation(m, st, iterations=6), st)
    ids = np.unique(l[m])
    sub = region[sl]
    for i in ids:
        nreg += 1; sub[m & (l == i)] = nreg; reg2u.append(u)
reg2u = np.array(reg2u, np.int16)
np.save(os.path.join(WORK, "unit.npy"), unit); np.save(os.path.join(WORK, "region.npy"), region); np.save(os.path.join(WORK, "reg2u.npy"), reg2u)
ra = np.bincount(region[region > 0])
print("regions", nreg, "| area>=150:", int((ra >= 150).sum()), "| unknown land px:", int((region == -1).sum()), "of", int((region != 0).sum()))

# ---- overlay samples: (region, x6000, y6000, type, nx, ny) ; type = neighbour unit, 0 water ; n = outward normal (px, y down)
from scipy.spatial import cKDTree
rows = []
def add(ba, bb, x, y, dx, dy):
    for a, b, sg in ((ba, bb, 1.0), (bb, ba, -1.0)):
        ok = (a > 0) & (b >= 0)
        ua = reg2u[np.clip(a, 0, None)]; ub = reg2u[np.clip(b, 0, None)]
        m = ok & (ua != ub)
        k = int(m.sum())
        rows.append(np.stack([a[m], x[m], y[m], ub[m], np.full(k, sg * dx), np.full(k, sg * dy)], 1))
ii, jj = np.nonzero(region[:, :-1] != region[:, 1:])
add(region[ii, jj], region[ii, jj + 1], 2 * jj + 2, 2 * ii + 1, 1.0, 0.0)
ii, jj = np.nonzero(region[:-1, :] != region[1:, :])
add(region[ii, jj], region[ii + 1, jj], 2 * jj + 1, 2 * ii + 2, 0.0, 1.0)
ov = np.concatenate(rows).astype(np.float32)
ov = ov[np.argsort(ov[:, 0], kind="stable")]
# smooth the staircase normals along each region's boundary
st_ = np.searchsorted(ov[:, 0], np.arange(ov[:, 0].max() + 2))
for r in range(1, len(st_) - 1):
    seg = ov[st_[r]:st_[r + 1]]
    if len(seg) < 2: continue
    tr = cKDTree(seg[:, 1:3]); nb = tr.query_ball_point(seg[:, 1:3], 9.0)
    n = np.array([seg[i, 4:6].mean(0) for i in nb]); l = np.hypot(n[:, 0], n[:, 1])
    good = l > 0.2; seg[good, 4:6] = n[good] / l[good, None]
np.save(os.path.join(WORK, "ov_samples.npy"), ov)
print("overlay samples", len(ov))

if "--skip-real" not in sys.argv:
    real = np.load(os.path.join(WORK, "real_lab.npy"))
    al = np.arange(len(codes) + 1, dtype=np.int16)
    for a, b in ALIAS.items(): al[idx[a]] = idx[b]
    real = al[real]
    np.save(os.path.join(WORK, "real_unit.npy"), real)
    rows = []
    left = real; right = np.roll(real, -1, axis=1)
    ii, jj = np.nonzero(left != right)
    a = left[ii, jj]; b = right[ii, jj]
    lon = -180 + (jj + 1) / 60.0; lat = 90 - (ii + 0.5) / 60.0
    lon[lon >= 180] -= 360
    for u, t, q in ((a, b, 0), (b, a, 1)):                    # outward normal: 0 east, 1 west, 2 north, 3 south
        m = u > 0; rows.append(np.stack([u[m], t[m], lon[m], lat[m], np.full(int(m.sum()), q)], 1))
    ii, jj = np.nonzero(real[:-1] != real[1:])
    a = real[ii, jj]; b = real[ii + 1, jj]
    lon = -180 + (jj + 0.5) / 60.0; lat = 90 - (ii + 1) / 60.0
    for u, t, q in ((a, b, 3), (b, a, 2)):
        m = u > 0; rows.append(np.stack([u[m], t[m], lon[m], lat[m], np.full(int(m.sum()), q)], 1))
    rs = np.concatenate(rows).astype(np.float32)
    rs = rs[np.argsort(rs[:, 0], kind="stable")]
    np.save(os.path.join(WORK, "real_samples.npy"), rs)
    print("real samples", len(rs))
