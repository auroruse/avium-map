"""Along every border two regions share, their warps should name the same real place. Measure the gap.
-> work/seams.npy rows: regionA, regionB, x6000, y6000, lonA, latA, lonB, latB, km"""
import sys, pickle, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb")); region = np.load(os.path.join(WORK, "region.npy"))
reg2u = np.load(os.path.join(WORK, "reg2u.npy")); codes = json.load(open(os.path.join(WORK, "ne_meta.json")))["codes"]
ov = np.load(os.path.join(WORK, "ov_samples.npy"))
ov = ov[ov[:, 3] > 0]
# only real land borders: the two units must touch in the real world too (a suture is meant to disagree)
rs = np.load(os.path.join(WORK, "real_samples.npy")); k = rs[:, 0].astype(np.int64) * 1000 + rs[:, 1].astype(np.int64)
ku, kc = np.unique(k, return_counts=True); realpair = set(ku[kc >= 30].tolist())
ov = ov[np.array([int(reg2u[int(r)]) * 1000 + int(t) in realpair for r, t in zip(ov[:, 0], ov[:, 3])])]
ix = np.clip(np.floor((ov[:, 1] + 1.6 * ov[:, 4]) / 2).astype(int), 0, 2999); iy = np.clip(np.floor((ov[:, 2] + 1.6 * ov[:, 5]) / 2).astype(int), 0, 2999)
nb = region[iy, ix]; a = ov[:, 0].astype(int)
ok = (nb > 0) & (nb != a) & (reg2u[np.clip(nb, 0, None)] == ov[:, 3].astype(int)) & np.isin(a, list(warps)) & np.isin(nb, list(warps))
ov, a, nb = ov[ok], a[ok], nb[ok]
out = np.zeros((len(ov), 9))
for A in np.unique(a):
    m = a == A; lo, la = warps[int(A)](ov[m, 1], ov[m, 2]); out[m, 4] = lo; out[m, 5] = la
for B in np.unique(nb):
    m = nb == B; lo, la = warps[int(B)](ov[m, 1], ov[m, 2]); out[m, 6] = lo; out[m, 7] = la
p1 = np.radians(out[:, 5]); p2 = np.radians(out[:, 7]); dl = np.radians(out[:, 6] - out[:, 4])
out[:, 8] = 2 * 6371 * np.arcsin(np.sqrt(np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))
out[:, 0] = a; out[:, 1] = nb; out[:, 2] = ov[:, 1]; out[:, 3] = ov[:, 2]
np.save(os.path.join(WORK, "seams.npy"), out)
km = out[:, 8]
print("shared-border samples", len(km), "| gap km: median %.0f | p75 %.0f | p90 %.0f | p95 %.0f | over 100 km: %.1f%%" % (np.median(km), np.percentile(km, 75), np.percentile(km, 90), np.percentile(km, 95), 100 * (km > 100).mean()))
pairs = {}
for A, B, k in zip(a, nb, km):
    if A < B: pairs.setdefault((int(A), int(B)), []).append(k)
rows = sorted(((np.percentile(v, 90), np.median(v), len(v), k) for k, v in pairs.items() if len(v) >= 15), reverse=True)
print("worst seams (p90 km, median km, samples):")
print("  " + "; ".join(f"{codes[reg2u[k[0]]-1]}#{k[0]}|{codes[reg2u[k[1]]-1]}#{k[1]} {p:.0f}/{md:.0f}/{n}" for p, md, n, k in rows[:40]))

# ---- consensus targets: where two neighbours disagree, which one to believe?
# The true place lies on the real border between the two units, and an estimate near one of its region's pinned
# anchors has had less room to slide. The better estimate becomes a target for both regions.
if "--targets" in sys.argv:
    import fit as F
    from scipy.spatial import cKDTree
    lm = np.load(os.path.join(WORK, "landmarks.npy")) if os.path.exists(os.path.join(WORK, "landmarks.npy")) else np.zeros((0, 6))
    atree = {}
    for r in np.unique(lm[:, 0]): atree[int(r)] = cKDTree(lm[lm[:, 0] == r][:, 1:3])
    def cost(reg, other, lon, lat, x, y):
        """km off the real border between the two units + a quarter of the distance to this region's nearest anchor"""
        c = np.full(len(lon), 1e6)
        for R in np.unique(reg):
            m = reg == R; U = F.Unit.get(int(reg2u[int(R)]))
            E, N = aeqd_fwd(lon[m], lat[m], U.lon0, U.lat0)
            d = np.full(m.sum(), 1e6); oth = other[m]
            for O in np.unique(oth):
                t = int(reg2u[int(O)])
                if t in U.trees:
                    k = oth == O; d[k] = U.trees[t].query(np.stack([E[k], N[k]], 1))[0]
            a = atree[int(R)].query(np.stack([x[m], y[m]], 1))[0] * 3.5 if int(R) in atree else np.full(m.sum(), 6000.0)
            c[m] = d + 0.25 * np.minimum(a, 6000.0)
        return c
    A, B, x, y = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
    cA = cost(A, B, out[:, 4], out[:, 5], x, y); cB = cost(B, A, out[:, 6], out[:, 7], x, y)
    useA = cA <= cB
    tl = np.where(useA, out[:, 4], out[:, 6]); tp = np.where(useA, out[:, 5], out[:, 7])
    close = out[:, 8] < 25
    # where they already agree, meet in the middle (lon is safe to average at this separation)
    tl = np.where(close, out[:, 4] + ((out[:, 6] - out[:, 4] + 180) % 360 - 180) / 2, tl); tp = np.where(close, (out[:, 5] + out[:, 7]) / 2, tp)
    ok = np.minimum(cA, cB) < 400
    T = np.concatenate([np.stack([A, x, y, tl, tp], 1)[ok], np.stack([B, x, y, tl, tp], 1)[ok]])
    np.save(os.path.join(WORK, "border_targets.npy"), T)
    won = {}
    for a_, b_, ua, cl in zip(A[ok], B[ok], useA[ok], close[ok]):
        if cl: continue
        w = int(a_) if ua else int(b_); l = int(b_) if ua else int(a_)
        won[w] = won.get(w, 0) + 1; won[-l] = won.get(-l, 0) + 1
    lost = sorted(((v, -k) for k, v in won.items() if k < 0), reverse=True)[:14]
    print("border targets:", len(T), "| regions corrected most (samples where the neighbour was believed):", "; ".join(f"{codes[reg2u[r]-1]}#{r} {v}" for v, r in lost))
