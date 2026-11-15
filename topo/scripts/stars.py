"""Match each region's whole constellation of city dots to its country's real cities in one go.
A single dot can be mistaken; a pattern of several, matched under one similarity, cannot.
-> work/star_anchors.npy rows: region, x6000, y6000, lon, lat ; work/star_report.json"""
import sys, json, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
import shapefile
rng = np.random.default_rng(3)
SHOW = set(sys.argv[1:])
region = np.load(os.path.join(WORK, "region.npy")); reg2u = np.load(os.path.join(WORK, "reg2u.npy"))
dots = np.load(os.path.join(WORK, "dots.npy")); warps = pickle.load(open(os.path.join(WORK, "warps_prior.pkl"), "rb"))
meta = json.load(open(os.path.join(WORK, "ne_meta.json"))); codes = meta["codes"]; idx = {c: i + 1 for i, c in enumerate(codes)}
ALIAS = {"SAH": "MAR", "AFG": "IRN", "EST": "FIN", "SVK": "HUN"}
fitted = np.isin(region, list(warps))
dist, (iy, ix) = ndi.distance_transform_edt(~fitted, return_indices=True)
r = shapefile.Reader(os.path.join(DATA, "ne_places", "ne_10m_populated_places"), encoding="utf-8")
f = [x[0] for x in r.fields[1:]]; g = {k: f.index(k) for k in ("NAME", "ADM0_A3", "POP_MAX", "FEATURECLA", "LATITUDE", "LONGITUDE")}
byu = {}
for rec in r.records():
    c = ALIAS.get(rec[g["ADM0_A3"]], rec[g["ADM0_A3"]])
    # the overlay only marks capitals and sizeable cities; a hamlet in the pool is a false match waiting for a speck of ink
    fc = rec[g["FEATURECLA"]]
    if not (rec[g["POP_MAX"]] >= 80000 or "capital" in fc): continue
    if c in idx: byu.setdefault(idx[c], []).append((rec[g["POP_MAX"]], "Admin-0 capital" in fc, rec[g["LONGITUDE"]], rec[g["LATITUDE"]], rec[g["NAME"]]))
byreg = {}
for k, (x, y, a) in enumerate(dots):
    yi, xi = int(round(y)), int(round(x))
    if dist[yi, xi] > 5: continue
    byreg.setdefault(int(region[iy[yi, xi], ix[yi, xi]]), []).append(k)

def match(T, C, mid, base=30.0, grow=0.07):
    """dots at plane positions T against cities C: one-to-one, tolerance loosening away from the pivot"""
    D = np.hypot(T[:, None, 0] - C[None, :, 0], T[:, None, 1] - C[None, :, 1])
    c = D.argmin(1); d = D[np.arange(len(T)), c]
    tol = base + grow * np.hypot(T[:, 0] - mid[0], T[:, 1] - mid[1])
    ok = d < tol
    for cc in np.unique(c[ok]):                      # a city belongs to the nearest dot only
        m = np.nonzero(ok & (c == cc))[0]
        if len(m) > 1: ok[m[d[m] > d[m].min()]] = False
    return ok, c, d, tol

out = []; report = []
for b, ks in byreg.items():
    u = int(reg2u[b]); cities = sorted(byu.get(u, []), reverse=True)
    if not cities: continue
    n = len(ks); W = warps[b]
    P = np.stack([2 * dots[ks, 0] + 1, 2 * dots[ks, 1] + 1], 1); big = dots[ks, 2] >= 25
    plo, pla = W(P[:, 0], P[:, 1]); lon0, lat0 = centroid(plo, pla)
    K = min(len(cities), max(4 * n + 10, 25))
    pool = cities[:K] + [c for c in cities[K:] if c[1]]
    C = np.stack(aeqd_fwd(np.array([c[2] for c in pool]), np.array([c[3] for c in pool]), lon0, lat0), 1)
    cap = np.array([c[1] for c in pool])
    Q0 = np.stack(aeqd_fwd(plo, pla, lon0, lat0), 1)
    p = P[:, 0] - 1j * P[:, 1]; Cc = C[:, 0] + 1j * C[:, 1]
    # prior rotation of this region, from its current warp
    A = W.A; ang0 = np.angle(complex(A[0, 0], A[1, 0]))
    D0 = np.hypot(Q0[:, None, 0] - C[None, :, 0], Q0[:, None, 1] - C[None, :, 1])
    cand = []
    for i in range(n):
        o = np.argsort(D0[i]); o = o[D0[i][o] < 900][:7]
        if big[i] and cap[o].any(): o = o[cap[o]]
        cand.append(o)
    best = None
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n) if abs(p[i] - p[j]) >= 14]
    if len(pairs) > 400: pairs = [pairs[k] for k in rng.choice(len(pairs), 400, replace=False)]
    for i, j in pairs:
        for a in cand[i]:
            for c2 in cand[j]:
                if a == c2: continue
                s = (Cc[c2] - Cc[a]) / (p[j] - p[i])
                if not (1.9 < abs(s) < 5.6): continue
                da = np.angle(s * np.exp(-1j * ang0))
                if abs(da) > np.radians(50): continue
                t = s * (p - p[i]) + Cc[a]; T = np.stack([t.real, t.imag], 1)
                ok, cc, d, tol = match(T, C, (T[i] + T[j]) / 2)
                sc = ok.sum() + 0.01 * (1 - d[ok] / tol[ok]).sum()
                if best is None or sc > best[0]: best = (sc, ok, cc, s, Cc[a] - s * p[i])
    if n == 1:
        o = cand[0]
        if len(o) and D0[0][o[0]] < (300 if big[0] and cap[o[0]] else 60) and (len(o) == 1 or D0[0][o[1]] > 1.8 * D0[0][o[0]] + 20):
            out.append((b, P[0, 0], P[0, 1], pool[o[0]][2], pool[o[0]][3])); report.append((codes[u - 1], b, 1, 1))
        continue
    if best is None: report.append((codes[u - 1], b, n, 0)); continue
    sc, ok, cc, s, t0 = best
    need = 2 if n == 2 else max(3, int(np.ceil(0.34 * n)))
    if ok.sum() < need: report.append((codes[u - 1], b, n, 0)); continue
    if n == 2 and not (D0[0][cc[0]] < 300 and D0[1][cc[1]] < 300): report.append((codes[u - 1], b, n, 0)); continue
    # refine: affine through the matched pairs, then rematch with tolerance tied to the nearest matched dot
    for _ in range(3):
        m = np.nonzero(ok)[0]
        if len(m) >= 3:
            Af = fit_affine(P[m, 0], -P[m, 1], C[cc[m], 0], C[cc[m], 1], np.ones(len(m)))
            T = np.stack([Af[0, 0] * P[:, 0] - Af[0, 1] * P[:, 1] + Af[0, 2], Af[1, 0] * P[:, 0] - Af[1, 1] * P[:, 1] + Af[1, 2]], 1)
            res = T[m] - C[cc[m]]
            # carry each matched dot's leftover to its neighbours, so a bent country is followed locally
            dd = np.hypot(P[:, None, 0] - P[None, m, 0], P[:, None, 1] - P[None, m, 1]); w = 1.0 / (dd + 20.0) ** 2
            T = T - (w @ res) / w.sum(1)[:, None]
        else:
            t = s * p + t0; T = np.stack([t.real, t.imag], 1); dd = np.hypot(P[:, None, 0] - P[None, m, 0], P[:, None, 1] - P[None, m, 1])
        D = np.hypot(T[:, None, 0] - C[None, :, 0], T[:, None, 1] - C[None, :, 1]); c2 = D.argmin(1); d = D[np.arange(n), c2]
        tol = 30.0 + 0.10 * dd.min(1) * abs(s)
        ok2 = d < tol; ok2[m] = True; c2[m] = cc[m]
        for q in np.unique(c2[ok2]):
            mm = np.nonzero(ok2 & (c2 == q))[0]
            if len(mm) > 1:
                keep = mm[np.isin(mm, m)]
                keep = keep[0] if len(keep) else mm[d[mm].argmin()]
                ok2[mm[mm != keep]] = False
        ok, cc = ok2, c2
    for k in np.nonzero(ok)[0]: out.append((b, P[k, 0], P[k, 1], pool[cc[k]][2], pool[cc[k]][3]))
    report.append((codes[u - 1], b, n, int(ok.sum())))
    if codes[u - 1] in SHOW: print(" ", codes[u - 1], b, ":", ", ".join(pool[cc[k]][4] for k in np.nonzero(ok)[0]))
np.save(os.path.join(WORK, "star_anchors.npy"), np.array(out))
report.sort(key=lambda t: -t[2])
json.dump(report, open(os.path.join(WORK, "star_report.json"), "w"))
tot = sum(t[2] for t in report); got = sum(t[3] for t in report)
print(f"dots on fitted regions: {tot} | matched to a real city: {got} | regions with dots: {len(report)}, with a match: {sum(1 for t in report if t[3])}")
print("largest:", "; ".join(f"{c}#{b} {m}/{n}" for c, b, n, m in report[:36]))
print("unmatched regions with 2+ dots:", "; ".join(f"{c}#{b} 0/{n}" for c, b, n, m in report if m == 0 and n >= 2))
