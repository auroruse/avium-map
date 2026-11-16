"""Eivorie: its own ground, made from the Eivorian map (data/eivorie/eivorie_map.png; user, 15 Nov 2026: "Implement custom
terrain for Eivorie"). That map is drawn over its own relief shading, but the shading cannot be lifted off it: the big
translucent names (FIERGENWEALD, MIDDELSAERIMMA and the rest) sit in it and would come back as ridges. So the map only says
where the uplands and the plains are, read from its lit slopes alone (lettering only ever darkens), and the ground is built
here as running water would leave it (_fluvial): every cell drains to Eivorie's drawn rivers (they are fictional) or to the
sea, and stands above the cell it drains to by the slope a stream of its size holds, steep where the map is rugged.

Heights are an assumption; the map gives none. They are set to sit with the ground round Eivorie (user: "Maybe too high
comparatively to surrounding elevation"): within ~280 km the neighbours reach 650 m at the 95th percentile and 910 m at the
99th, so Fiergenweald (Old English firgen, mountain, and weald, forest) is upland with 98% of Eivorie under TOP (900 m)
and summits to about 1,500 m, the plains 20-200 m.

The map is laid on the 6000 grid by the affine in data/eivorie/affine_coast.npy: fitted to the city dots, then to the coast
(the two coastlines agree to about 6 px). build(h, land, KM) rewrites h over Eivorie, easing into the neighbours' ground."""
import os, sys, csv, heapq, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scipy import ndimage as ndi
from common import *
from polar import _n, _ss

HERE = os.path.join(DATA, "eivorie")
THETA = 0.45                      # how fast a stream's slope falls as it gathers water (slope ~ area ** -THETA), as on real rivers
SETTLE = 8                        # times the water is re-routed down the ground it made
HEAD = 6.0                        # cells of water below which the ground is hillside, not channel
TOP = 900.0                       # m: the height 98% of Eivorie stands under
RIM = 60                          # px (12000 grid) of the neighbours' land the drainage is built across as well

def _mask6000():
    """Eivorie's land on the borders layer (6000 grid), found as riverlayer.py finds it: the fills its cities stand in"""
    bord = read_png(os.path.join(LAYERS, "borders.PNG")); eiv = np.zeros((6000, 6000), bool); cols = {}
    for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t"):
        if r["KIND"] == "city" and r["NATION"] == "Eivorie" and r["X"]:
            x, y = int(float(r["X"])), int(float(r["Y"]))
            if bord[y, x, 3] > 200: cols.setdefault(tuple(int(v) for v in bord[y, x, :3]), []).append((y, x))
    for c, pts in cols.items():
        lab, _ = ndi.label((np.abs(bord[..., :3].astype(int) - np.array(c)).max(-1) <= 3) & (bord[..., 3] > 200))
        eiv |= np.isin(lab, list({int(lab[y, x]) for y, x in pts} - {0}))
    return eiv

def _nconv(v, w, s):
    w = w.astype(np.float32); return ndi.gaussian_filter(v * w, s) / np.maximum(ndi.gaussian_filter(w, s), 1e-4)

def upland(log=print):
    """How rugged the Eivorian map's relief is, 0-1, on the image's own pixels, and Eivorie's extent there"""
    im = read_png(os.path.join(HERE, "eivorie_map.png"))[..., :3].astype(np.float32); r, g, b = im[..., 0], im[..., 1], im[..., 2]
    green = (g - r > 15) & (g - b > 20) & (g > 60)                          # Eivorie's fill; the neighbours are other colours
    lab, _ = ndi.label(ndi.binary_closing(green, iterations=4)); big = np.bincount(lab.ravel())[1:].argmax() + 1
    E = ndi.binary_fill_holes(lab == big)
    ok = E & ndi.binary_erosion(ndi.binary_opening(green, iterations=1), iterations=1)   # not roads, rivers, icons, dots
    Y = 0.3 * r + 0.59 * g + 0.11 * b
    base = _nconv(Y, ok, 25.0); keep = ok & (Y > 0.85 * base)               # lettering and deep shadow left out of the reference
    base = _nconv(Y, keep, 25.0)
    lit = np.where(keep, np.maximum(Y / np.maximum(base, 1.0) - 1.0, 0.0), 0.0)   # lit slopes only: lettering never brightens
    R = np.sqrt(_nconv(lit ** 2, ok, 18.0))
    lo, hi = np.percentile(R[E], [15, 92]); U = _nconv(_ss((R - lo) / (hi - lo)), E, 26.0)          # uplands rise through foothills
    log("    Eivorian map: %d px of Eivorie, roughness read from %.0f%% of them" % (int(E.sum()), 100 * (ok & E).sum() / E.sum()))
    return U.astype(np.float32), E

def _membrane(D, inside, fixed, KM, length, S=4, iters=1500):
    """C over `inside`, equal to D on `fixed` cells and relaxing away from them (screened Laplace: changes shape over
    `length` km, never along a band shaped like the boundary); edges against the sea carry no constraint"""
    cs = (D.shape[0] // S, D.shape[1] // S); cut = lambda a: a[:cs[0] * S, :cs[1] * S].reshape(cs[0], S, cs[1], S)
    Dc = cut(D).mean((1, 3)); I = cut(inside).mean((1, 3)) > 0.5; F = (cut(fixed).mean((1, 3)) > 0.5) & ~I
    act = I | F; C = np.where(F, Dc, 0.0).astype(np.float64); k2 = (S * KM / length) ** 2
    for _ in range(iters):
        acc = np.zeros_like(C); n = np.zeros_like(C)
        for sh_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = np.roll(C, sh_, (0, 1)); ok = np.roll(act, sh_, (0, 1))
            acc += np.where(ok, nb, C); n += 1.0
        C = np.where(I, acc / (n + k2), np.where(F, Dc, 0.0))
    full = np.zeros(D.shape, np.float32); full[:cs[0] * S, :cs[1] * S] = _up_lin(C.astype(np.float32), (cs[0] * S, cs[1] * S))
    return ndi.gaussian_filter(full, S)

def _up_lin(a, shape):
    yy = (np.arange(shape[0]) + 0.5) * a.shape[0] / shape[0] - 0.5; xx = (np.arange(shape[1]) + 0.5) * a.shape[1] / shape[1] - 0.5
    return ndi.map_coordinates(a, np.meshgrid(yy, xx, indexing="ij"), order=1, mode="nearest")

def _thin(m):
    """A stroke down to its middle line, one pixel wide (Zhang-Suen)"""
    m = m.copy()
    while True:
        gone = False
        for step in (0, 1):
            P = np.pad(m, 1); n = [P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:], P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]]
            B = sum(v.astype(np.uint8) for v in n); A = sum((~n[i] & n[(i + 1) % 8]).astype(np.uint8) for i in range(8))
            c = (~(n[0] & n[2] & n[4]) & ~(n[2] & n[4] & n[6])) if step == 0 else (~(n[0] & n[2] & n[6]) & ~(n[0] & n[4] & n[6]))
            rm = m & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any(): m &= ~rm; gone = True
        if not gone: return m

def _fluvial(dom, outlet, skel, steep, rng, log=print):
    """Ground as running water leaves it, over the cells of `dom`.
    Every cell is given the cell it drains to: the cheapest way down to an `outlet` cell (the shore, the rim) or to a
    drawn river (`skel`, one pixel wide), over ground whose cost is noise, which is what makes the streams wander and
    join. Travel along a drawn river costs nothing, so a river is one channel from its head to its mouth and everything
    beside it drains into it. Then the water is counted down the tree (A: cells draining through each cell) and the
    ground is raised up it from the outlets: a cell stands above the one it drains to by steep * (A + HEAD) ** -THETA,
    the slope a stream of that size holds when it cuts as fast as the land rises (HEAD: a hillside is not a stream, and
    the first few cells of water do not steepen it). Small streams are steep and big ones nearly
    flat, so valleys, spurs and sharp divides come out at every scale, a river's bed falls all the way to its mouth,
    and its head stands on high ground.
    -> G (rise above the outlet per unit of steepness; z = base + K * G), A"""
    sh = dom.shape; m = sh[1]; dom = dom.copy(); dom[0], dom[-1], dom[:, 0], dom[:, -1] = False, False, False, False
    N = 0.7 * _n(sh, 2.5, rng) + 0.5 * _n(sh, 8, rng) + 0.3 * _n(sh, 1.0, rng)
    w = np.exp(0.9 * N).ravel().tolist(); dl = dom.ravel().tolist(); sk = (skel & dom).ravel().tolist()
    n = dom.size; best = [np.inf] * n; pr = [-1] * n; seen = [False] * n; order = []; cnt = 0; heap = []
    for i in np.flatnonzero((outlet & dom).ravel()).tolist(): best[i] = 0.0; heap.append((0.0, cnt, i)); cnt += 1
    heapq.heapify(heap); offs = ((-m - 1, 1.4142), (-m, 1.0), (-m + 1, 1.4142), (-1, 1.0), (1, 1.0), (m - 1, 1.4142), (m, 1.0), (m + 1, 1.4142))
    while heap:
        c, _, i = heapq.heappop(heap)
        if seen[i]: continue
        seen[i] = True; order.append(i); si = sk[i]
        for o, ln in offs:
            j = i + o
            if dl[j] and not seen[j]:
                cj = c if (si and sk[j]) else c + w[j] * ln
                if cj < best[j]: best[j] = cj; pr[j] = i; cnt += 1; heapq.heappush(heap, (cj, cnt, j))
    pr0 = pr; st = steep.ravel(); Gr = None
    def raise_(order, pr):
        A = [1.0] * n
        for i in reversed(order):
            if pr[i] >= 0: A[pr[i]] += A[i]
        o = np.array(order, np.int64); pred = np.array(pr, np.int64); A = np.array(A, np.float32)
        ln = np.where(np.isin(np.abs(o - pred[o]), (1, m)), 1.0, 1.4142)
        gain = (st[o] * (A[o] + HEAD) ** -THETA * ln).tolist(); G = [0.0] * n; pl = pred[o].tolist()
        for k, i in enumerate(order):
            if pl[k] >= 0: G[i] = G[pl[k]] + gain[k]
        return np.array(G, np.float32), A
    G, A = raise_(order, pr)
    # A fixed drainage leaves ground that disagrees with itself across a divide: a basin that reaches its river the long
    # way round stands as a table above the slope beside it. So the water is sent down the ground it has just made, lowest
    # first from the outlets, and the ground raised again, until the two agree. The drawn rivers keep their channels.
    for it in range(SETTLE):
        Gr = G if Gr is None else 0.5 * (Gr + G); key = Gr.tolist()
        seen = [False] * n; pr = [-1] * n; order = []; cnt = 0; heap = []
        for i in np.flatnonzero((outlet & dom).ravel()).tolist(): seen[i] = True; heap.append((0.0, cnt, i)); cnt += 1
        heapq.heapify(heap)
        while heap:
            lv, _, i = heapq.heappop(heap); order.append(i)
            for o, _ln in offs:
                j = i + o
                if dl[j] and not seen[j]:
                    if sk[j]:
                        if pr0[j] != i: continue                                     # a drawn river is entered only from downstream
                        seen[j] = True; pr[j] = i; cnt += 1; heapq.heappush(heap, (lv, cnt, j))
                    else: seen[j] = True; pr[j] = i; cnt += 1; heapq.heappush(heap, (max(lv, key[j]), cnt, j))
        G2, A = raise_(order, pr); moved = float(np.abs(G2 - G)[dom.ravel()].mean() / max(float(G2[dom.ravel()].mean()), 1e-6)); G = G2
    log("    drainage: %d cells, %d on drawn rivers; the largest stream drains %.0f km2; last settling pass moved the ground %.1f%%"
        % (len(order), int(np.sum(sk)), float(A.max()) * 3.06, 100 * moved))
    return G.reshape(sh), A.reshape(sh)

def build(h, land, KM, seed=31, log=print):
    rng = np.random.default_rng(seed)
    eiv6 = _mask6000(); ys, xs = np.nonzero(ndi.binary_dilation(eiv6, iterations=40))
    rs = slice(2 * ys.min(), 2 * ys.max() + 2); cs = slice(2 * xs.min(), 2 * xs.max() + 2)
    E12 = eiv6.repeat(2, 0).repeat(2, 1)[rs, cs]; L = land[rs, cs]; sh = L.shape
    # the map's ruggedness, laid onto the grid
    U, Ei = upland(log); T = np.load(os.path.join(HERE, "affine_coast.npy"))
    A = np.array([[T[0, 0], T[1, 0]], [T[0, 1], T[1, 1]]]); inv = np.linalg.inv(A)
    yy, xx = np.mgrid[rs, cs].astype(np.float32); X6 = (xx + 0.5) / 2 - T[2, 0]; Y6 = (yy + 0.5) / 2 - T[2, 1]; del yy, xx
    u = inv[0, 0] * X6 + inv[0, 1] * Y6; v = inv[1, 0] * X6 + inv[1, 1] * Y6; del X6, Y6
    Ug = ndi.map_coordinates(U, [v, u], order=1, mode="nearest"); del u, v
    Ug = ndi.gaussian_filter(Ug, 3.0)
    # drawn rivers in Eivorie (fictional, kept as drawn): the skeleton the ground drains to
    dr6 = (read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0) & ndi.binary_dilation(eiv6, iterations=8)
    rv = dr6.repeat(2, 0).repeat(2, 1)[rs, cs] & L
    drv = (ndi.distance_transform_edt(~rv) * KM).astype(np.float32) if rv.any() else np.full(sh, 1e4, np.float32)
    # The ground is what its rivers have made of it (user, 16 Nov 2026: "eivorie looks unrealistic terrainwise compared to
    # surroundings"; before this it was an envelope of smooth noise with a trough pressed along each river, two thirds of the
    # neighbours' relief at every scale and no sharp divide anywhere). The drainage is built across RIM px of the neighbours'
    # land as well and let out at the far side of it, or every border would be a divide and stand as a ridge.
    dom = L & (ndi.distance_transform_edt(~E12) <= RIM)
    water = ndi.binary_dilation(~L, structure=np.ones((3, 3), bool)); far = ndi.binary_dilation(L & ~dom, structure=np.ones((3, 3), bool))
    skel = _thin(rv) & dom
    mouths = skel & ndi.binary_dilation(~L, iterations=5)
    # how steep the country is: the map's uplands, the plains a tenth of them, and long swells so no two ranges match
    steep = (0.10 + 0.90 * Ug ** 1.3) * np.exp(0.25 * _n(sh, 60, rng))
    G, A = _fluvial(dom, (water | far | mouths) & dom, skel, steep.astype(np.float32), rng, log)
    K = TOP / float(np.percentile(G[E12 & L], 98))
    z = np.where(dom, 2.0 + K * G, h[rs, cs]).astype(np.float32)
    z = np.where(dom, _nconv(z, dom, 0.6), z)                              # hillsides creep: no divide is a knife edge
    # Joined to the neighbours without a seam along the border. A crossfade by distance from the border draws the border
    # itself into the ground (user: "what's with the sharp fucking cutoff where Eivorie's borders are?"). Instead the
    # broad level is corrected by a field that equals the neighbours' level at the border and relaxes away from it
    # (a screened membrane, ~120 km), and only the fine grain is crossfaded, over a few km.
    hc = h[rs, cs]; h0 = hc.copy()
    # a drawn river on the border needs its valley on the neighbours' side too, or the bed is cut as a trench along it
    edge = ndi.distance_transform_edt(~E12) + ndi.distance_transform_edt(E12)       # px from the border, either side
    side = L & (edge < 14.0) & (drv < 25.0)                                          # both banks, wherever the river runs
    if side.any():
        fl0 = 8.0 + 0.3 * ndi.gaussian_filter(h0, 30.0); w0 = 9.0
        h0 = np.where(side, np.minimum(h0, fl0 + (h0 - fl0) * (1.0 - np.exp(-(drv / w0) ** 2))), h0)
        hc[:] = np.where(side, h0, hc)
    lp = lambda a: _nconv(a, L, 18.0)
    zl, hl = lp(z), lp(h0); D = hl - zl
    C = _membrane(D, E12 & L, L & ~E12, KM, 120.0)
    wf = _ss(ndi.distance_transform_edt(E12) / 20.0)                       # the grain changes over ~35 km
    out = zl + C + (z - zl) * wf + (h0 - hl) * (1 - wf)
    wb = _ss(ndi.distance_transform_edt(E12) / 10.0)                       # what the coarse level field leaves, over ~17 km
    out = out * wb + h0 * (1 - wb)
    hc[:] = np.where(L & E12, np.maximum(out, 2.0), hc)
    log("    joined to the neighbours: level corrected by %.0f m at the 95th percentile, %.0f m at most"
        % (float(np.percentile(np.abs(C[E12 & L]), 95)), float(np.abs(C[E12 & L]).max())))
    m = E12 & L
    log("  Eivorie: %d px, ground %.0f-%.0f m, median %.0f, 95%% under %.0f | uplands (map ruggedness > 0.5) on %.0f%%"
        % (int(m.sum()), float(z[m].min()), float(z[m].max()), float(np.median(z[m])), float(np.percentile(z[m], 95)), 100 * (Ug[m] > 0.5).mean()))
    return h

if __name__ == "__main__":
    # preview: the finished heights with Eivorie rebuilt -> argv[1] (int16, 12000 grid)
    import sys, time
    t0 = time.time(); land = np.load(os.path.join(WORK, "land12k.npy")); H = np.load(os.path.join(WORK, "height.npy")).astype(np.float32)
    h = np.where(land, H, 0); h = build(h, land, 1.75); H = np.where(land, h, H)
    np.save(sys.argv[1], np.round(H).astype(np.int16)); print("preview written", round(time.time() - t0), "s")
