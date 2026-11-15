"""Checks on the traced rivers, one per kind of defect: cities off their river, doubled lines, specks, ruler-straight runs,
cusps, ends in mid-air, short stubs, loops.  -> prints; work/rivqa.pkl holds the flagged spots (6000 grid) for look sheets"""
import sys, pickle, csv; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
M = 12000; N = pickle.load(open(os.path.join(WORK, "river_net.pkl"), "rb")); net = N["paths"]; spots = {}
idr = np.zeros((M, M), np.int32); jn = np.ones((M, M), bool)
for i, p in enumerate(net, 1):
    c = p["cells"]; idr[c[:, 0], c[:, 1]] = np.where(idr[c[:, 0], c[:, 1]] == 0, i, idr[c[:, 0], c[:, 1]]); jn[c[0, 0], c[0, 1]] = False; jn[c[-1, 0], c[-1, 1]] = False
comp, isl = N["comp"], N["isl"]; nc = int(comp.max()) + 1; has = np.zeros(nc, bool); has[comp[N["fixed"]]] = True; size = np.bincount(comp, minlength=nc)
print("rivers: %d in %d networks | networks that reach the sea or a lake: %d, carrying %.1f%% of river length | end inland: %d" % (len(net), nc, has.sum(), 100 * size[has].sum() / len(comp), (~has).sum()))
# cities that stood on a drawn river
drawn = read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0; eiv = np.load(os.path.join(WORK, "eiv.npy")); dd = ndi.distance_transform_edt(~drawn)
alpha = read_png(os.path.join(WORK, "rivers12000.png"))[..., 3] > 128; dr = ndi.distance_transform_edt(~alpha) / 2
rows = [r for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if r["KIND"] == "city" and r["X"]]
on = [(r["NAME"], int(float(r["X"])), int(float(r["Y"]))) for r in rows if dd[int(float(r["Y"])), int(float(r["X"]))] <= 4 and not eiv[int(float(r["Y"])), int(float(r["X"]))]]
d = np.array([dr[min(y * 2 + 1, M - 1), min(x * 2 + 1, M - 1)] for n, x, y in on]); o = np.argsort(-d)
print("cities that stood on a drawn river: %d | now within 1.5 px of a river: %d, within 3 px: %d, farther than 6 px: %d | median %.1f px" % (len(on), (d <= 1.5).sum(), (d <= 3).sum(), (d > 6).sum(), np.median(d)))
print("  farthest:", ", ".join("%s %.0f" % (on[k][0], d[k]) for k in o[:14])); spots["city"] = [(on[k][1], on[k][2]) for k in o[:6]]
# doubled lines: another river within 4 px, away from any junction
jd = ndi.distance_transform_edt(jn); flag = np.zeros((M, M), bool); nd = 0
for i, p in enumerate(net, 1):
    c = p["cells"]; bad = np.zeros(len(c), bool)
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            if dy * dy + dx * dx > 16: continue
            v = idr[np.clip(c[:, 0] + dy, 0, M - 1), np.clip(c[:, 1] + dx, 0, M - 1)]; bad |= (v != 0) & (v != i)
    bad &= jd[c[:, 0], c[:, 1]] > 16; flag[c[bad, 0], c[bad, 1]] = True; nd += int(bad.sum())
lab, k = ndi.label(ndi.binary_dilation(flag, iterations=5)); sz = ndi.sum(flag, lab, np.arange(1, k + 1)) if k else np.array([]); com = ndi.center_of_mass(flag, lab, np.arange(1, k + 1)) if k else []
big = [j for j in np.argsort(-sz) if sz[j] >= 12]
print("doubled lines: %d cells in %d stretches of 12 cells or more |" % (nd, len(big)), " ".join("(%d,%d):%d" % (com[j][1] // 2, com[j][0] // 2, sz[j]) for j in big[:10])); spots["double"] = [(int(com[j][1] // 2), int(com[j][0] // 2)) for j in big[:6]]
# specks
lab, k = ndi.label(alpha); sz = np.bincount(lab.ravel())[1:]; small = np.nonzero(sz < 80)[0]
com = ndi.center_of_mass(alpha, lab, small + 1) if len(small) else []
print("specks (drawn blobs under 80 px): %d |" % len(small), " ".join("(%d,%d)" % (c[1] // 2, c[0] // 2) for c in com[:10])); spots["speck"] = [(int(c[1] // 2), int(c[0] // 2)) for c in com[:6]]
# ruler-straight runs and cusps
st = []; cu = []; tot = 0
for p in net:
    c = p["cells"].astype(float); n = len(c); tot += n; Wn = 80
    for a in range(0, n - Wn, 20):
        s = c[a:a + Wn]; ch = s[-1] - s[0]; L = np.hypot(*ch)
        if L < 60: continue
        dev = np.abs((s[:, 0] - s[0, 0]) * ch[1] - (s[:, 1] - s[0, 1]) * ch[0]) / L
        if dev.max() < 0.9: st.append((int(s[Wn // 2, 1] // 2), int(s[Wn // 2, 0] // 2)))
    if n > 30:
        s = ndi.gaussian_filter1d(c, 1.5, axis=0, mode="nearest"); u = s[8:-8] - s[:-16]; v = s[16:] - s[8:-8]
        cs = (u * v).sum(1) / (np.hypot(u[:, 0], u[:, 1]) * np.hypot(v[:, 0], v[:, 1]) + 1e-9); k = np.nonzero(cs < -0.5)[0]
        if len(k): j = k[np.argmin(cs[k])] + 8; cu.append((int(c[j, 1] // 2), int(c[j, 0] // 2)))
print("ruler-straight runs of 80 cells: %d (%.1f%% of river length) |" % (len(st), 100 * len(st) * 20 / tot), " ".join("(%d,%d)" % q for q in st[:8])); spots["straight"] = st[:6]
print("hairpin cusps: %d |" % len(cu), " ".join("(%d,%d)" % q for q in cu[:10])); spots["cusp"] = cu[:6]
inl = sorted(N["inland"], key=lambda r: -size[comp[r]])
print("networks that end inland, largest first (cells, x, y):", ", ".join("%d (%d,%d)" % (size[comp[r]], N["cx"][r] // 2, N["cy"][r] // 2) for r in inl[:16])); spots["inland"] = [(int(N["cx"][r] // 2), int(N["cy"][r] // 2)) for r in inl[:6]]
pickle.dump(spots, open(os.path.join(WORK, "rivqa.pkl"), "wb"))
