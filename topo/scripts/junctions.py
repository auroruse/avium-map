"""Triple junctions (three units, or two units and water, meet) on the overlay and in the real world."""
import sys, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy.spatial import cKDTree

def cluster(P, r):
    """greedy cluster of points (n,2) within r -> list of index arrays"""
    if len(P) == 0: return []
    tree = cKDTree(P); seen = np.zeros(len(P), bool); out = []
    for i in range(len(P)):
        if seen[i]: continue
        grp = [i]; seen[i] = True; k = 0
        while k < len(grp):
            for j in tree.query_ball_point(P[grp[k]], r):
                if not seen[j]: seen[j] = True; grp.append(j)
            k += 1
        out.append(np.array(grp))
    return out

def windows(lab, wrap):
    a = lab[:-1]; c = lab[1:]
    if wrap:
        b = np.roll(a, -1, 1); d = np.roll(c, -1, 1)
    else:
        a, b, c, d = a[:, :-1], lab[:-1, 1:], c[:, :-1], lab[1:, 1:]
    m = (a != b) | (a != c) | (a != d) | (b != c) | (b != d) | (c != d)
    ii, jj = np.nonzero(m)
    q = np.stack([a[ii, jj], b[ii, jj], c[ii, jj], d[ii, jj]], 1)
    return ii, jj, q

if not os.path.exists(os.path.join(WORK, "real_junctions.npy")) or "--real" in sys.argv:
    # ---------- real
    real = np.load(os.path.join(WORK, "real_unit.npy"))
    ii, jj, q = windows(real, True)
    qs = np.sort(q, 1); nd = 1 + (qs[:, 1:] != qs[:, :-1]).sum(1)
    m = nd == 3; ii, jj, qs = ii[m], jj[m], qs[m]
    lon = -180 + (jj + 1) / 60.0; lon[lon >= 180] -= 360; lat = 90 - (ii + 1) / 60.0
    rows = []
    for k in range(len(ii)):
        u = np.unique(qs[k])
        for x in u:
            if x <= 0: continue
            o = u[u != x]
            rows.append((x, o[0], o[1], lon[k], lat[k]))
    R = np.array(rows, np.float64)
    # cluster per (unit, pair) within ~12 km (use degrees scaled by cos lat)
    out = []
    key = R[:, 0] * 1e6 + R[:, 1] * 1e3 + R[:, 2]
    for kk in np.unique(key):
        r = R[key == kk]
        P = np.stack([r[:, 3] * np.cos(np.radians(r[:, 4])), r[:, 4]], 1)
        for g in cluster(P, 0.12):
            # mean on the sphere via simple average is fine at this scale (no cluster spans the antimeridian by 12 km... guard)
            lo = r[g, 3]
            if np.ptp(lo) > 180: lo = np.where(lo < 0, lo + 360, lo)
            out.append((r[0, 0], r[0, 1], r[0, 2], (lo.mean() + 180) % 360 - 180, r[g, 4].mean()))
    np.save(os.path.join(WORK, "real_junctions.npy"), np.array(out))
    print("real junctions", len(out))

# ---------- overlay
blob = np.load(os.path.join(WORK, "region.npy")); b2u = np.load(os.path.join(WORK, "reg2u.npy"))
ii, jj, q = windows(blob, False)
rows = []
for k in range(len(ii)):
    bs = np.unique(q[k])
    if (bs < 0).any(): continue
    us = b2u[bs]
    for b, u in zip(bs, us):
        if b == 0: continue
        o = np.unique(us[us != u])
        if len(o) == 2: rows.append((b, o[0], o[1], 2 * jj[k] + 2, 2 * ii[k] + 2))
O = np.array(rows, np.float64); out = []
key = O[:, 0] * 1e6 + O[:, 1] * 1e3 + O[:, 2]
for kk in np.unique(key):
    r = O[key == kk]
    for g in cluster(r[:, 3:5], 14):
        out.append((r[0, 0], r[0, 1], r[0, 2], r[g, 3].mean(), r[g, 4].mean()))
np.save(os.path.join(WORK, "ov_junctions.npy"), np.array(out))
print("overlay junctions", len(out))
