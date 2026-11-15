"""Relax the georeference so the terrain keeps a natural shape.
The overlay squeezes some of the world two- and threefold; followed exactly, real ridges come out as streaks.
This solves for one smooth shift of every map pixel's real position that
  - caps the local stretch at CAP (area kept),
  - moves ground that landed on real sea onto the nearest real shore,
  - leaves the printed cities where they are and the Avium cities nearly so,
  - keeps real neighbours joined along their shared borders.
-> work/relax_d.npy (750x750x3, km, added to the unit-sphere position), work/relax_r.npy (region of each node)"""
import sys, json, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix, identity
from scipy.sparse.linalg import splu
CAP, G, R_E = 1.5, 4, 6371.0
AW = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0     # how hard a printed city holds its ground; the stretch cap must be able to win
t0 = time.time()
own = np.load(os.path.join(WORK, "own.npy")); flon = np.load(os.path.join(WORK, "fwd_lon_raw.npy")); flat = np.load(os.path.join(WORK, "fwd_lat_raw.npy"))
reg2u = np.load(os.path.join(WORK, "reg2u.npy")); real = np.load(os.path.join(WORK, "real_unit.npy"), mmap_mode="r")
R = own[G // 2::G, G // 2::G].copy(); lo = flon[G // 2::G, G // 2::G]; la = flat[G // 2::G, G // 2::G]
valid = (R > 0) & np.isfinite(lo); R[~valid] = 0; n = int(valid.sum()); N = R.shape[0]
def xyz(lo, la):
    lo = np.radians(lo); la = np.radians(la); return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
def lonlat(v):
  with np.errstate(all='ignore'): return np.degrees(np.arctan2(v[..., 1], v[..., 0])), np.degrees(np.arcsin(np.clip(v[..., 2] / np.linalg.norm(v, axis=-1), -1, 1)))
V = np.where(valid[..., None], xyz(lo, la) * R_E, 0.0); V0 = V.copy()
idx = np.full(R.shape, -1); idx[valid] = np.arange(n)
mono = read_png(os.path.join(LAYERS, "mono.png"))[:, :, 0] > 0
aland = mono[G::2 * G, G::2 * G][:N, :N] if False else mono.reshape(N, 2 * G, N, 2 * G).mean(axis=(1, 3)) > 0.5      # Avium land at the node
# real land at 2 arc-minutes and, for every cell, its nearest land cell
rl = np.asarray(real[::2, ::2]) > 0
_, (ry, rx) = ndi.distance_transform_edt(~rl, return_indices=True)
# which unit pairs really share a land border
rs = np.load(os.path.join(WORK, "real_samples.npy")); k = rs[:, 0].astype(np.int64) * 1000 + rs[:, 1].astype(np.int64)
ku, kc = np.unique(k, return_counts=True); realpair = np.zeros(1000 * 1000, bool); realpair[ku[kc >= 30]] = True
U = reg2u[R]
# anchors
aw = np.zeros(R.shape)
lm = np.load(os.path.join(WORK, "landmarks.npy")); av = np.load(os.path.join(WORK, "avium_anchors.npy"))
for rows, w in ((lm, AW), (av, AW / 15)):
    j = np.clip((rows[:, 1] / 2 / G).astype(int), 0, N - 1); i = np.clip((rows[:, 2] / 2 / G).astype(int), 0, N - 1)
    np.maximum.at(aw, (i, j), w)
def jac(V):
    def d(ax):
        a = np.roll(V, -1, ax); b = np.roll(V, 1, ax); ra = np.roll(R, -1, ax) == R; rb = np.roll(R, 1, ax) == R
        return np.where((ra & rb)[..., None], (a - b) / 2, np.where(ra[..., None], a - V, np.where(rb[..., None], V - b, 0.0)))
    return d(1), d(0)
Jx0, Jy0 = jac(V); SIGN = np.sign(np.median((np.cross(Jx0, Jy0) * V).sum(-1)[valid]))
f0 = valid & aland & ((np.cross(Jx0, Jy0) * V).sum(-1) * SIGN <= 0) & (np.linalg.norm(Jx0, axis=-1) > 0) & (np.linalg.norm(Jy0, axis=-1) > 0)
print("before: folded %.2f%% of land" % (100 * f0.sum() / (valid & aland).sum()))
for it in range(16):
    Jx, Jy = jac(V)
    a = (Jx * Jx).sum(-1); b = (Jx * Jy).sum(-1); c = (Jy * Jy).sum(-1)
    tr = a + c; disc = np.sqrt(np.maximum(tr * tr / 4 - (a * c - b * b), 0)); l1 = tr / 2 + disc; l2 = np.maximum(tr / 2 - disc, 1e-9)
    s1 = np.sqrt(l1); s2 = np.sqrt(l2); ratio = s1 / s2
    v1 = np.stack([l1 - c, b], -1); nn = np.linalg.norm(v1, axis=-1); flat_ = nn < 1e-9
    v1 = np.where(flat_[..., None], np.array([1.0, 0.0]), v1 / np.maximum(nn, 1e-12)[..., None]); v2 = np.stack([-v1[..., 1], v1[..., 0]], -1)
    # every node is asked for a sound footprint: stretch no more than CAP, the right way up, and not crushed.
    # A crushed node (two map places a long way apart with almost the same real position) is given back a share of
    # the typical area; it is what makes rivers hop and terrain smear.
    area = s1 * s2; m_ = valid & aland; A_typ = float(np.median(area[m_]))
    nrm = V / np.maximum(np.linalg.norm(V, axis=-1), 1e-9)[..., None]
    orient = (np.cross(Jx, Jy) * nrm).sum(-1) * SIGN
    live = valid & (s1 > 1e-3)
    need = live & ((ratio > CAP) | (area < 0.35 * A_typ) | (orient <= 0))
    A2 = np.maximum(area, 0.35 * A_typ); r2 = np.minimum(np.where(np.isfinite(ratio), ratio, CAP), CAP)
    s1n = np.sqrt(A2 * r2); s2n = np.sqrt(A2 / r2)
    u1 = (Jx * v1[..., 0:1] + Jy * v1[..., 1:2]) / np.maximum(s1, 1e-3)[..., None]
    u1 = u1 - nrm * (u1 * nrm).sum(-1, keepdims=True); u1 /= np.maximum(np.linalg.norm(u1, axis=-1), 1e-9)[..., None]
    u2 = SIGN * np.cross(nrm, u1)
    Tx = np.where(need[..., None], u1 * (s1n * v1[..., 0])[..., None] + u2 * (s2n * v2[..., 0])[..., None], Jx)
    Ty = np.where(need[..., None], u1 * (s1n * v1[..., 1])[..., None] + u2 * (s2n * v2[..., 1])[..., None], Jy)
    crushed = m_ & (area < 0.2 * A_typ)
    I, J, W_, B = [], [], [], []
    def edges(p, q, t, w):
        ip, iq = idx[p], idx[q]
        I.extend([ip, ip, iq, iq]); J.extend([ip, iq, ip, iq]); W_.extend([w, -w, -w, w]); B.append((ip, -w[:, None] * t)); B.append((iq, w[:, None] * t))
    for ax, T in ((1, Tx), (0, Ty)):
        sl_p = (slice(None), slice(0, -1)) if ax == 1 else (slice(0, -1), slice(None)); sl_q = (slice(None), slice(1, None)) if ax == 1 else (slice(1, None), slice(None))
        vp, vq = valid[sl_p], valid[sl_q]; same = vp & vq & (R[sl_p] == R[sl_q])
        pi = np.nonzero(same); p = tuple(x + (sl_p[k].start or 0) for k, x in enumerate(pi)); q = tuple(x + (sl_q[k].start or 0) for k, x in enumerate(pi))
        t = 0.5 * (T[p] + T[q]) - (V[q] - V[p]); edges(p, q, t, np.ones(len(pi[0])))
        nb = vp & vq & (R[sl_p] != R[sl_q]) & realpair[U[sl_p].astype(np.int64) * 1000 + U[sl_q]] & (np.linalg.norm(V[sl_q] - V[sl_p], axis=-1) < 150)
        pi = np.nonzero(nb); p = tuple(x + (sl_p[k].start or 0) for k, x in enumerate(pi)); q = tuple(x + (sl_q[k].start or 0) for k, x in enumerate(pi))
        edges(p, q, np.zeros((len(pi[0]), 3)), np.ones(len(pi[0])))
    diag = np.full(n, 2e-4); rhs = np.zeros((n, 3))
    diag += aw[valid]                                               # cities stay put
    # ground on real sea: wanted shift = to the nearest real shore and 8 km past it
    lo_, la_ = lonlat(V); lo_ = np.nan_to_num(lo_); la_ = np.nan_to_num(la_); ci = np.clip(((90 - la_) * 30).astype(int), 0, 5399); cj = np.clip(((lo_ + 180) * 30).astype(int), 0, 10799)
    sea = valid & aland & ~rl[ci, cj]
    cl = -180 + (rx[ci, cj] + 0.5) / 30.0; ca = 90 - (ry[ci, cj] + 0.5) / 30.0
    tgt = xyz(cl, ca) * R_E - V; dn = np.linalg.norm(tgt, axis=-1); tgt = tgt * (1 + 8.0 / np.maximum(dn, 1.0))[..., None]
    wc = 0.6; diag[idx[sea]] += wc; rhs[idx[sea]] += wc * tgt[sea]
    for ip, val in B: np.add.at(rhs, ip, val)
    A = coo_matrix((np.concatenate(W_), (np.concatenate(I), np.concatenate(J))), shape=(n, n)).tocsc() + identity(n, format="csc").multiply(diag)
    lu = splu(A.tocsc()); d = np.stack([lu.solve(rhs[:, k]) for k in range(3)], 1)
    V[valid] += d; V[valid] *= (R_E / np.linalg.norm(V[valid], axis=-1))[:, None]
    m = valid & aland
    Jx2, Jy2 = jac(V); fold = m & ((np.cross(Jx2, Jy2) * V).sum(-1) * SIGN <= 0) & (np.linalg.norm(Jx2, axis=-1) > 0) & (np.linalg.norm(Jy2, axis=-1) > 0)
    print(f"round {it}: crushed {100*crushed.sum()/m.sum():.2f}% | folded {100*fold.sum()/m.sum():.2f}% | stretch over {CAP}: {100*(ratio[m] > CAP).mean():.0f}% of land, over 2: {100*(ratio[m] > 2).mean():.0f}%, over 3: {100*(ratio[m] > 3).mean():.1f}% | on real sea {100*sea.sum()/m.sum():.1f}% | shift this round median {np.median(np.linalg.norm(d, axis=1)):.0f} km, max {np.linalg.norm(d, axis=1).max():.0f} | {time.time()-t0:.0f}s", flush=True)
D = np.where(valid[..., None], V - V0, 0).astype(np.float32)
np.save(os.path.join(WORK, "relax_d.npy"), D); np.save(os.path.join(WORK, "relax_r.npy"), R.astype(np.int32))
sh = np.linalg.norm(D[valid & aland], axis=-1)
ca = np.linalg.norm(D[np.clip((lm[:, 2] / 2 / G).astype(int), 0, N - 1), np.clip((lm[:, 1] / 2 / G).astype(int), 0, N - 1)], axis=-1)
print("printed cities moved, km: median %.0f | p90 %.0f | max %.0f" % (np.median(ca), np.percentile(ca, 90), ca.max()))
print("total shift on Avium land, km: median %.0f | p90 %.0f | p99 %.0f | max %.0f" % (np.median(sh), np.percentile(sh, 90), np.percentile(sh, 99), sh.max()))
