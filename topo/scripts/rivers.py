"""Real rivers (Natural Earth) pushed through the inverse of the warps onto the Avium grid.
-> work/fwd_lon.npy, fwd_lat.npy (3000 grid), work/river_lines.pkl (rank, name, Nx2 xy on the 6000 grid)"""
import sys, json, pickle, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import shapefile
t0 = time.time()
own = np.load(os.path.join(WORK, "own.npy")); warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
reg2u = np.load(os.path.join(WORK, "reg2u.npy")); real = np.load(os.path.join(WORK, "real_unit.npy"))
flon = np.full(own.shape, np.nan, np.float32); flat = np.full(own.shape, np.nan, np.float32)
objs = ndi.find_objects(own); RX = Relax(WORK)
for b, W in warps.items():
    sl = objs[b - 1]
    if sl is None: continue
    yy, xx = np.nonzero(own[sl] == b); yy += sl[0].start; xx += sl[1].start
    lo, la = W(2 * xx + 1.0, 2 * yy + 1.0)
    lo, la = Relax.apply(RX.region(b), lo, la, 2 * xx + 1.0, 2 * yy + 1.0)
    flon[yy, xx] = lo; flat[yy, xx] = la
np.save(os.path.join(WORK, "fwd_lon.npy"), flon); np.save(os.path.join(WORK, "fwd_lat.npy"), flat)
def xyz(lon, lat):
    lo = np.radians(lon); la = np.radians(lat)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
V = np.full(own.shape + (3,), np.nan, np.float32)
ok = own > 0
V[ok] = xyz(flon[ok], flat[ok])
ii, jj = np.nonzero(ok); P = V[ii, jj].astype(np.float64); U = reg2u[own[ii, jj]]
gtree = cKDTree(P)
order = np.argsort(U, kind="stable"); us, st = np.unique(U[order], return_index=True); st = list(st) + [len(order)]
utree = {}; rtree = {}
def tree_for(u):
    if u not in utree:
        k = np.searchsorted(us, u)
        if k >= len(us) or us[k] != u: utree[u] = None
        else:
            idx = order[st[k]:st[k + 1]]; utree[u] = (cKDTree(P[idx]), idx)
    return utree[u]
print("forward grid", len(P), "px", round(time.time() - t0), "s")

def invert(lon, lat, steady=False):
    """lon/lat arrays -> x,y on the 6000 grid (nan where the place is not on the map)"""
    t = xyz(lon, lat).astype(np.float64); n = len(t)
    r = np.clip(((90 - lat) * 60).astype(int), 0, 10799); c = np.clip(((lon + 180) * 60).astype(int), 0, 21599)
    u = np.asarray(real[r, c])
    if steady and n > 3:
        # a river that follows a border flips country at every bend; keep it with whichever side it is mostly on
        # over each ~80 km, so one warp places the whole stretch
        from scipy.ndimage import uniform_filter1d
        us = np.unique(u[u > 0])
        if len(us) > 1:
            sc = np.stack([uniform_filter1d((u == k).astype(np.float32), 81, mode="nearest") for k in us])
            u = us[sc.argmax(0)]
        elif len(us) == 1: u = np.full(n, us[0])
    best = np.full(n, -1); bd = np.full(n, 9.0)
    for uu in np.unique(u):
        if uu <= 0: continue
        tr = tree_for(int(uu))
        if tr is None: continue
        m = np.nonzero(u == uu)[0]
        d, k = tr[0].query(t[m]); best[m] = tr[1][k]; bd[m] = d
    far = bd > 40 / 6371.0                                # not found in its own country: take whatever is nearest
    if far.any():
        d, k = gtree.query(t[far]); fi = np.nonzero(far)[0]
        better = d < bd[fi]; best[fi[better]] = k[better]; bd[fi[better]] = d[better]
    if steady and n > 3:
        # the same for regions: where two map areas answer for the same real ground, a river must not hop between them
        from scipy.ndimage import uniform_filter1d
        rg = np.where(best >= 0, own[ii[np.maximum(best, 0)], jj[np.maximum(best, 0)]], 0); rs_ = np.unique(rg[rg > 0])
        if len(rs_) > 1:
            sc = np.stack([uniform_filter1d((rg == k).astype(np.float32), 81, mode="nearest") for k in rs_]); want = rs_[sc.argmax(0)]
            for k in rs_:
                m = np.nonzero((want == k) & (rg != k))[0]
                if not len(m): continue
                if k not in rtree:
                    sel = np.nonzero(own[ii, jj] == k)[0]; rtree[k] = (cKDTree(P[sel]), sel)
                d, q = rtree[k][0].query(t[m]); okk = d < bd[m] + 30 / 6371.0
                best[m[okk]] = rtree[k][1][q[okk]]; bd[m[okk]] = d[okk]
    good = bd < 45 / 6371.0
    x = np.full(n, np.nan); y = np.full(n, np.nan)
    g = np.nonzero(good)[0]
    i = ii[best[g]]; j = jj[best[g]]; o = own[i, j]
    def diff(di, dj):
        i1 = np.clip(i + di, 0, 2999); j1 = np.clip(j + dj, 0, 2999); i0 = np.clip(i - di, 0, 2999); j0 = np.clip(j - dj, 0, 2999)
        a = V[i1, j1].astype(np.float64); b = V[i0, j0].astype(np.float64); c0 = V[i, j].astype(np.float64)
        va = (own[i1, j1] == o); vb = (own[i0, j0] == o)
        out = np.where((va & vb)[:, None], (a - b) / 2, np.where(va[:, None], a - c0, np.where(vb[:, None], c0 - b, 0)))
        return out
    qx = diff(0, 1); qy = diff(1, 0); d = t[g] - V[i, j].astype(np.float64)
    a11 = (qx * qx).sum(1); a12 = (qx * qy).sum(1); a22 = (qy * qy).sum(1); b1 = (qx * d).sum(1); b2 = (qy * d).sum(1)
    det = a11 * a22 - a12 * a12; okd = det > 1e-18
    aa = np.where(okd, (b1 * a22 - b2 * a12) / np.where(okd, det, 1), 0); bb = np.where(okd, (a11 * b2 - a12 * b1) / np.where(okd, det, 1), 0)
    aa = np.clip(aa, -2, 2); bb = np.clip(bb, -2, 2)
    x[g] = 2 * (j + aa) + 1; y[g] = 2 * (i + bb) + 1
    if steady:
        # where real ground is crushed on the map, places far apart on the map answer for almost the same real spot and
        # the nearest one flips from vertex to vertex. A vertex that would hop takes instead the candidate that carries
        # the line on from the vertex before it.
        for k in range(1, n):
            if np.isnan(x[k]) or np.isnan(x[k - 1]) or np.hypot(x[k] - x[k - 1], y[k] - y[k - 1]) <= 5: continue
            tr = tree_for(int(u[k])) if u[k] > 0 else None
            if tr is None: continue
            cand = tr[0].query_ball_point(t[k], bd[k] + 15 / 6371.0)
            if not cand: continue
            c = tr[1][np.array(cand)]; cx = 2.0 * jj[c] + 1; cy = 2.0 * ii[c] + 1
            q = np.hypot(cx - x[k - 1], cy - y[k - 1]).argmin()
            if np.hypot(cx[q] - x[k - 1], cy[q] - y[k - 1]) < np.hypot(x[k] - x[k - 1], y[k] - y[k - 1]): x[k], y[k] = cx[q], cy[q]
    return x, y

if __name__ == "__main__":
    r = shapefile.Reader(os.path.join(DATA, "ne_rivers", "ne_10m_rivers_lake_centerlines"), encoding="utf-8")
    f = [x[0] for x in r.fields[1:]]; ir = f.index("scalerank"); iname = f.index("name"); ic = f.index("featurecla")
    lines = []; nv = 0
    for sr in r.iterShapeRecords():
        if sr.record[ic] == "Canal": continue
        pts = np.array(sr.shape.points); parts = list(sr.shape.parts) + [len(pts)]
        for a, b in zip(parts[:-1], parts[1:]):
            p = pts[a:b]
            if len(p) < 2: continue
            # densify to <= ~1 km
            seg = np.hypot(np.diff(p[:, 0]) * np.cos(np.radians(p[:-1, 1])), np.diff(p[:, 1])) * 111.0
            k = np.maximum(np.ceil(seg / 1.0).astype(int), 1)
            tt = np.concatenate([np.arange(kk) / kk + s for s, kk in enumerate(k)] + [[len(p) - 1.0]])
            lo = np.interp(tt, np.arange(len(p)), p[:, 0]); la = np.interp(tt, np.arange(len(p)), p[:, 1])
            x, y = invert(lo, la, steady=True); nv += len(x)
            # split where the river leaves the map or jumps across a suture
            bad = np.isnan(x); jump = np.zeros(len(x), bool); jump[1:] = np.hypot(np.diff(x), np.diff(y)) > 16
            start = 0
            for e in list(np.nonzero(bad | jump)[0]) + [len(x)]:
                if e - start >= 2: lines.append((int(sr.record[ir]), sr.record[iname], np.stack([x[start:e], y[start:e]], 1)))
                start = e + 1 if (e < len(x) and bad[e]) else e
    pickle.dump(lines, open(os.path.join(WORK, "river_lines.pkl"), "wb"))
    tot = sum(len(l[2]) for l in lines)
    print("rivers:", len(lines), "pieces,", tot, "of", nv, "vertices placed", round(time.time() - t0), "s")
