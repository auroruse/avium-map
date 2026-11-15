"""Georeference every labelled overlay blob.
Typed-boundary ICP (similarity -> affine -> coarse-to-fine TPS) anchored by triple junctions and hand landmarks."""
import sys, json, pickle, time, copy; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy.spatial import cKDTree
rng = np.random.default_rng(7)
SLO, SHI = 1.9, 5.6        # plausible km per overlay px on this map
meta = json.load(open(os.path.join(WORK, "ne_meta.json"))); codes = meta["codes"]
blob = np.load(os.path.join(WORK, "region.npy")); b2u = np.load(os.path.join(WORK, "reg2u.npy"))
ov = np.load(os.path.join(WORK, "ov_samples.npy")); rs = np.load(os.path.join(WORK, "real_samples.npy"))
OJ = np.load(os.path.join(WORK, "ov_junctions.npy")); RJ = np.load(os.path.join(WORK, "real_junctions.npy"))
ru = rs[:, 0].astype(int); rstart = np.searchsorted(ru, np.arange(ru.max() + 2))
ostart = np.searchsorted(ov[:, 0], np.arange(int(ov[:, 0].max()) + 2))
LM = {}
lmf = os.path.join(WORK, "landmarks.npy")       # rows: blob, x6000, y6000, lon, lat
if os.path.exists(lmf):
    for r in np.load(lmf): LM.setdefault(int(r[0]), []).append(r[1:])

AREA = np.bincount(blob[blob > 0]); UAREA = np.bincount(b2u[1:len(AREA)], weights=AREA[1:], minlength=int(b2u.max()) + 1)
REAL = np.load(os.path.join(WORK, "real_unit.npy"), mmap_mode="r")
INNER = {}                                          # a few thousand interior pixels of every region, 6000 grid
BT = {}
btf = os.path.join(WORK, "border_targets.npy")       # rows: region, x6000, y6000, lon, lat (from seams.py --targets)
if os.path.exists(btf) and "--targets" in sys.argv:
    _bt = np.load(btf); _o = np.argsort(_bt[:, 0], kind="stable"); _bt = _bt[_o]
    _s = np.searchsorted(_bt[:, 0], np.arange(int(_bt[:, 0].max()) + 2))
    for _r in np.unique(_bt[:, 0]).astype(int): BT[_r] = _bt[_s[_r]:_s[_r + 1], 1:]
adj = {}
for a, b in ((blob[:, :-1], blob[:, 1:]), (blob[:-1], blob[1:])):
    m = (a != b) & (a > 0) & (b > 0)
    k, c = np.unique(a[m].astype(np.int64) * 100000 + b[m], return_counts=True)
    for kk, cc in zip(k, c):
        i, j = int(kk // 100000), int(kk % 100000)
        adj.setdefault(i, {}); adj.setdefault(j, {})
        adj[i][j] = adj[i].get(j, 0) + int(cc); adj[j][i] = adj[j].get(i, 0) + int(cc)

class Unit:
    cache = {}
    def __init__(self, u):
        r = rs[rstart[u]:rstart[u + 1]]
        self.lon0, self.lat0 = centroid(r[:, 2], r[:, 3])
        E, N = aeqd_fwd(r[:, 2], r[:, 3], self.lon0, self.lat0)
        t = r[:, 1].astype(int); q = r[:, 4].astype(int)
        # outward normal of each real sample, expressed in this unit's plane
        dl = np.array([0.02, -0.02, 0.0, 0.0])[q]; dp = np.array([0.0, 0.0, 0.02, -0.02])[q]
        E2, N2 = aeqd_fwd(r[:, 2] + dl / np.maximum(np.cos(np.radians(r[:, 3])), 0.05), r[:, 3] + dp, self.lon0, self.lat0)
        nr = np.stack([E2 - E, N2 - N], 1); nr /= np.maximum(np.hypot(nr[:, 0], nr[:, 1]), 1e-9)[:, None]
        self.trees = {}; self.pts = {}; self.nrm = {}
        for tt in np.unique(t):
            m = t == tt
            if m.sum() >= (30 if tt else 4):          # a real land border is at least ~50 km of samples
                self.pts[tt] = np.stack([E[m], N[m]], 1); self.trees[tt] = cKDTree(self.pts[tt]); self.nrm[tt] = nr[m]
        j = RJ[RJ[:, 0] == u]
        JE, JN = aeqd_fwd(j[:, 3], j[:, 4], self.lon0, self.lat0) if len(j) else (np.zeros(0), np.zeros(0))
        self.J = [(int(a), int(b), e, n) for (a, b), e, n in zip(j[:, 1:3], JE, JN)]
    @classmethod
    def get(cls, u):
        if u not in cls.cache: cls.cache[u] = Unit(u)
        return cls.cache[u]

class Blob:
    def __init__(self, b):
        self.b = b; self.u = int(b2u[b]); self.unit = Unit.get(self.u)
        s = ov[ostart[b]:ostart[b + 1]]
        self.x = s[:, 1].astype(float); self.y = s[:, 2].astype(float)
        self.nx = s[:, 4].astype(float); self.ny = s[:, 5].astype(float)
        t = s[:, 3].astype(int); w = np.where(t == 0, 1.0, 2.0)
        sut = ~np.isin(t, list(self.unit.trees.keys()))        # neighbour is not a real neighbour: a suture
        t[sut] = 0; w[sut] = 0.4
        self.sut = sut
        if 0 not in self.unit.trees:                            # landlocked unit: no coast to match
            keep = t != 0; self.x, self.y, t, w, self.sut = self.x[keep], self.y[keep], t[keep], w[keep], self.sut[keep]
            self.nx, self.ny = self.nx[keep], self.ny[keep]
        self.t = t; self.w = w; self.n = len(t)
        self.u_ = self.x; self.v_ = -self.y
        # junctions of this blob, with suture types folded into water
        self.oj = []
        for r in OJ[OJ[:, 0] == b]:
            tt = sorted(int(v) if int(v) in self.unit.trees else 0 for v in r[1:3])
            if tt[0] != tt[1]: self.oj.append((tt[0], tt[1], r[3], r[4]))
        self.rev = {}
        whole = (self.t != 0).sum() == 0 and AREA[b] >= 0.5 * UAREA[self.u]      # an island drawn complete
        for tt in np.unique(self.t):
            if tt == 0 and not whole: continue
            P = self.unit.pts[tt]; sel = rng.choice(len(P), min(len(P), 1500), replace=False)
            self.rev[tt] = (P[sel], self.unit.nrm[tt][sel])
        self.L = np.zeros((0, 4))                               # landmarks: u, v, E, N
        self.hand = np.zeros((0, 4)); self.hand_trust = np.zeros(0, bool)
        if b in LM:
            h = np.array(LM[b]); E, N = aeqd_fwd(h[:, 2], h[:, 3], self.unit.lon0, self.unit.lat0)
            self.hand = np.stack([h[:, 0], -h[:, 1], E, N], 1); self.hand_trust = h[:, 4] > 0
        self.bt = np.zeros((0, 4))                              # agreed places along shared borders: u, v, E, N
        if b in BT:
            t = BT[b]; E, N = aeqd_fwd(t[:, 2], t[:, 3], self.unit.lon0, self.unit.lat0)
            self.bt = np.stack([t[:, 0], -t[:, 1], E, N], 1)
        self.L = self.hand; self.hand_ok = np.ones(len(self.hand), bool); self.bad_j = set(); self.nj = 0; self.dropped = 0
        self.J = np.zeros((0, 4))
    def drop_worst(self, W):
        """remove the anchor that a smooth warp disagrees with most; hand-placed ones are never dropped"""
        cand = []
        for k, j in enumerate(self.J):
            E, N = W.plane(np.array([j[0]]), np.array([-j[1]]))
            cand.append((float(np.hypot(E[0] - j[2], N[0] - j[3])), "j", k))
        if not cand: return False
        d, kind, k = max(cand)
        if d < 8.0: return False                      # nothing is really out of line; the fold is not an anchor's doing
        if kind == "h": self.hand_ok[k] = False
        else:
            self.bad_j.add((round(float(self.J[k, 0]), 1), round(float(self.J[k, 1]), 1))); self.J = np.delete(self.J, k, 0)
        self.L = np.concatenate([self.hand[self.hand_ok], self.J]); self.dropped += 1
        return True
    def match_junctions(self, W, dmax=500.0):
        got = {}
        for (t1, t2, x, y) in self.oj:
            if (round(float(x), 1), round(float(-y), 1)) in self.bad_j: continue
            E, N = W.plane(np.array([x]), np.array([y])); best = None
            for k, (a, b, e, n) in enumerate(self.unit.J):
                if (a, b) != (t1, t2): continue
                d = float(np.hypot(e - E[0], n - N[0]))
                if d < dmax and (best is None or d < best[0]): best = (d, k)
            if best and (best[1] not in got or best[0] < got[best[1]][0]):
                got[best[1]] = (best[0], x, -y, self.unit.J[best[1]][2], self.unit.J[best[1]][3])
        self.J = np.array([v[1:] for v in got.values()]) if got else np.zeros((0, 4))
        self.L = np.concatenate([self.hand[self.hand_ok], self.J]); self.nj = len(self.J)
    def mapped(self, W):
        E, N = W.plane(self.x, self.y); E2, N2 = W.plane(self.x + 3 * self.nx, self.y + 3 * self.ny)
        n = np.stack([E2 - E, N2 - N], 1); n /= np.maximum(np.hypot(n[:, 0], n[:, 1]), 1e-9)[:, None]
        return E, N, n
    def nn(self, W, K=12):
        """nearest real boundary point of the same type that faces the same way"""
        E, N, n = self.mapped(W)
        d = np.full(self.n, 1e9); TE = np.zeros(self.n); TN = np.zeros(self.n)
        for tt in np.unique(self.t):
            m = np.nonzero(self.t == tt)[0]
            P = self.unit.pts[tt]; k = min(K, len(P))
            dd, ii = self.unit.trees[tt].query(np.stack([E[m], N[m]], 1), k=k)
            if k == 1: dd = dd[:, None]; ii = ii[:, None]
            ok = (self.unit.nrm[tt][ii] * n[m][:, None, :]).sum(-1) > 0.0
            first = ok.argmax(1); has = ok.any(1); r = np.arange(len(m))
            d[m] = np.where(has, dd[r, first], 1e9); p = P[ii[r, first]]; TE[m] = p[:, 0]; TN[m] = p[:, 1]
        return d, TE, TN
    def reverse(self, W, dmax):
        """real boundary points pulling the nearest mapped overlay sample of the same type: stops collapse"""
        E, N, n = self.mapped(W); U, V, TE, TN, Wt = [], [], [], [], []
        for tt, (Q, Qn) in self.rev.items():
            idx = np.nonzero(self.t == tt)[0]
            if len(idx) < 3: continue
            dd, jj = cKDTree(np.stack([E[idx], N[idx]], 1)).query(Q)
            k = (dd < dmax) & ((n[idx[jj]] * Qn).sum(1) > 0.0)
            if k.any():
                j = idx[jj[k]]
                U.append(self.u_[j]); V.append(self.v_[j]); TE.append(Q[k, 0]); TN.append(Q[k, 1]); Wt.append(0.5 * self.w[j])
        if not U: return [np.zeros(0)] * 5
        return [np.concatenate(a) for a in (U, V, TE, TN, Wt)]
    def score(self, W, cap=250.0):
        sc = W.scale()
        if not (SLO < sc < SHI): return 1e6
        d, _, _ = self.nn(W)
        return float((np.minimum(d, cap) * self.w).sum() / self.w.sum())   # km
    def icp(self, W, mode, iters, d0, d1, lam=None):
        for k in range(iters):
            dmax = d0 + (d1 - d0) * k / max(iters - 1, 1)
            d, TE, TN = self.nn(W)
            keep = d < dmax
            if mode != "tps" and keep.sum() >= 8: keep &= d < 2.5 * np.median(d[keep]) + 5.0
            if keep.sum() + len(self.L) + len(self.bt) < 6: break
            u, v, E, N, w = self.u_[keep], self.v_[keep], TE[keep], TN[keep], self.w[keep]
            ru_, rv_, rE, rN, rw = self.reverse(W, dmax)
            if self.b in INNER:
                # containment: the region's own ground must land on its own country. A pixel that lands on real
                # water is pulled to the nearest real shore; one that lands in a neighbour, to the border with it.
                gx, gy = INNER[self.b]; gE, gN = W.plane(gx, gy)
                lo, la = aeqd_inv(gE, gN, self.unit.lon0, self.unit.lat0)
                ru = REAL[np.clip(((90 - la) * 60).astype(int), 0, 10799), np.clip(((lo + 180) * 60).astype(int), 0, 21599)]
                for tt in np.unique(ru):
                    if tt == self.u or int(tt) not in self.unit.trees: continue
                    m = np.nonzero(ru == tt)[0]
                    dd, ii = self.unit.trees[int(tt)].query(np.stack([gE[m], gN[m]], 1))
                    k = dd < 1.5 * dmax
                    if k.any():
                        P = self.unit.pts[int(tt)][ii[k]]
                        ru_ = np.concatenate([ru_, gx[m[k]]]); rv_ = np.concatenate([rv_, -gy[m[k]]])
                        rE = np.concatenate([rE, P[:, 0]]); rN = np.concatenate([rN, P[:, 1]]); rw = np.concatenate([rw, np.full(int(k.sum()), 1.5)])
            if len(self.bt):                                    # agreed border places ride along with the reverse set
                ru_ = np.concatenate([ru_, self.bt[:, 0]]); rv_ = np.concatenate([rv_, self.bt[:, 1]])
                rE = np.concatenate([rE, self.bt[:, 2]]); rN = np.concatenate([rN, self.bt[:, 3]]); rw = np.concatenate([rw, np.full(len(self.bt), 4.0)])
            if mode != "tps" and len(ru_):
                u, v, E, N, w = (np.concatenate([u, ru_]), np.concatenate([v, rv_]), np.concatenate([E, rE]),
                                 np.concatenate([N, rN]), np.concatenate([w, rw]))
            nl = len(self.L)
            if nl:
                wl = np.full(nl, max(8.0, 0.25 * w.sum() / nl))
                ua, va, Ea, Na, wa = (np.concatenate([u, self.L[:, 0]]), np.concatenate([v, self.L[:, 1]]),
                                      np.concatenate([E, self.L[:, 2]]), np.concatenate([N, self.L[:, 3]]), np.concatenate([w, wl]))
            else: ua, va, Ea, Na, wa = u, v, E, N, w
            if mode == "sim" or len(ua) < 12:
                A = fit_similarity(ua, va, Ea, Na, wa)
                if not (SLO < np.hypot(A[0, 0], A[1, 0]) < SHI): break
                W.A = A; W.tps = None
            elif mode == "aff":
                A = fit_affine(ua, va, Ea, Na, wa)
                s = np.linalg.svd(A[:, :2], compute_uv=False)
                if not (s[1] / s[0] > 0.45 and np.linalg.det(A[:, :2]) > 0 and SLO < np.sqrt(s[0] * s[1]) < SHI): break
                W.A = A; W.tps = None
            else:
                W.tps = None
                n = keep.sum(); sel = rng.choice(n, min(n, 340), replace=False)
                nr = len(ru_); rsel = rng.choice(nr, min(nr, 420), replace=False, p=rw / rw.sum()) if nr else np.zeros(0, int)
                cu = np.concatenate([u[sel], ru_[rsel], self.L[:, 0]]); cv = np.concatenate([v[sel], rv_[rsel], self.L[:, 1]])
                cE = np.concatenate([E[sel], rE[rsel], self.L[:, 2]]); cN = np.concatenate([N[sel], rN[rsel], self.L[:, 3]])
                sm = np.concatenate([lam / w[sel], lam / rw[rsel], np.full(nl, lam * 0.02)])
                x0, y0 = cu, -cv
                E0, N0 = W.plane(x0, y0)
                W.c = np.array([self.u_.mean(), self.v_.mean()]); W.s = float(max(self.u_.std(), self.v_.std(), 1.0))
                q = np.stack([(cu - W.c[0]) / W.s, (cv - W.c[1]) / W.s], 1) + rng.normal(0, 1e-6, (len(cu), 2))
                W.tps = RBFInterpolator(q, np.stack([cE - E0, cN - N0], 1), kernel="thin_plate_spline", smoothing=sm, degree=1)
        return W

def guard(A, B):
    return Warp(B.unit.lon0, B.unit.lat0, A) if SLO < np.hypot(A[0, 0], A[1, 0]) < SHI else None

def init_centroids(B):
    P, Q, Wt = [], [], []
    for tt in np.unique(B.t):
        if tt == 0: continue
        m = B.t == tt
        if m.sum() < 5: continue
        P.append([B.u_[m].mean(), B.v_[m].mean()]); Q.append(B.unit.pts[tt].mean(0)); Wt.append(m.sum())
    if len(P) < 2: return None
    P, Q = np.array(P), np.array(Q)
    if np.ptp(P, 0).max() < 6: return None
    return guard(fit_similarity(P[:, 0], P[:, 1], Q[:, 0], Q[:, 1], np.array(Wt, float)), B)

def init_shape(B):
    types = np.unique(B.t)
    allp = np.concatenate([B.unit.pts[t] for t in types])
    if len(allp) > 4000: allp = allp[rng.choice(len(allp), 4000, replace=False)]
    oc = np.array([B.u_.mean(), B.v_.mean()]); rc = allp.mean(0)
    so = np.sqrt(((B.u_ - oc[0]) ** 2 + (B.v_ - oc[1]) ** 2).mean()); sr = np.sqrt(((allp - rc) ** 2).sum(1).mean())
    best = None
    for ang in np.arange(0, 360, 15):
        for f in (1.0, 0.75):
            a = float(np.clip(f * sr / max(so, 1e-6), SLO + .1, SHI - .1)) * np.exp(1j * ang * D2R); b = complex(*rc) - a * complex(*oc)
            W = Warp(B.unit.lon0, B.unit.lat0, [[a.real, -a.imag, b.real], [a.imag, a.real, b.imag]])
            B.icp(W, "sim", 4, 600, 300)
            s = B.score(W)
            if best is None or s < best[0]: best = (s, W)
    return best[1]

def init_hand(B):
    if len(B.hand) < 2: return None
    h = B.hand
    return guard(fit_similarity(h[:, 0], h[:, 1], h[:, 2], h[:, 3], np.ones(len(h))), B)

def init_from(B, Wn):
    lon, lat = Wn(B.x, B.y)
    E, N = aeqd_fwd(lon, lat, B.unit.lon0, B.unit.lat0)
    return guard(fit_similarity(B.u_, B.v_, E, N, np.ones(B.n)), B)

SCHED = ((30, 300), (10, 260), (3, 220), (1, 170), (0.3, 120), (0.1, 90), (0.05, 60))
def jac_ok(W, gx, gy, h=3.0):
    """the warp must not fold, pinch or balloon anywhere on the region (or just beyond it)"""
    E1, N1 = W.plane(gx + h, gy); E0, N0 = W.plane(gx - h, gy); E3, N3 = W.plane(gx, gy + h); E2, N2 = W.plane(gx, gy - h)
    a = (E1 - E0) / (2 * h); c = (N1 - N0) / (2 * h); b = (E3 - E2) / (2 * h); d = (N3 - N2) / (2 * h)
    det = a * d - b * c; det0 = -np.linalg.det(W.A[:, :2])
    r = det / det0
    fro = a * a + b * b + c * c + d * d
    s2 = np.sqrt(np.maximum((fro - np.sqrt(np.maximum(fro * fro - 4 * det * det, 0))) / 2, 0)); s1 = np.sqrt((fro + np.sqrt(np.maximum(fro * fro - 4 * det * det, 0))) / 2)
    sv = np.linalg.svd(W.A[:, :2], compute_uv=False)
    an = (s2 / np.maximum(s1, 1e-9)) / (sv[1] / sv[0])
    return bool(r.min() > 0.04 and np.percentile(r, 2) > 0.15 and np.percentile(r, 98) < 6.0 and np.percentile(an, 2) > 0.15)
def full(B, W):
    # a match further away than a fraction of the region's own size is not evidence of anything
    ext = W.scale() * 2 * np.sqrt(AREA[B.b]); cap = max(35.0, 0.3 * ext); big = max(120.0, ext)
    B.icp(W, "sim", 6, min(400, big), min(150, big)); B.match_junctions(W, min(500.0, big))
    B.icp(W, "sim", 4, min(300, big), min(150, big)); B.match_junctions(W, min(500.0, big))
    B.icp(W, "aff", 8, min(300, big), min(120, big)); B.match_junctions(W, min(500.0, big))
    B.stage = 0
    if B.n >= 40 or len(B.L) >= 4:
        good = copy.copy(W)
        for i, (lam, d) in enumerate(SCHED):
            ok = False
            for attempt in range(3):
                W = copy.copy(good); B.icp(W, "tps", 3, min(d, cap), min(d, cap), lam=lam)
                if jac_ok(W, *GRID[B.b]): ok = True; break
                if not B.drop_worst(good): break
            if not ok:
                W = good; break
            good = copy.copy(W); B.stage = i + 1
            if i in (1, 3): B.match_junctions(W, min(300.0, big))
    return W

if __name__ == "__main__":
    t0 = time.time()
    ids = [int(b) for b in np.unique(ov[:, 0]) if b2u[int(b)] > 0]
    blobs = {}
    for b in ids:
        B = Blob(b)
        if B.n >= 40 and AREA[b] >= 150: blobs[b] = B
    print("fitting", len(blobs), "blobs")
    from scipy import ndimage as ndi
    GRID = {}
    objs = ndi.find_objects(np.clip(blob, 0, None))
    for b in blobs:
        sl = objs[b - 1]; r0, c0 = max(sl[0].start - 12, 0), max(sl[1].start - 12, 0)
        m = ndi.binary_dilation(blob[r0:sl[0].stop + 12, c0:sl[1].stop + 12] == b, iterations=4)
        yy, xx = np.nonzero(m); k = rng.choice(len(yy), min(len(yy), 2500), replace=False)
        GRID[b] = (2.0 * (xx[k] + c0) + 1, 2.0 * (yy[k] + r0) + 1)
        yy, xx = np.nonzero(blob[sl] == b); k = rng.choice(len(yy), min(len(yy), 3000), replace=False)
        INNER[b] = (2.0 * (xx[k] + sl[1].start) + 1, 2.0 * (yy[k] + sl[0].start) + 1)
    fit = {}
    for b, B in blobs.items():
        cands = [c for c in (init_hand(B), init_centroids(B), init_shape(B)) if c is not None]
        best = None
        for i, W in enumerate(cands):
            B.icp(W, "sim", 10, 400, 150); s = B.score(W)
            if i == 0 and len(B.hand) >= 2: s = -1.0          # hand landmarks win outright
            if best is None or s < best[0]: best = (s, W)
        fit[b] = [best[0], best[1]]
    print("pass 1 done", round(time.time() - t0), "s")
    for rnd in range(4):
        changed = 0
        for b, B in blobs.items():
            for nb, cnt in sorted(adj.get(b, {}).items(), key=lambda kv: -kv[1]):
                if nb not in fit or fit[nb][0] > 25: continue
                W = init_from(B, fit[nb][1])
                if W is None: continue
                B.icp(W, "sim", 10, 400, 150); s = B.score(W)
                if s < fit[b][0] - 1.0: fit[b] = [s, W]; changed += 1
        print("pass 2 round", rnd, "improved", changed)
        if not changed: break
    out = {}; rep = []
    for b, B in blobs.items():
        W = full(B, fit[b][1])
        d, _, _ = B.nn(W); px = (d / W.scale())[~B.sut]
        if len(px) == 0: px = d / W.scale()
        out[b] = W
        rep.append((float(np.median(px)), float(np.percentile(px, 90)), float(fit[b][0]), b, codes[B.u - 1], B.n, W.scale(), B.nj, len(B.oj), B.stage))
    pickle.dump(out, open(os.path.join(WORK, "warps.pkl"), "wb"))
    rep.sort(reverse=True, key=lambda r: r[1])
    print("done", round(time.time() - t0), "s.  px residual (6000 grid, sutures excluded): median / p90 / init km / blob / unit / n / km-per-px / junctions matched/found")
    for r in rep[:45]: print(f"  {r[0]:6.1f} {r[1]:7.1f} {r[2]:7.1f}  {r[3]:4d} {r[4]} n={r[5]} {r[6]:.2f} j={r[7]}/{r[8]}")
    med = np.array([r[0] for r in rep]); p90 = np.array([r[1] for r in rep]); n = np.array([r[5] for r in rep])
    print("anchors dropped as inconsistent:", sum(B.dropped for B in blobs.values()))
    print("flex stage reached (0 = affine only .. 7 = full):", np.bincount([r[9] for r in rep], minlength=8).tolist())
    print("blobs:", len(rep), "| sample-weighted median", round(float((med * n).sum() / n.sum()), 2), "| blobs with p90 > 10px:", int((p90 > 10).sum()), "| > 25px:", int((p90 > 25).sum()))
    json.dump([list(r) for r in rep], open(os.path.join(WORK, "fit_report.json"), "w"))
