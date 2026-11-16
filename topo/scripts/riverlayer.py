"""The rivers layer: real rivers, laid in the valleys of the Avium terrain.
Each Natural Earth river arrives through the warps a few km off its valley. It is re-traced on the terrain, cell by cell, from its
upper end down: inside a corridor round the warped line, along the route that climbs least and keeps to the valley floor. A trace
stops the moment it meets the sea, a lake or a river already traced, so rivers join and never cross, loop or run double.
Big rivers go first. Ends left in mid-air are led downhill to water if that needs no climb, short ones are dropped.
Eivorie's rivers are fictional: the hand-drawn ones are kept there and nothing real is traced.
GENERATED = False keeps the hand-drawn layer everywhere and traces nothing.
-> work/river_net.pkl (the traced network: every cell and the cell it drains to), work/rivers_final.pkl (smoothed lines, 6000 grid), work/rivers12000.png, work/eiv.npy
riverlayer.py x0,y0,x1,y1  traces only that box (6000 grid) and writes work/rivtest.png instead"""
import sys, pickle, time, csv, heapq; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components
t0 = time.time(); M = 12000
GENERATED = True
W, CHUNK, HOP, MINLEN = 10, 300, 80, 80          # corridor half-width, trace chunk, longest hop bridged, shortest river kept: px on the 12000 grid
BOX = [int(v) * 2 for v in sys.argv[1].split(",")] if len(sys.argv) > 1 else None

H = np.load(os.path.join(WORK, "height_raw.npy")).astype(np.float32); land = np.load(os.path.join(WORK, "land12k.npy"))
Hw = np.where(land, H, np.load(os.path.join(WORK, "waterlevel.npy"))); del H              # water cells carry their surface level
relh = Hw - ndi.minimum_filter(Hw, 17)                                                    # height above the local valley floor
drawn = read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0
bord = read_png(os.path.join(LAYERS, "borders.PNG")); eiv = np.zeros((6000, 6000), bool); cols = {}
for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t"):
    if r["KIND"] == "city" and r["NATION"] == "Eivorie" and r["X"]:
        x, y = int(float(r["X"])), int(float(r["Y"]))
        if bord[y, x, 3] > 200: cols.setdefault(tuple(int(v) for v in bord[y, x, :3]), []).append((y, x))
for c, pts in cols.items():
    lab, _ = ndi.label((np.abs(bord[..., :3].astype(int) - np.array(c)).max(-1) <= 3) & (bord[..., 3] > 200))
    eiv |= np.isin(lab, list({int(lab[y, x]) for y, x in pts} - {0}))
eiv = ndi.binary_dilation(eiv, iterations=8); del bord
if not GENERATED: eiv[:] = True
np.save(os.path.join(WORK, "eiv.npy"), eiv)
eiv12 = eiv.repeat(2, 0).repeat(2, 1); keptdrawn = (drawn & eiv).repeat(2, 0).repeat(2, 1)
occ = np.zeros((M, M), np.int32); occ[keptdrawn & land] = -1                               # which river holds each cell; -1 is a kept drawn river

# ---------------- the real lines, cut into land runs that point downhill
src = "river_lines_adj.pkl" if os.path.exists(os.path.join(WORK, "river_lines_adj.pkl")) else "river_lines.pkl"
lines = pickle.load(open(os.path.join(WORK, src), "rb")) if GENERATED else []
Hmin = None
def dense(p):
    s = np.r_[0, np.cumsum(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])))]; k = int(max(s[-1], 1)) + 1; t = np.linspace(0, s[-1], k)
    return np.c_[np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])]
pieces = []
for rank, name, xy in lines:
    p = np.asarray(xy, float) * 2 + 0.5
    if BOX and not ((p[:, 0] > BOX[0] - 300) & (p[:, 0] < BOX[2] + 300) & (p[:, 1] > BOX[1] - 300) & (p[:, 1] < BOX[3] + 300)).any(): continue
    seg = np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])); cut = [0] + list(np.nonzero(seg > HOP)[0] + 1) + [len(p)]
    for a, b in zip(cut[:-1], cut[1:]):
        if b - a < 2: continue
        q = dense(p[a:b]); xi = np.round(q[:, 0]).astype(int); yi = np.round(q[:, 1]).astype(int)
        inside = (xi >= 0) & (xi < M) & (yi >= 0) & (yi < M); xc, yc = np.clip(xi, 0, M - 1), np.clip(yi, 0, M - 1)
        ok = inside & land[yc, xc] & ~eiv12[yc, xc]; wat = inside & ~land[yc, xc]
        ok = ndi.binary_closing(np.r_[True, ok, True], np.ones(7))[1:-1] & inside & ~eiv12[yc, xc]     # a few px over a lake edge do not break a river
        e = np.nonzero(np.diff(np.r_[0, ok.astype(int), 0]))[0]
        for s0, s1 in zip(e[::2], e[1::2]):
            if s1 - s0 < 14: continue
            r = q[s0:s1]; n = max(len(r) // 8, 3)                                             # which end is lower decides the direction; a lake at the top is a source
            h0, h1 = np.median(Hw[yc[s0:s0 + n], xc[s0:s0 + n]]), np.median(Hw[yc[s1 - n:s1], xc[s1 - n:s1]])
            pieces.append(dict(rank=int(rank), name=name, pts=r[::-1].copy() if h0 < h1 - 3 else r))
pieces.sort(key=lambda d: (d["rank"], -len(d["pts"])))
print("real river runs to trace:", len(pieces), "from", src, "| %.0f s" % (time.time() - t0), flush=True)

# cities that stood on a drawn river hold it: near one, the trace keeps tight to the line, which the calibration ran through the city
dd_ = ndi.distance_transform_edt(~drawn); cm = np.ones((M, M), bool)
for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t"):
    if r["KIND"] == "city" and r["X"]:
        x, y = int(float(r["X"])), int(float(r["Y"]))
        if dd_[y, x] <= 4 and not eiv[y, x]: cm[min(2 * y + 1, M - 1), min(2 * x + 1, M - 1)] = False
stick = (1.0 + 12.0 * np.clip(1.0 - ndi.distance_transform_edt(cm) / 24.0, 0, 1)).astype(np.float32); del dd_, cm

# ---------------- tracing
OFF = [(0, 1, 1.0), (1, 0, 1.0), (0, -1, 1.0), (-1, 0, 1.0), (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
def route(pts, start, w, last, rem, me=0, free=False, avoid=0, ban=(), eager=False):
    """One chunk. pts: the guide line; start: (y, x) cell to leave from, or None; last: this is the river's final chunk;
    rem: guide length still to come after this chunk. -> cells [(y, x)...], kind 'water' | 'river' | 'end' | 'stuck'"""
    xi = np.round(pts[:, 0]).astype(int); yi = np.round(pts[:, 1]).astype(int)
    x0, x1, y0, y1 = max(xi.min() - w - 2, 0), min(xi.max() + w + 3, M), max(yi.min() - w - 2, 0), min(yi.max() + w + 3, M)
    if start is not None: x0, x1, y0, y1 = min(x0, max(start[1] - 2, 0)), max(x1, min(start[1] + 3, M)), min(y0, max(start[0] - 2, 0)), max(y1, min(start[0] + 3, M))
    hh, ww = y1 - y0, x1 - x0; line = np.zeros((hh, ww), bool); al = np.zeros((hh, ww), np.int32)
    ok = (xi >= x0) & (xi < x1) & (yi >= y0) & (yi < y1); line[yi[ok] - y0, xi[ok] - x0] = True; al[yi[ok] - y0, xi[ok] - x0] = np.nonzero(ok)[0]
    d, (iy, ix) = ndi.distance_transform_edt(~line, return_indices=True); along = al[iy, ix]; n = len(pts)
    L = land[y0:y1, x0:x1]; O = occ[y0:y1, x0:x1]; hw = Hw[y0:y1, x0:x1]; rh = relh[y0:y1, x0:x1]
    inC = d <= w
    if start is None:
        yy, xx = np.nonzero(inC & L & (along <= 4) & (d <= 8)); o = O[yy, xx] != 0
        if len(yy) == 0: return [], "stuck", 0
        if o.any(): k = np.nonzero(o)[0][np.argmin(d[yy[o], xx[o]])]                         # carry on from a river that ends here
        else: k = np.argmin(hw[yy, xx] + 4 * d[yy, xx])
        sy, sx = int(yy[k]), int(xx[k])
    else: sy, sx = start[0] - y0, start[1] - x0; inC[sy, sx] = True
    if avoid == 0 and O[sy, sx] not in (0, me): avoid = int(O[sy, sx])                        # the river it carries on from: never run back into that one
    gy, gx = np.ogrid[:hh, :ww]; zone = ((gy - sy) ** 2 + (gx - sx) ** 2 <= 49) & (not free) & (not eager)      # a guided trace ignores what lies round its own start
    other = (O != 0) & (O != me) & (O != avoid)
    if len(ban): other &= ~np.isin(O, ban)                                                    # its own network is no way out, but may be crossed
    if other.any(): dO, (jy, jx) = ndi.distance_transform_edt(~other, return_indices=True)
    else: dO = np.full((hh, ww), 99.0); jy = jx = None
    term = inC & (~L | ((dO <= 2.5) & ~zone))                                                 # water, or within reach of another river: the trace ends there and joins it
    node = inC & (L | term)
    if avoid: node &= O != avoid
    node[sy, sx] = True; term[sy, sx] = False
    near = np.where((dO <= 6) & ~term & ~zone, 2.0, 0.0)                                      # no creeping alongside another river: join it or keep clear
    idx = -np.ones((hh, ww), np.int64); ny, nx = np.nonzero(node); idx[ny, nx] = np.arange(len(ny)); I, J, C = [], [], []
    go = ~term[ny, nx]
    for dy, dx, ln in OFF:
        y2, x2 = ny + dy, nx + dx; m = go & (y2 >= 0) & (y2 < hh) & (x2 >= 0) & (x2 < ww); y2c, x2c = np.clip(y2, 0, hh - 1), np.clip(x2, 0, ww - 1); j = idx[y2c, x2c]; m &= j >= 0
        u = np.nonzero(m)[0]; vy, vx = y2c[m], x2c[m]
        c = ln * ((0.03 if free else 0.005 + 0.02 * d[vy, vx] * stick[y0:y1, x0:x1][vy, vx]) + 0.01 * np.maximum(rh[vy, vx], 0)) + np.where(L[vy, vx], np.maximum(hw[vy, vx] - hw[ny[u], nx[u]], 0), 0.0) + near[vy, vx]         # a lake's level is an estimate: running into one is never a climb
        I.append(u); J.append(j[m]); C.append(c)
    G = coo_matrix((np.concatenate(C), (np.concatenate(I), np.concatenate(J))), shape=(len(ny), len(ny))).tocsr()
    dist, pred = dijkstra(G, directed=True, indices=int(idx[sy, sx]), return_predecessors=True)
    tn = term[ny, nx]; fin = np.isfinite(dist); cost = np.full(len(ny), np.inf)
    cost[tn & fin] = dist[tn & fin] + (0.0 if free or eager else 0.15 * (rem + n - 1 - along[ny, nx][tn & fin]))     # joining early costs a little: the rest of the guide goes unused
    if not free:
        ez = fin & ~tn & (along[ny, nx] >= n - 5) & (d[ny, nx] <= 3)
        cost[ez] = np.minimum(cost[ez], dist[ez] + (25.0 if last else 0.0))
    if not np.isfinite(cost).any():
        if free: return [], "stuck", avoid
        r = fin & ~tn; k = np.nonzero(r)[0][np.lexsort((dist[r], -along[ny, nx][r]))[0]]; kind = "stuck"
    else: k = int(np.argmin(cost)); kind = ("water" if not L[ny[k], nx[k]] else "river") if tn[k] else "end"
    out = []; k0 = k
    while k >= 0: out.append((int(ny[k]) + y0, int(nx[k]) + x0)); k = pred[k] if pred[k] >= 0 else -1
    out = out[::-1]
    if kind == "river" and not other[ny[k0], nx[k0]]: out.append((int(jy[ny[k0], nx[k0]]) + y0, int(jx[ny[k0], nx[k0]]) + x0))      # the last step onto the river it joins
    return out, kind, avoid

def trace(pts, me=0, w=W, ban=(), eager=False):
    cells = []; start = None; kind = "end"; avoid = -9 if eager else 0                        # an onward route may cross the river it leaves from
    for a in range(0, len(pts) - 1, CHUNK):
        b = min(a + CHUNK + 1, len(pts)); last = b >= len(pts)
        if len(pts) - b < 40: b = len(pts); last = True
        c, kind, avoid = route(pts[a:b], start, w, last, len(pts) - b, me, avoid=avoid, ban=ban, eager=eager)
        if not c: kind = "stuck"; break
        cells += c if not cells else c[1:]; start = cells[-1]
        if kind != "end" or last: break
    return cells, kind
def hof(cells): c = np.asarray(cells); return Hw[c[:, 0], c[:, 1]]
def climbof(cells): return float(np.maximum(np.diff(hof(cells)), 0).sum()) if len(cells) > 1 else 0.0
def barrier(cells):
    if len(cells) < 2: return 0.0
    h = hof(cells); return float((np.maximum.accumulate(h[::-1])[::-1] - h).max())

paths = []; flipped = widened = headcut = 0
def lay(pc, fixed=False, ban=(), eager=False, minc=8):
    global flipped, widened, headcut
    me = len(paths) + 1
    pts = pc["pts"]; cells, kind = trace(pts, me, W, ban, eager)
    if not fixed and len(cells) >= 8 and barrier(cells) > 120:                                              # read the wrong way round? try the other
        c2, k2 = trace(pts[::-1].copy(), me, W, ban, eager)
        if len(c2) >= 8 and climbof(c2) < 0.6 * climbof(cells): cells, kind, pts = c2, k2, pts[::-1].copy(); flipped += 1
    if len(cells) >= 8 and barrier(cells) > 150:                                              # the valley lies further from the line than the corridor reaches
        c2, k2 = trace(pts, me, 26, ban, eager)
        if len(c2) >= 8 and barrier(c2) < 0.7 * barrier(cells) and (not fixed or k2 in ("water", "river")): cells, kind = c2, k2; widened += 1
    seen = {}; out = []                                                                       # a trace never crosses itself
    for cell in cells:
        if cell in seen: del out[seen[cell] + 1:]; seen = {q: n for n, q in enumerate(out)}
        else: seen[cell] = len(out); out.append(cell)
    if len(out) < minc: return
    c = np.array(out); son = int(occ[c[0, 0], c[0, 1]])
    own = occ[c[:, 0], c[:, 1]] == 0; own &= land[c[:, 0], c[:, 1]]; occ[c[own, 0], c[own, 1]] = me
    paths.append(dict(rank=pc["rank"], name=pc["name"], cells=c, kind=kind, to=int(occ[c[-1, 0], c[-1, 1]]) if kind == "river" else 0, alive=True, son=son))
for pc in pieces:
    lay(pc)
    if len(paths) % 400 == 0: print("  traced", len(paths), "| %.0f s" % (time.time() - t0), flush=True)
nreal = len(paths)

# ---------------- drawn rivers with no real river beside them: the same tracing, with the drawn line as the guide
def spine(mask):
    """The longest line through a blob of drawn river: farthest point from anywhere, then farthest from that."""
    ys_, xs_ = np.nonzero(mask); idx = -np.ones(mask.shape, np.int64); idx[ys_, xs_] = np.arange(len(ys_)); I, J, C = [], [], []
    for dy, dx, ln in OFF[:2] + OFF[4:6]:
        y2, x2 = ys_ + dy, xs_ + dx; ok = (y2 >= 0) & (y2 < mask.shape[0]) & (x2 >= 0) & (x2 < mask.shape[1]); j = np.where(ok, idx[np.clip(y2, 0, mask.shape[0] - 1), np.clip(x2, 0, mask.shape[1] - 1)], -1); ok &= j >= 0
        I.append(np.nonzero(ok)[0]); J.append(j[ok]); C.append(np.full(int(ok.sum()), ln))
    G = coo_matrix((np.concatenate(C), (np.concatenate(I), np.concatenate(J))), shape=(len(ys_), len(ys_))).tocsr()
    d0 = dijkstra(G, directed=False, indices=0); d0[~np.isfinite(d0)] = -1; A = int(np.argmax(d0))
    dA, pred = dijkstra(G, directed=False, indices=A, return_predecessors=True); dA[~np.isfinite(dA)] = -1; k = int(np.argmax(dA)); ln = float(dA[k]); out = []
    while k >= 0: out.append((ys_[k], xs_[k])); k = pred[k] if pred[k] >= 0 else -1
    return np.array(out), ln
def drawn_pass():
    """Drawn rivers (outside Eivorie) with no traced river beside them: traced with the drawn line as the guide. -> how many"""
    if not GENERATED or BOX: return 0
    made = 0
    far = ndi.distance_transform_edt((occ > 0).reshape(6000, 2, 6000, 2).max((1, 3)) == 0) > 12        # more than 12 px (6000 grid) from every traced river
    lab, nl = ndi.label(drawn & ~eiv & far, structure=np.ones((3, 3)))
    for i, sl in enumerate(ndi.find_objects(lab), 1):
        m = lab[sl] == i
        for _ in range(8):                                                                    # the main line, then any branches left over
            if m.sum() < 80: break
            o, ln = spine(m)
            if ln < 30: break
            g = np.c_[(o[:, 1] + sl[1].start) * 2 + 1.0, (o[:, 0] + sl[0].start) * 2 + 1.0]; g = dense(ndi.gaussian_filter1d(g, 3.0, axis=0, mode="nearest"))
            xi, yi = np.clip(np.round(g[:, 0]).astype(int), 0, M - 1), np.clip(np.round(g[:, 1]).astype(int), 0, M - 1); n = max(len(g) // 8, 3)
            h0, h1 = np.median(Hw[yi[:n], xi[:n]]), np.median(Hw[yi[-n:], xi[-n:]]); k = len(paths)
            lay(dict(rank=6, name="(drawn)", pts=g[::-1].copy() if h0 < h1 - 3 else g)); made += len(paths) - k
            on = np.zeros(m.shape, bool); on[o[:, 0], o[:, 1]] = True; m = m & (ndi.distance_transform_edt(~on) > 6)
    return made
ndrawn = drawn_pass()
print("traced:", nreal, "real rivers and", ndrawn, "drawn rivers that have no real one beside them | turned round:", flipped, "| corridor widened:", widened, "| %.0f s" % (time.time() - t0), flush=True)
# a river that carries on from another: the upper one ends exactly where the lower one begins
stitched = 0
for j, q in sorted(enumerate(paths, 1), key=lambda t: -t[0]):
    k = q["son"]
    if k <= 0 or k == j: continue
    p = paths[k - 1]
    if p["kind"] in ("water", "river"): continue
    at = np.nonzero((p["cells"][:, 0] == q["cells"][0, 0]) & (p["cells"][:, 1] == q["cells"][0, 1]))[0]
    if len(at) and len(p["cells"]) - 1 - at[-1] <= max(30, 0.25 * len(p["cells"])):           # only a short overshoot is cut off; a river that merely starts where another starts is left whole
        p["cells"] = p["cells"][:at[-1] + 1]; p["kind"], p["to"] = "river", j; stitched += 1

# ---------------- ends left in mid-air
loose = lambda p: p["kind"] not in ("water", "river")
def beside(i, p, r=2):
    """The river whose line passes the end of this one (its number), or 0. One that itself stops at this spot does not count."""
    e = p["cells"][-1]; o = occ[max(e[0] - r, 0):e[0] + r + 1, max(e[1] - r, 0):e[1] + r + 1]
    for t in np.unique(o[(o != 0) & (o != i)]).tolist():
        if t < 0: return t
        q = paths[t - 1]; dq = np.abs(q["cells"] - e).max(1); k = int(np.argmin(dq))
        if dq[k] > r + 1 or (q["kind"] == "river" and q["to"] == i) or (loose(q) and k >= len(q["cells"]) - 4): continue
        return t
    return 0
def around(c, me, r=2):
    o = occ[max(c[0] - r, 0):c[0] + r + 1, max(c[1] - r, 0):c[1] + r + 1]; o = o[(o != 0) & (o != me)]
    return int(o[0]) if len(o) else 0
led = 0
def settle(first=1):
    """Ends left in mid-air, from river number `first` on: join the river beside them, else run downhill to water, else end inland."""
    global led
    for rnd in (0, 1):
        for i, p in enumerate(paths, 1):
            if i >= first and loose(p):
                t = beside(i, p)
                if t: p["kind"], p["to"] = "river", t
    for i, p in enumerate(paths, 1):
        if i < first or not loose(p): continue
        up_ = {i}; grew = True                                                                    # the rivers that already run into this one are no way out of it
        while grew:
            grew = False
            for j, q in enumerate(paths, 1):
                if j not in up_ and q["kind"] == "river" and q["to"] in up_: up_.add(j); grew = True
        e = tuple(int(v) for v in p["cells"][-1]); c, kind, _ = route(np.array([[e[1], e[0]]], float), e, 70, True, 0, i, free=True, avoid=-9, ban=sorted(up_ - {i}))       # is there water or a river downhill of here?
        cb = climbof(c)                                                                           # no climb as a rule; a short last step to water may cross what the elevation data cannot resolve
        if kind in ("water", "river") and ((len(c) <= 110 and cb <= 30) or (len(c) <= 25 and cb <= 80) or (kind == "water" and len(c) <= 70 and cb <= 150)):
            c = np.array(c); own = (occ[c[:, 0], c[:, 1]] == 0) & land[c[:, 0], c[:, 1]]; t = int(occ[c[-1, 0], c[-1, 1]]) if kind == "river" else 0
            occ[c[own, 0], c[own, 1]] = i; p["cells"] = np.r_[p["cells"], c[1:]]; p["kind"], p["to"] = kind, t; led += 1
        else:
            p["kind"] = "inland"; h = ndi.gaussian_filter1d(hof(p["cells"]), 1.5, mode="nearest"); k = int(np.argmin(h))            # it ends where the ground stops falling
            last = set(map(tuple, p["cells"][k + 1:].tolist())); used = any(tuple(q["cells"][-1].tolist()) in last or tuple(q["cells"][0].tolist()) in last for q in paths if q is not p)
            if k >= 0.5 * len(h) and h[-1] - h[k] > 20 and not used: p["cells"] = p["cells"][:k + 1]
settle()
# a source is the top of its river: a stretch before it that lies over the divide goes, unless another river runs into it
ends = set(tuple(p["cells"][-1].tolist()) for p in paths if p["kind"] == "river")
for i, p in enumerate(paths, 1):
    if p["son"] != 0: continue
    c = p["cells"]; h = ndi.gaussian_filter1d(hof(c), 1.5, mode="nearest"); k = int(np.argmax(h))
    if 0 < k < 0.45 * len(c) and h[k] - h[0] > 30 and not (set(map(tuple, c[:k].tolist())) & ends): p["cells"] = c[k:]; headcut += 1
# A channel that runs beside a longer river for much of its way reads as the same river drawn twice (user: "Duplicate
# rivers to fix", the Ob's Small Ob and a split of the Ob near Govnovka; a split Chao Phraya too). It goes, unless other
# rivers run into it: those are carried on, from where they met it, to the nearest point of the river it ran beside.
def twins(R=18, share=0.35, run=40):
    al = [(i, p) for i, p in enumerate(paths, 1) if p["alive"]]; idm = np.zeros((M, M), np.int32); endm = np.zeros((M, M), bool)
    for i, p in al:
        c = p["cells"]; idm[c[:, 0], c[:, 1]] = np.where(idm[c[:, 0], c[:, 1]] == 0, i, idm[c[:, 0], c[:, 1]]); endm[c[0, 0], c[0, 1]] = endm[c[-1, 0], c[-1, 1]] = True
    jd = ndi.distance_transform_edt(~endm); ln = np.zeros(len(paths) + 1, np.int64)
    for i, p in al: ln[i] = len(p["cells"])
    offs = [(dy, dx) for dy in range(-R, R + 1) for dx in range(-R, R + 1) if 9 < dy * dy + dx * dx <= R * R][::3]
    gone = kept = carried = 0
    for i, p in al:
        c = p["cells"]
        if len(c) < run: continue
        near = np.zeros(len(c), bool); who = np.zeros(len(c), np.int64)
        for dy, dx in offs:
            v = idm[np.clip(c[:, 0] + dy, 0, M - 1), np.clip(c[:, 1] + dx, 0, M - 1)]; hit = (v != 0) & (v != i) & (ln[v] >= len(c))
            who = np.where(hit & ~near, v, who); near |= hit
        near &= jd[c[:, 0], c[:, 1]] > 30
        best = cur = 0
        for b in near: cur = cur + 1 if b else 0; best = max(best, cur)
        if near.mean() > share and best > run:
            j = int(np.bincount(who[near]).argmax()); mc = paths[j - 1]["cells"]; links = []
            for k, q in enumerate(paths, 1):
                if not (q["alive"] and q["kind"] == "river" and q["to"] == i): continue
                e = q["cells"][-1]; t = int(np.argmin(np.abs(mc - e).max(1))); f = mc[t]; n = int(np.abs(f - e).max())
                if n > 3 * R: links = None; break
                seg = np.round(np.linspace(e, f, n + 1)).astype(np.int64)[1:]; links.append((k, q, seg, j))
            if links is None: kept += 1; continue
            for k, q, seg, j in links:
                q["cells"] = np.concatenate([q["cells"], seg]); q["to"] = j
                free = (occ[seg[:, 0], seg[:, 1]] == 0) | (occ[seg[:, 0], seg[:, 1]] == i); occ[seg[free, 0], seg[free, 1]] = k
            occ[(occ == i)] = 0; p["alive"] = False; gone += 1; carried += len(links)
    print("channels running beside a bigger river dropped: %d, their %d tributaries carried on to it | kept: %d" % (gone, carried, kept), flush=True)
twins()
# drop what would read as a spur: short rivers, and rivers that end in mid-air unless they are long; never one that others run into
while True:
    fed = set(p["to"] for p in paths if p["alive"] and p["kind"] == "river"); n = 0
    for i, p in enumerate(paths, 1):
        if not p["alive"] or i in fed: continue
        ln = len(p["cells"]); gone = p["kind"] == "river" and p["to"] > 0 and not paths[p["to"] - 1]["alive"]
        if (p["name"] == "(drawn)" or (stick[p["cells"][:, 0], p["cells"][:, 1]] >= 7).any()) and ln >= 20: continue      # a river drawn by hand stays, and so does one a city stands on
        if ln < MINLEN or (p["kind"] == "inland" and ln < 3 * MINLEN) or gone: p["alive"] = False; n += 1
    if n == 0: break
# a network that is all stubs goes as a whole
par = list(range(len(paths) + 1))
def find(a):
    while par[a] != a: par[a] = par[par[a]]; a = par[a]
    return a
for i, p in enumerate(paths, 1):
    if not p["alive"]: continue
    for k in (p["to"] if p["kind"] == "river" else 0, p["son"]):
        if k > 0 and paths[k - 1]["alive"]: par[find(i)] = find(k)
tot = {}
for i, p in enumerate(paths, 1):
    if p["alive"]: tot[find(i)] = tot.get(find(i), 0) + len(p["cells"])
small = 0
for i, p in enumerate(paths, 1):
    if p["alive"] and tot[find(i)] < 2 * MINLEN and p["name"] != "(drawn)" and not (stick[p["cells"][:, 0], p["cells"][:, 1]] >= 7).any(): p["alive"] = False; small += 1
net = [p for p in paths if p["alive"]]
print("rivers kept: %d of %d | stitched end to start: %d | led downhill to water: %d | sources moved to the divide: %d | stub networks dropped: %d | %.0f s"
      % (len(net), len(paths), stitched, led, headcut, small, time.time() - t0), flush=True)

# ---------------- which way everything runs: one flood over the whole traced network, from the water up
def orient(net):
    lin = np.concatenate([p["cells"][:, 0].astype(np.int64) * M + p["cells"][:, 1] for p in net]); uq, inv = np.unique(lin, return_inverse=True)
    cy, cx = (uq // M).astype(np.int32), (uq % M).astype(np.int32); n = len(uq); isl = land[cy, cx]
    cid = np.zeros((M, M), np.int32); cid[cy, cx] = np.arange(n) + 1; owner = np.zeros((M, M), np.int32); E1, E2 = [], []; o = 0
    for j, p in enumerate(net, 1):
        c = p["cells"]; m = owner[c[:, 0], c[:, 1]] == 0; owner[c[m, 0], c[m, 1]] = j; v = inv[o:o + len(c)]; o += len(c); E1.append(v[:-1]); E2.append(v[1:])
    x1, x2 = [], []
    for j, p in enumerate(net, 1):                                                                # rivers whose ends meet without sharing a cell are joined there
        for e in (p["cells"][0], p["cells"][-1]):
            y0, x0 = max(e[0] - 2, 0), max(e[1] - 2, 0); wc = cid[y0:e[0] + 3, x0:e[1] + 3]; wo = owner[y0:e[0] + 3, x0:e[1] + 3]; yy, xx = np.nonzero((wc > 0) & (wo != j))
            if len(yy) and owner[e[0], e[1]] == j: k = np.argmin((yy + y0 - e[0]) ** 2 + (xx + x0 - e[1]) ** 2); x1.append(cid[e[0], e[1]] - 1); x2.append(wc[yy[k], xx[k]] - 1)
    a_ = np.r_[np.concatenate(E1), np.array(x1, np.int64)]; b_ = np.r_[np.concatenate(E2), np.array(x2, np.int64)]; ok = a_ != b_; a_, b_ = a_[ok], b_[ok]
    G = coo_matrix((np.ones(2 * len(a_), np.int8), (np.r_[a_, b_], np.r_[b_, a_])), shape=(n, n)).tocsr(); nc, comp = connected_components(G, directed=False)
    hc = Hw[cy, cx].astype(np.float64); root = ~isl | (occ[cy, cx] == -1); has = np.zeros(nc, bool); has[comp[root]] = True
    od = np.lexsort((hc, comp)); low = od[np.r_[True, comp[od][1:] != comp[od][:-1]]]; inland = low[~has[comp[low]]]; root[inland] = True       # no water to reach: it ends at its lowest point
    ip, ix = G.indptr, G.indices; hl = hc.tolist(); pred = np.full(n, -1, np.int64); order = np.zeros(n, np.int64); seen = root.copy()
    heap = [(hl[i], 0, int(i)) for i in np.nonzero(root)[0]]; heapq.heapify(heap); k = 0
    while heap:
        lv, _, i = heapq.heappop(heap); order[i] = k; k += 1
        for j in ix[ip[i]:ip[i + 1]]:
            if not seen[j]: seen[j] = True; pred[j] = i; heapq.heappush(heap, (max(lv, hl[j]), k, int(j)))
    up = np.zeros(n, np.int32)
    for i in np.argsort(-order):
        if pred[i] >= 0: up[pred[i]] = max(up[pred[i]], up[i] + 1)
    return dict(uq=uq, inv=inv, cy=cy, cx=cx, n=n, isl=isl, pred=pred, order=order, up=up, comp=comp, nc=nc, has=has, inland=inland, root=root, hc=hc)

# ---------------- rivers whose sea Pangaea closed: on along the lowest ground to the nearest sea, lake or river, if that takes no real climb
occ[:] = 0; occ[keptdrawn & land] = -1                                                       # only the rivers that were kept still hold ground
for i, p in enumerate(paths, 1):
    if p["alive"]: c = p["cells"]; m = (occ[c[:, 0], c[:, 1]] == 0) & land[c[:, 0], c[:, 1]]; occ[c[m, 0], c[m, 1]] = i
k0 = len(paths); again = drawn_pass(); settle(k0 + 1)                                        # drawn rivers whose real counterpart did not survive the clean-up
net = [p for p in paths if p["alive"]]; print("drawn rivers traced on a second look:", again, flush=True)
O_ = orient(net); over = 0
for rnd in range(4):
    if not (len(O_["inland"]) and GENERATED and not BOX): break
    before = over; left = len(O_["inland"])
    K = 4; C = M // K; Lc = land.reshape(C, K, C, K).any((1, 3)); Hc = np.where(land, Hw, 9e9).reshape(C, K, C, K).min((1, 3)); Wc = (~land).reshape(C, K, C, K).any((1, 3))
    outlet = Wc.copy(); good = O_["has"][O_["comp"]]; outlet[O_["cy"][good] // K, O_["cx"][good] // K] = True                        # water, or a river that reaches water
    Hc = np.where(outlet & Wc, np.minimum(Hc, np.where(land, 9e9, Hw).reshape(C, K, C, K).min((1, 3))), Hc)
    P = C + 2; hp = np.full((P, P), 9e9); hp[1:-1, 1:-1] = np.where(Lc | outlet, Hc, 9e9); hl = hp.ravel().tolist(); okc = (np.pad(Lc | outlet, 1)).ravel().tolist()
    seen = bytearray(P * P); predc = np.full(P * P, -1, np.int64); lvl = np.zeros(P * P); seq = np.zeros(P * P, np.int64); nq = 0; src = np.nonzero(np.pad(outlet, 1).ravel())[0]
    heap = [(hl[i], int(i)) for i in src]; heapq.heapify(heap); offs = (-P - 1, -P, -P + 1, -1, 1, P - 1, P, P + 1)
    for i in src: seen[i] = 1
    while heap:                                                                               # every land cell learns the way out that crosses the lowest ground
        lv, i = heapq.heappop(heap); lvl[i] = lv; seq[i] = nq; nq += 1
        for d_ in offs:
            j = i + d_
            if not seen[j] and okc[j]: seen[j] = 1; predc[j] = i; heapq.heappush(heap, (lv if lv > hl[j] else hl[j], j))
    jobs = []; mouths_ = 0
    def hops(i, cap=16):
        k_ = 0
        while predc[i] >= 0 and k_ < cap: i = int(predc[i]); k_ += 1
        return k_
    ci = (O_["cy"] // K + 1).astype(np.int64) * P + O_["cx"] // K + 1; sizes = np.bincount(O_["comp"], minlength=O_["nc"])
    dWc = ndi.distance_transform_edt(~Wc) * K; seen_ = np.frombuffer(seen, np.uint8); isend = np.zeros(O_["n"], bool); o_ = 0          # px to the nearest water; the two ends of every river
    for p_ in net: isend[O_["inv"][o_]] = isend[O_["inv"][o_ + len(p_["cells"]) - 1]] = True; o_ += len(p_["cells"])
    for r in O_["inland"]:
        i = int(ci[r]); cl = lvl[i] - O_["hc"][r]; lim = 200 if sizes[O_["comp"][r]] >= 600 else 60
        if not seen[i] or cl > lim: continue
        m_ = np.nonzero(O_["comp"] == O_["comp"][r])[0]; x_ = m_[np.lexsort((seq[ci[m_]], lvl[ci[m_]]))[0]]          # it leaves from the cell that already stands nearest the way out
        # unless one of its own rivers already ends beside the water: a real river's line ends at its mouth, so that end is the way out, not a second line laid next to it
        e_ = m_[isend[m_] & (seen_[ci[m_]] > 0) & (dWc[O_["cy"][m_] // K, O_["cx"][m_] // K] <= 24) & (lvl[ci[m_]] - O_["hc"][r] <= lim) & (lvl[ci[m_]] <= lvl[ci[x_]] + 60)]
        e_ = [e for e in e_ if hops(int(ci[e])) < 16]                                              # and only if the way out from that end is the short one to the water beside it
        if len(e_): x_ = e_[int(np.argmin(lvl[ci[e_]]))]; mouths_ += 1
        jobs.append((cl, int(x_), int(ci[x_])))
    cl_ = np.array([lvl[(O_["cy"][r] // K + 1) * P + O_["cx"][r] // K + 1] - O_["hc"][r] for r in O_["inland"]]); kinds_ = []
    print("  networks that leave by a river of their own that ends beside the water:", mouths_, flush=True)
    print("  inland ends: %d | climb to get out: under 10 m %d, 10-60 m %d, 60-200 m %d, over 200 m %d" % (len(cl_), (cl_ < 10).sum(), ((cl_ >= 10) & (cl_ <= 60)).sum(), ((cl_ > 60) & (cl_ <= 200)).sum(), (cl_ > 200).sum()), flush=True)
    ids = [i_ for i_, p_ in enumerate(paths, 1) if p_["alive"]]; o_ = 0; grp = {}                # which network each river belongs to, kept up to date as networks merge
    for i_, p_ in zip(ids, net): grp[i_] = int(O_["comp"][O_["inv"][o_]]); o_ += len(p_["cells"])
    par_ = {}
    def top(a):
        while par_.get(a, a) != a: a = par_[a]
        return a
    for cl, r, i in sorted(jobs):
        mine = top(int(O_["comp"][r])); ban_ = [i_ for i_, g_ in grp.items() if top(g_) == mine]
        g = []
        while i >= 0 and len(g) < 4000: g.append(((i % P - 1) * K + K / 2, (i // P - 1) * K + K / 2)); i = predc[i]
        if len(g) < 2: continue
        g = np.array(g); g[0] = (O_["cx"][r], O_["cy"][r]); g = dense(ndi.gaussian_filter1d(g, 1.5, axis=0, mode="nearest")); k = len(paths)
        lay(dict(rank=6, name="(onward)", pts=g), fixed=True, ban=ban_, eager=True, minc=2)
        if len(paths) > k and loose(paths[-1]):                                                 # it found no way out: take it back
            occ[occ == len(paths)] = 0; paths.pop(); kinds_.append("no way out"); continue
        for q in paths[k:]:
            grp[len(paths)] = mine
            if q["kind"] == "river" and q["to"] in grp and top(grp[q["to"]]) != mine: par_[top(grp[q["to"]])] = mine
            if loose(q):
                t = beside(len(paths), q)
                q["kind"], q["to"] = ("river", t) if t else ("inland", 0)
            over += 1; kinds_.append(q["kind"])
        if len(paths) == k: kinds_.append("nothing")
    net = [p for p in paths if p["alive"]]; O_ = orient(net)
    print("  onward routes ended:", {k_: kinds_.count(k_) for k_ in set(kinds_)}, flush=True)
    del hp, hl, okc, seen, predc, lvl
    if over == before or len(O_["inland"]) >= left: break
uq, inv, cy, cx, n, isl, pred, order, up, comp, nc, has, inland, root = (O_[k] for k in ("uq", "inv", "cy", "cx", "n", "isl", "pred", "order", "up", "comp", "nc", "has", "inland", "root"))
size = np.bincount(comp, minlength=nc)
print("networks: %d | reach the sea or a lake: %d (%.1f%% of river length) | end inland: %d | led onward over low ground: %d | %.0f s" % (nc, int(has.sum()), 100 * size[has].sum() / n, int((~has).sum()), over, time.time() - t0), flush=True)
pickle.dump(dict(cy=cy, cx=cx, pred=pred, order=order, isl=isl, fixed=root & ~np.isin(np.arange(n), inland), up=up, comp=comp, inland=inland,
                 paths=[dict(rank=p["rank"], name=p["name"], cells=p["cells"].astype(np.int32)) for p in net]), open(os.path.join(WORK, "river_net.pkl"), "wb"))

# ---------------- draw
def smooth(c):
    p = c[:, ::-1].astype(np.float64); q = ndi.gaussian_filter1d(p, 2.0, axis=0, mode="nearest")
    wgt = np.clip(np.minimum(np.arange(len(p)), len(p) - 1 - np.arange(len(p))) / 5.0, 0, 1)[:, None]; return p + (q - p) * wgt          # ends stay where they join
final = [(p["rank"], p["name"], smooth(p["cells"])) for p in net]
pickle.dump([(r, nm, (xy - 0.5) / 2) for r, nm, xy in final], open(os.path.join(WORK, "rivers_final.pkl"), "wb"))
alpha = np.zeros((M, M), np.float32); land_d = ndi.binary_dilation(land, iterations=3)
HALF = np.array([1.3, 1.6, 1.9, 2.4]); marks = [np.ones((M, M), bool) for _ in HALF]; o = 0
for (rank, name, xy), p in zip(final, net):
    u = up[inv[o:o + len(xy)]].astype(np.float64); o += len(xy); base = 2.4 if rank <= 3 else 1.9 if rank <= 6 else 1.6
    s_ = np.r_[0, np.cumsum(np.hypot(np.diff(xy[:, 0]), np.diff(xy[:, 1])))]; q = dense(xy); uq_ = np.interp(np.linspace(0, s_[-1], len(q)), s_, u)
    hw_ = base * np.clip(0.55 + 0.45 * uq_ / 70.0, 0, 1)                                      # a river grows from its source
    k = np.argmin(np.abs(hw_[:, None] - HALF[None, :]), 1); qq = np.r_[q, (q[:-1] + q[1:]) / 2]; kk = np.r_[k, k[:-1]]
    yy = np.clip(np.round(qq[:, 1]).astype(int), 0, M - 1); xx = np.clip(np.round(qq[:, 0]).astype(int), 0, M - 1)
    for c in range(len(HALF)): marks[c][yy[kk == c], xx[kk == c]] = False
for half, m in zip(HALF, marks):
    if not m.all(): alpha = np.maximum(alpha, np.clip(half + 0.5 - ndi.distance_transform_edt(m).astype(np.float32), 0, 1))
del marks
alpha = np.clip((ndi.gaussian_filter(alpha, 0.7) - 0.5) * 2.0 + 0.5, 0, 1)                                   # take the stair-steps off
oa = ndi.gaussian_filter(keptdrawn.astype(np.float32), 1.3); alpha = np.maximum(alpha, np.clip((oa - 0.5) * 3.0 + 0.5, 0, 1)); del oa
alpha *= np.clip((ndi.gaussian_filter(land.astype(np.float32), 0.8) - 0.35) / 0.3, 0, 1)                  # a river stops at the shore: nothing is drawn on water
if BOX:
    T = read_png(os.path.join(LAYERS, "terrain.png"))[BOX[1]:BOX[3], BOX[0]:BOX[2], :3].astype(np.float32); a = alpha[BOX[1]:BOX[3], BOX[0]:BOX[2], None]
    write_png(os.path.join(WORK, "rivtest.png"), (T * (1 - a) + np.array((30, 40, 120), np.float32) * a).astype(np.uint8)); print("wrote work/rivtest.png"); sys.exit()
out = np.zeros((M, M, 4), np.uint8); out[..., 0] = 56; out[..., 1] = 72; out[..., 2] = 104; out[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
write_png(os.path.join(WORK, "rivers12000.png"), out)
print("rivers drawn: %d cells of line | done %.0f s" % (n, time.time() - t0))
