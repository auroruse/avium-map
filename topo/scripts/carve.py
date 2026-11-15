"""Settle the ground under the rivers so each one runs downhill.
The traced rivers already follow the route that climbs least, so what is left is the grain of the elevation data: a pit here,
a bump there. For each network the bed that differs least from the ground and never rises downstream is solved (a linear
programme) and the ground beside it eased by the same amount over a few px. Eivorie's hand-drawn rivers get the same treatment
on their own, since they were never on real valleys. Then a shallow valley is pressed under every river so it reads as one.
height_raw.npy + waterlevel.npy + river_net.pkl -> height.npy, waterlevel_c.npy"""
import sys, time, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.optimize import linprog
from riverflow import network, climb, N
t0 = time.time(); M = 2 * N

def solve(h, up, down, fixed, w=None):
    """Least total change to h such that bed[down] <= bed[up] for every pair; fixed nodes keep their height."""
    m, k = len(h), len(up); w = np.ones(m) if w is None else w
    row = np.r_[np.arange(m), np.arange(m), m + np.arange(m), m + np.arange(m), 2 * m + np.arange(k), 2 * m + np.arange(k)]
    col = np.r_[np.arange(m), m + np.arange(m), np.arange(m), m + np.arange(m), down, up]
    val = np.r_[np.ones(m), -np.ones(m), -np.ones(m), -np.ones(m), np.ones(k), -np.ones(k)]
    A = coo_matrix((val, (row, col)), shape=(2 * m + k, 2 * m)).tocsr(); lo = np.where(fixed, h, np.minimum(h, 0.5)); hi = np.where(fixed, h, np.inf)
    res = linprog(np.r_[np.zeros(m), w], A_ub=A, b_ub=np.r_[h, -h, np.zeros(k)], bounds=np.c_[np.r_[lo, np.zeros(m)], np.r_[hi, np.full(m, np.inf)]], method="highs")
    assert res.status == 0, res.message
    return res.x[:m]

H = np.load(os.path.join(WORK, "height_raw.npy")).astype(np.float32); lev = np.load(os.path.join(WORK, "waterlevel.npy")); land = np.load(os.path.join(WORK, "land12k.npy"))
lev2 = lev.copy()

# ---------------- Eivorie: hand-drawn, fictional rivers on the 6000 grid
eiv = np.load(os.path.join(WORK, "eiv.npy")); riv6 = (read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0) & eiv
if riv6.any():
    SLOPE, WMIN, WMAX, LAKEW = 150.0, 5.0, 25.0, 300.0      # m of change per px of reach (6000 grid); reach limits in px; how much a lake resists moving
    net = network(H, lev, riv6); ys, xs, h, pred, lk = net["y"], net["x"], net["h"], net["pred"], net["lake"]; n = len(h)
    rep = np.arange(n); first = {}
    for i in np.nonzero(lk > 0)[0]: rep[i] = first.setdefault(lk[i], i)
    var = np.unique(rep); vi = -np.ones(n, np.int64); vi[var] = np.arange(len(var)); v = vi[rep]
    e = np.nonzero(pred >= 0)[0]; a, b = v[e], v[pred[e]]; keep = a != b
    bed = solve(h[var].astype(np.float64), a[keep], b[keep], np.zeros(len(var), bool), np.where(lk[var] > 0, LAKEW, 1.0))[v]; delta = bed - h; r = net["riv"]
    print("Eivorie's drawn rivers: %d px | changed by more than 20 m: %.1f%%, 100 m: %.1f%%, 500 m: %.1f%% | %.0f s" % (int(r.sum()), 100 * (np.abs(delta[r]) > 20).mean(), 100 * (np.abs(delta[r]) > 100).mean(), 100 * (np.abs(delta[r]) > 500).mean(), time.time() - t0), flush=True)
    np.savez(os.path.join(WORK, "flow.npz"), y=ys, x=xs, h=h, bed=bed, pred=pred, dist=net["dist"], riv=r, lake=lk)
    D = np.zeros((N, N), np.float32); D[ys, xs] = delta; node = np.zeros((N, N), bool); node[ys, xs] = True
    d, (iy, ix) = ndi.distance_transform_edt(~node, return_indices=True); dl = D[iy, ix]; del iy, ix
    reach = np.clip(np.abs(dl) / SLOPE, WMIN, WMAX); F = dl * (0.5 + 0.5 * np.cos(np.pi * np.minimum(d / reach, 1.0))).astype(np.float32); del d, dl, reach
    Fs = ndi.gaussian_filter(F, 1.5); Fs[ys, xs] = F[ys, xs]; del F
    yy = (np.arange(M) + 0.5) / 2 - 0.5; F12 = ndi.map_coordinates(Fs, np.meshgrid(yy, yy, indexing="ij"), order=1, mode="nearest"); del Fs
    H = np.where(land, np.maximum(H + F12, 0.5), H); del F12
    B = np.full((N, N), np.nan, np.float32); B[ys[lk == 0], xs[lk == 0]] = bed[lk == 0]; B = B.repeat(2, 0).repeat(2, 1)
    H = np.where(land & np.isfinite(B), np.maximum(B, 0.5), H); del B
    L6 = np.zeros((N, N), np.float32); L6[ys[lk > 0], xs[lk > 0]] = delta[lk > 0]; L12 = L6.repeat(2, 0).repeat(2, 1); wl, nw = ndi.label(~land)
    mx = ndi.maximum(L12, wl, np.arange(1, nw + 1)); mn = ndi.minimum(L12, wl, np.arange(1, nw + 1)); sh = np.r_[0, np.where(np.abs(mx) > np.abs(mn), mx, mn)].astype(np.float32)
    lev2 = np.maximum(lev + sh[wl], 0.0); lev2[land] = lev[land]; del wl, L12

# ---------------- the traced rivers, on the 12000 grid
SLOPE, WMIN, WMAX = 60.0, 5.0, 30.0                         # m of change per px of reach; reach limits in px
net = pickle.load(open(os.path.join(WORK, "river_net.pkl"), "rb"))
if len(net["cy"]):
    cy, cx, pred, isl, fixed = net["cy"].astype(np.int64), net["cx"].astype(np.int64), net["pred"], net["isl"], net["fixed"]
    h = np.where(isl, H[cy, cx], lev2[cy, cx]).astype(np.float64); e = np.nonzero(pred >= 0)[0]
    # the sea is fixed; a lake is one unknown, heavy but movable: its level was an estimate and the rivers running into it know better
    wl, nw = ndi.label(~land); ocean = np.bincount(wl.ravel())[1:].argmax() + 1; lid = np.where(isl, 0, wl[cy, cx]); islake = (lid > 0) & (lid != ocean)
    rep = np.arange(len(cy)); first = {}
    for i in np.nonzero(islake)[0]: rep[i] = first.setdefault(int(lid[i]), i)
    var = np.unique(rep); vi = -np.ones(len(cy), np.int64); vi[var] = np.arange(len(var)); v = vi[rep]; a_, b_ = v[e], v[pred[e]]; k_ = a_ != b_
    bed = solve(h[var], a_[k_], b_[k_], (fixed & ~islake)[var], np.where(islake[var], 300.0, 1.0))[v]; delta = (bed - h).astype(np.float32)
    moved = 0
    for l_, i in first.items():
        if abs(delta[i]) > 0.5: lev2[wl == l_] = bed[i]; moved += 1
    print("lakes whose level moved to fit the rivers running into them:", moved, "of", len(first), flush=True); del wl
    a = np.abs(delta[isl])
    print("traced rivers: %d cells | ground under them changed by more than 20 m: %.1f%%, 50 m: %.1f%%, 100 m: %.1f%%, 300 m: %.2f%%, 600 m: %.2f%% | largest %.0f m | cut %.0f%%, raised %.0f%% | %.0f s"
          % (len(cy), 100 * (a > 20).mean(), 100 * (a > 50).mean(), 100 * (a > 100).mean(), 100 * (a > 300).mean(), 100 * (a > 600).mean(), a.max(), 100 * -delta[delta < 0].sum() / max(a.sum(), 1), 100 * delta[delta > 0].sum() / max(a.sum(), 1), time.time() - t0), flush=True)
    D = np.zeros((M, M), np.float32); D[cy[isl], cx[isl]] = delta[isl]; node = np.zeros((M, M), bool); node[cy[isl], cx[isl]] = True
    T, PAD = 3000, 48; moved20 = moved200 = 0
    for y0 in range(0, M, T):
        for x0 in range(0, M, T):
            ya, yb, xa, xb = max(y0 - PAD, 0), min(y0 + T + PAD, M), max(x0 - PAD, 0), min(x0 + T + PAD, M); nd = node[ya:yb, xa:xb]
            if not nd.any(): continue
            d, (iy, ix) = ndi.distance_transform_edt(~nd, return_indices=True); dl = D[ya:yb, xa:xb][iy, ix]
            reach = np.clip(np.abs(dl) / SLOPE, WMIN, WMAX); F = (dl * (0.5 + 0.5 * np.cos(np.pi * np.minimum(d / reach, 1.0)))).astype(np.float32)
            Fs = ndi.gaussian_filter(F, 1.2); Fs[nd] = F[nd]; Fs = Fs[y0 - ya:y0 - ya + T, x0 - xa:x0 - xa + T]; sl = (slice(y0, y0 + T), slice(x0, x0 + T)); lm = land[sl]
            H[sl] = np.where(lm, np.maximum(H[sl] + Fs, 0.5), H[sl]); moved20 += int((np.abs(Fs[lm]) > 20).sum()); moved200 += int((np.abs(Fs[lm]) > 200).sum())
    del D, node
    H[cy[isl], cx[isl]] = np.maximum(bed[isl], 0.5)
    print("ground moved by more than 20 m on %.2f%% of land, more than 200 m on %.3f%%" % (100 * moved20 / land.sum(), 100 * moved200 / land.sum()), flush=True)
np.save(os.path.join(WORK, "waterlevel_c.npy"), lev2.astype(np.float32))
# No canyon is cut off a river mouth: a trench across the shelf or the basin floor is as dark as a river and reads as one drawn out to sea.
# The shelf edge is notched by seafloor.py's own canyon heads.
# a shallow valley under every river so it reads as one
riv = read_png(os.path.join(WORK, "rivers12000.png"))[..., 3] > 128
dd = ndi.distance_transform_edt(~riv).astype(np.float32)
H = np.where(land, np.maximum(H - 30.0 * np.exp(-(dd / 3.5) ** 2), np.minimum(H, 1.0)), H); del dd
np.save(os.path.join(WORK, "height.npy"), np.round(H).astype(np.int16))
# the check: every traced river, cell by cell, on the finished ground
if len(net["cy"]):
    hf = np.where(isl, H[cy, cx], lev2[cy, cx]).astype(np.float64); bar = hf.copy()
    for i in np.argsort(net["order"]):
        if pred[i] >= 0: bar[i] = max(hf[i], bar[pred[i]])
    c = (bar - hf)[isl]
    print("finished ground, river cells that must climb more than 5 m on the way to their mouth: %.2f%%, 20 m: %.2f%%, 50 m: %.3f%%" % (100 * (c > 5).mean(), 100 * (c > 20).mean(), 100 * (c > 50).mean()))
print("done %.0f s" % (time.time() - t0))
