"""Hyperborea and Tartarus: the two polar continents have nothing under them on the Pangaea overlay, so their ground is made
here from their Talopedia articles (hyperborea.md, tartarus.md; avium.md for Tartarus's ice sheet).

Hyperborea: coastal lowlands (0-200 m) with cliffs, lava fields, cinder cones and raised beaches; the Northern Wall, an
unbroken volcanic ring, peaks 2,000-4,000 m, highest 4,187 m, cut through by a handful of glacier gaps that line up with the
deepest fjords; behind it a high, flat-topped ice plateau. Offshore, the subduction trench the ring stands over. Two places
depart from the article at the user's word (15 Nov 2026): the Wall stands about 160 km inland, not 100, and the interior is
a plateau, Greenland's ice surface brought to 1,350-2,450 m, not a surface at 200-800 m.

Tartarus: Antarctica's real ice surface (ETOPO 2022 60s surface), laid over Tartarus where the two outlines agree best (user,
15 Nov 2026), thin over the Tartarean Rift. The Rift is the multi-ring basin already in the drawing: a mountainous central
island inside a deep moat, rings of island arcs over deep troughs, the rings carried on to the land as inward-facing scarps,
and fractures running out from it across the continent.

Built in map space at the pipeline's 1.75 km per 12000-grid pixel, like everything else on the map: the projection squeezes
the poles into the corners, and ground built true to the sphere would show stretched toward them. The drawing itself was
drawn in map space. No white ice: the ice sheets are coloured by height like any other ground (user, 15 Nov 2026).

build(land, has, KM) -> list of (rows, cols, land_mask, heights, sea_min_depth) per continent, all crops of the 12000 grid.
The ice is coloured by height like any other ground: no white and no ice tint (user, 15 Nov 2026)."""
import heapq, numpy as np
from scipy import ndimage as ndi

def _ss(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)

def _n(shape, s, rng):
    """smooth noise with a grain of about s px, standard deviation 1"""
    f = max(int(s // 4), 1); k = (shape[0] // f + 3, shape[1] // f + 3)
    g = ndi.gaussian_filter(rng.standard_normal(k).astype(np.float32), s / f)
    if f > 1:
        yy = (np.arange(shape[0]) + 0.5) / f; xx = (np.arange(shape[1]) + 0.5) / f
        g = ndi.map_coordinates(g, np.meshgrid(yy, xx, indexing="ij"), order=1, mode="nearest")
    else:
        g = g[:shape[0], :shape[1]]
    return (g - g.mean()) / g.std()

def _ridged(shape, s, rng): return (1.0 - np.clip(np.abs(_n(shape, s, rng)) / 1.6, 0, 1)) ** 2

def _up(a, shape, order=1):
    yy = (np.arange(shape[0]) + 0.5) * a.shape[0] / shape[0] - 0.5; xx = (np.arange(shape[1]) + 0.5) * a.shape[1] / shape[1] - 0.5
    return ndi.map_coordinates(a, np.meshgrid(yy, xx, indexing="ij"), order=order, mode="nearest")

def _valleys(z, band, water, KM, rng, S=2, keep=0.3, side=900.0, trunk=600.0, weight=None, ret_w=False, log=print):
    """Cut the drainage a range would have into z. The ground in `band` is flooded from the water inland, lowest first, which
    gives every cell the neighbour it drains to; the more ground drains through a cell the deeper its valley, down to `keep`
    of the height, and the cut widens away from the stream at `side` metres per coarse cell."""
    cs = (z.shape[0] // S, z.shape[1] // S); zc = z[:cs[0] * S, :cs[1] * S].reshape(cs[0], S, cs[1], S).mean((1, 3))
    zc = zc + 60.0 * _n(cs, 1.5, rng) * (S <= 2)
    b = band[:cs[0] * S, :cs[1] * S].reshape(cs[0], S, cs[1], S).any((1, 3)); w = water[:cs[0] * S, :cs[1] * S].reshape(cs[0], S, cs[1], S).any((1, 3))
    b[0], b[-1], b[:, 0], b[:, -1] = False, False, False, False
    m = cs[1]; bf = b.ravel(); z0 = zc.ravel(); seen = np.zeros(bf.size, bool); pred = np.full(bf.size, -1, np.int64)
    seeds = np.flatnonzero((ndi.binary_dilation(w) & b).ravel()); seen[seeds] = True
    heap = [(float(z0[i]), int(i)) for i in seeds]; heapq.heapify(heap); order = []; nb = (-m - 1, -m, -m + 1, -1, 1, m - 1, m, m + 1)
    while heap:
        zz, i = heapq.heappop(heap); order.append(i)
        for o in nb:
            j = i + o
            if bf[j] and not seen[j]: seen[j] = True; pred[j] = i; heapq.heappush(heap, (max(float(z0[j]), zz), j))
    if not order: return (z, np.zeros(z.shape, np.float32)) if ret_w else z
    order = np.array(order, np.int64); pos = np.full(bf.size, -1, np.int64); pos[order] = np.arange(len(order))
    pp = np.where(pred[order] >= 0, pos[pred[order]], -1).tolist(); acc = [1] * len(order)
    for k in range(len(order) - 1, -1, -1):
        if pp[k] >= 0: acc[pp[k]] += acc[k]
    A = np.ones(bf.size, np.float32); A[order] = acc
    wv = (_ss(np.log(A / 2.0) / np.log(trunk)).reshape(cs) * b).astype(np.float32)
    C = wv * (1.0 - keep) * np.maximum(zc, 0)
    for _ in range(7):
        for dy, dx, c in ((0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            C = np.maximum(C, np.roll(C, (dy, dx), (0, 1)) - side * c)
    if S > 2: C = ndi.gaussian_filter(C, 2.0)                               # gentle sides: no straight facets, no thin grid-aligned channels
    C = np.minimum(C * b, np.maximum(zc, 0) * (1.0 - keep))
    log("    valleys: %d cells drained, %d trunk cells" % (len(order), int((wv > 0.5).sum())))
    cut = np.zeros(z.shape, np.float32); cut[:cs[0] * S, :cs[1] * S] = _up(ndi.gaussian_filter(C, 0.8 if S <= 2 else 1.5), (cs[0] * S, cs[1] * S))
    out = z - cut * (band if weight is None else weight)
    if ret_w:
        wf = np.zeros(z.shape, np.float32); wf[:cs[0] * S, :cs[1] * S] = _up(wv, (cs[0] * S, cs[1] * S)); return out, wf
    return out

def _cone(z, cy, cx, h, R, crater, caldera, KM, aspect=1.0, ang=0.0):
    """a volcano (or a peak) of height h and radius R km, added onto z at (cy, cx); aspect > 1 draws it out along ang"""
    rp = int(R * aspect / KM) + 2; y0, y1 = max(cy - rp, 0), min(cy + rp + 1, z.shape[0]); x0, x1 = max(cx - rp, 0), min(cx + rp + 1, z.shape[1])
    yy, xx = np.mgrid[y0:y1, x0:x1]; a = np.arctan2(yy - cy, xx - cx)
    du = (xx - cx) * np.cos(ang) + (yy - cy) * np.sin(ang); dw = -(xx - cx) * np.sin(ang) + (yy - cy) * np.cos(ang)
    r = np.hypot(du / aspect, dw) * KM / R
    r = r * (1.0 + 0.08 * np.cos(3 * a + h) + 0.05 * np.cos(5 * a + R))           # not a perfect circle
    c = h * np.clip(1.0 - r, 0, 1) ** 1.45
    if caldera: c = np.minimum(c, h * 0.82) - 0.25 * h * np.exp(-(r / 0.22) ** 6)
    else: c = c - crater * h * np.exp(-(r / 0.07) ** 2)
    z[y0:y1, x0:x1] += np.maximum(c, 0)

def _coast_fields(land, KM, sig=28):
    """distance inland from the coast as a whole (fjords and bays filled), and offshore from it, in km"""
    Lsm = ndi.gaussian_filter(land.astype(np.float32), sig) > 0.5
    return Lsm, (ndi.distance_transform_edt(Lsm) * KM).astype(np.float32), (ndi.distance_transform_edt(~Lsm) * KM).astype(np.float32)

def _streaks(sh, vy, vx, rng, S=3, steps=14):
    """fine grain smeared along a flow field (line integral convolution): the flow lines on an ice stream's surface"""
    cs = (sh[0] // S, sh[1] // S); tex = ndi.gaussian_filter(rng.standard_normal(cs).astype(np.float32), 0.6)
    fy = vy[:cs[0] * S:S, :cs[1] * S:S]; fx = vx[:cs[0] * S:S, :cs[1] * S:S]
    gy, gx = np.mgrid[:cs[0], :cs[1]].astype(np.float32); acc = tex.copy()
    for sg in (1.0, -1.0):
        py, px = gy.copy(), gx.copy()
        for _ in range(steps):
            dy = ndi.map_coordinates(fy, [py, px], order=1, mode="nearest"); dx = ndi.map_coordinates(fx, [py, px], order=1, mode="nearest")
            py += sg * dy; px += sg * dx; acc += ndi.map_coordinates(tex, [py, px], order=1, mode="nearest")
    acc = ndi.gaussian_filter(acc, 0.7); acc /= acc.std()                                 # no grid left to show once stretched
    out = np.zeros(sh, np.float32); out[:cs[0] * S, :cs[1] * S] = _up(acc, (cs[0] * S, cs[1] * S), order=3); return out

def _ice_surface(ice, mask, seeds, KM, rng, log, S=6, trunk=1500.0, keep=0.8, wind=None):
    """What an ice sheet's surface carries besides its overall shape: ice streams branching back from where the ice leaves
    (seeds), flow lines along them, fields of low snow dunes across the slope, and dead-flat patches over lakes under the ice."""
    sh = ice.shape
    ice, wv = _valleys(ice, mask, seeds, KM, rng, S=S, keep=keep, side=55.0, trunk=trunk, ret_w=True, log=log)
    sm = ndi.gaussian_filter(ice, 12.0); gy, gx = np.gradient(sm); g = np.maximum(np.hypot(gy, gx), 1e-6)
    strm = ndi.gaussian_filter(wv, 6.0); strm = _ss(strm / max(float(strm.max()), 1e-6) * 2.5)
    ice = ice + (4.0 + 9.0 * strm) * _streaks(sh, -gy / g, -gx / g, rng) * mask          # flow lines, strongest on the streams
    if wind is not None:                                                                   # swells across the flow, 20-40 km apart
        ice = ice + 30.0 * _streaks(sh, gx / g, -gy / g, rng, S=8, steps=5) * (0.4 + 0.6 * (1 - strm)) * mask
    pat = _ss((_n(sh, 220, rng) + 0.1) / 0.9) * (1 - strm)                                # dunes where the ice is not streaming:
    if wind is None: ice = ice + 6.0 * _streaks(sh, gx / g, -gy / g, rng, S=4, steps=6) * pat * mask   # short grain across the slope
    else:                                                                                  # ridges across the wind that built them
        wy, wx = wind; pat = _ss((_n(sh, 260, rng) + 0.3) / 0.8) * (1 - strm)
        ice = ice + 13.0 * _streaks(sh, wx, -wy, rng, S=3, steps=10) * pat * mask
    lk = _ss((_n(sh, 40, rng) - 1.55) / 0.35) * (1 - strm) * mask                          # lakes under the ice: flat, a touch low
    ice = ice * (1 - lk) + (ndi.gaussian_filter(ice, 10.0) - 4.0) * lk
    log("    ice surface: %.1f%% streaming, %.1f%% dune fields, %.1f%% over subglacial lakes" % (100 * (strm[mask] > 0.5).mean(), 100 * (pat[mask] > 0.5).mean(), 100 * (lk[mask] > 0.5).mean()))
    return ice

def _hyperborea(land, P, KM, rng, log):
    sh = land.shape; water = ~land
    Lsm, Dg, Do = _coast_fields(land, KM)
    Dw = Dg + 16.0 * _n(sh, 70, rng) + 9.0 * _n(sh, 25, rng)              # the ring follows the coast, not a ruler line off it
    rc = 160.0 + 22.0 * np.clip(_n(sh, 260, rng), -1.6, 1.6)               # crest about 160 km inland (user, 15 Nov 2026)
    x = Dw - rc
    # coastal lowland: cliffs at the sea, rising to 200 m at the foot of the Wall; knobbed ground
    low = 45.0 + 155.0 * _ss(Dw / np.maximum(rc - 40.0, 20.0)) + 30.0 * _n(sh, 22, rng) + 20.0 * _n(sh, 5, rng)
    low = low + 70.0 * _n(sh, 45, rng) * _ss(Dw / 25.0) + 35.0 * _ridged(sh, 9, rng) * _ss(Dw / 15.0)           # rolling hills
    low = low - 14.0 * _ss((_n(sh, 3, rng) - 1.2) / 0.5) * _ss((90.0 - low) / 40.0)                           # thermokarst pits
    # the Wall
    Hc = np.clip(2950.0 + 550.0 * _n(sh, 320, rng) + 400.0 * _n(sh, 90, rng), 2250.0, 3900.0)
    wo = 30.0 + 30.0 * _ss(0.5 + 0.5 * _n(sh, 180, rng)); wi = 40.0 + 40.0 * _ss(0.5 + 0.5 * _n(sh, 180, rng))
    prof = np.exp(-0.5 * (x / np.where(x < 0, wo, wi)) ** 2)
    serr = np.clip(0.78 + 0.16 * _n(sh, 45, rng) + 0.1 * _n(sh, 14, rng), 0.45, 1.1)   # a broad massif: the drainage below carves the ridges
    foot = np.exp(-0.5 * ((x + 1.6 * wo) / (0.7 * wo)) ** 2) * (650.0 * _ridged(sh, 16, rng) * _ss(0.6 + 0.6 * _n(sh, 120, rng)))
    ring = Hc * prof * serr + 110.0 * prof * (_ridged(sh, 4, rng) - 0.35) + foot
    # nunataks: peaks of the buried range standing out of the ice behind the Wall
    z = np.maximum(low, low + ring)
    # volcanoes along the Wall, a few lava shields on the lowland, cones on the larger islands
    cand = np.argwhere(P & (np.abs(x) < 14.0))
    rng.shuffle(cand); placed = []
    for cy, cx in cand:
        if len(placed) >= 46: break
        if any((cy - py) ** 2 + (cx - px) ** 2 < (62.0 / KM) ** 2 for py, px in placed): continue
        placed.append((cy, cx)); h = rng.uniform(500.0, 1500.0)
        _cone(z, cy, cx, h, h / 1000.0 * rng.uniform(16.0, 24.0), rng.uniform(0.05, 0.12), rng.random() < 0.3, KM)
    shields = np.argwhere(P & (Dw > 12.0) & (x < -45.0)); rng.shuffle(shields); ns = 0
    for cy, cx in shields[:400]:
        if ns >= 9: break
        if any((cy - py) ** 2 + (cx - px) ** 2 < (90.0 / KM) ** 2 for py, px in placed): continue
        placed.append((cy, cx)); ns += 1; h = rng.uniform(220.0, 480.0)
        _cone(z, cy, cx, h, rng.uniform(22.0, 40.0), 0.04, False, KM)
    clus = _ss((_n(sh, 120, rng) - 0.5) / 0.6); cc = np.argwhere(P & (x < -50.0) & (Dw > 8.0) & (rng.random(sh) < 0.0006 * clus)); ncc = 0
    for cy, cx in cc[:160]:
        h = rng.uniform(60.0, 260.0); _cone(z, cy, cx, h, rng.uniform(2.5, 6.0), 0.18, False, KM); ncc += 1
    il, nil = ndi.label(P & ~Lsm); ni = 0
    for i, sl in enumerate(ndi.find_objects(il), 1):
        if sl is None: continue
        m = il[sl] == i
        if m.sum() < 500 or rng.random() < 0.35: continue
        cy, cx = [int(v) for v in ndi.center_of_mass(m)]; cy += sl[0].start; cx += sl[1].start
        if not P[cy, cx]: continue
        h = rng.uniform(300.0, 900.0); _cone(z, cy, cx, h, min(h / 1000.0 * 18.0, 0.6 * np.sqrt(m.sum()) * KM), 0.08, False, KM); ni += 1
    # lava flows: lobes with steep fronts, spreading downhill from the volcanoes onto the lowland
    vmask = np.zeros(sh, bool)
    for cy, cx in placed: vmask[cy, cx] = True
    dvol = (ndi.distance_transform_edt(~vmask) * KM).astype(np.float32)
    lobes = _n(sh, 26, rng) + 0.6 * _n(sh, 9, rng) + 0.9 * _ss((70.0 - dvol) / 50.0)
    lava = 40.0 * _ss((lobes - 0.95) / 0.12) + 25.0 * _ss((lobes - 1.45) / 0.1)
    z = z + lava * _ss((-x - 10.0) / 20.0) * P
    log("    Northern Wall crest %.0f-%.0f km inland, %d volcanoes on it, %d lava shields, %d cinder cones, %d island cones, lava on %.1f%% of the lowland"
        % (np.percentile(rc[P], 5), np.percentile(rc[P], 95), len(placed) - ns, ns, ncc, ni, 100 * ((lava > 20) & P & (x < -10)).sum() / max((P & (x < -10)).sum(), 1)))
    # glacier gaps at the heads of the deepest fjords, cut through the Wall and on into the plateau
    fj = water & Lsm; lab, _ = ndi.label(water); ocean = np.bincount(lab.ravel())[1:].argmax() + 1; fj &= lab == ocean
    heads = []
    for i in np.argsort(-np.where(fj, Dg, 0), axis=None)[:20000]:
        cy, cx = divmod(int(i), sh[1])
        if Dg[cy, cx] < 10.0: break
        if all((cy - py) ** 2 + (cx - px) ** 2 > (700.0 / KM) ** 2 for py, px in heads): heads.append((cy, cx))
        if len(heads) >= 7: break
    gy, gx = np.gradient(ndi.gaussian_filter(Dg, 12.0)); path = np.zeros(sh, bool); trough = np.zeros(sh, bool)
    gyo, gxo = np.gradient(ndi.gaussian_filter(Do, 12.0)); wy = _n(sh, 90, rng); wx = _n(sh, 90, rng)
    for cy, cx in heads:
        y, x0_ = float(cy), float(cx)
        for _ in range(4000):
            iy, ix = int(round(y)), int(round(x0_))
            if not (0 <= iy < sh[0] and 0 <= ix < sh[1]) or Dg[iy, ix] > rc[iy, ix] + 160.0: break
            path[iy, ix] = True; g = np.hypot(gy[iy, ix], gx[iy, ix])
            if g < 1e-4: break
            y += 2.0 * (gy[iy, ix] / g + 0.5 * wy[iy, ix]); x0_ += 2.0 * (gx[iy, ix] / g + 0.5 * wx[iy, ix])
        y, x0_ = float(cy), float(cx)                                       # and out across the shelf: the trough the glacier cut
        for _ in range(4000):
            iy, ix = int(round(y)), int(round(x0_))
            if not (0 <= iy < sh[0] and 0 <= ix < sh[1]) or Do[iy, ix] > 150.0: break
            trough[iy, ix] = True
            if Dg[iy, ix] > 0: g = -np.hypot(gy[iy, ix], gx[iy, ix]); vy_, vx_ = gy[iy, ix], gx[iy, ix]
            else: g = np.hypot(gyo[iy, ix], gxo[iy, ix]); vy_, vx_ = gyo[iy, ix], gxo[iy, ix]
            if abs(g) < 1e-4: break
            y += 2.0 * vy_ / g; x0_ += 2.0 * vx_ / g
    dv = (ndi.distance_transform_edt(~path) * KM).astype(np.float32) if path.any() else np.full(sh, 1e4, np.float32)
    dv = dv + 4.0 * _n(sh, 20, rng)
    PLAT = 1650.0
    floor = 20.0 + (PLAT - 120.0) * _ss(Dg / (rc + 30.0)) ** 1.4               # the outlet glacier, falling from the plateau to its fjord
    gw = 30.0 + 12.0 * _n(sh, 120, rng)
    u = np.exp(-(np.maximum(dv, 0) / np.maximum(gw, 16.0)) ** 3)           # broad, flat-floored ice tongues
    z = z * (1 - u) + np.minimum(z, floor) * u
    log("    glacier gaps through the Wall: %d, at fjords %s km deep behind the coast" % (len(heads), [int(Dg[p]) for p in heads]))
    mo = np.zeros(sh, bool)
    for cy, cx in heads:
        q = np.argwhere(path & (np.abs(x - (-0.55 * rc)) < 3.0))
        if len(q): q = q[np.argmin((q[:, 0] - cy) ** 2 + (q[:, 1] - cx) ** 2)]; mo[q[0], q[1]] = True
    if mo.any():
        dm = (ndi.distance_transform_edt(~mo) * KM).astype(np.float32) + 3.0 * _n(sh, 10, rng)
        z = z + P * (55.0 * np.exp(-((dm - 34.0) / 4.5) ** 2) + 35.0 * np.exp(-((dm - 48.0) / 4.0) ** 2)) * _ss((-x - 20.0) / 20.0) * (1 - u)
    log("    end moraines at %d gap mouths" % int(mo.sum()))
    # the outer face drains to the sea; the inner face is under ice
    z = _valleys(z, P & (x < 45.0) & (z > 150.0), water, KM, rng, S=1, keep=0.16, side=380.0, trunk=900.0, weight=P * _ss((45.0 - x) / 30.0), log=log)
    # raised beaches: the lowland next to the sea stands in steps
    t = z / 22.0; step = 22.0 * (np.floor(t) + _ss((t - np.floor(t) - 0.7) / 0.3))
    tw = P * _ss((30.0 - Dw) / 15.0) * _ss((170.0 - z) / 40.0) * _ss(0.4 + 0.6 * _n(sh, 90, rng))
    z = z + 0.7 * tw * (step - z)
    # the ice plateau: 200-800 m, broad and smooth, lower toward the gaps the ice leaves by, drained through them
    icem = P & (x > -4.0)
    # the plateau: Greenland's ice sheet laid over the interior (user, 15 Nov 2026), its domes, divides and streams, with its
    # heights brought to the plateau's, 1,350-2,450 m; beyond Greenland's edge, its edge carried on at about 1,000 m
    interior = P & (x > 25.0)
    HG, wG = _fit_greenland(interior, KM, log); gG = wG > 0.5; wG = _ss((wG - 0.2) / 0.6)
    dG, (iy, ix) = ndi.distance_transform_edt(~gG, return_indices=True)
    hg = wG * HG + (1 - wG) * (1000.0 + (np.maximum(HG[iy, ix], 1000.0) - 1000.0) * np.exp(-dG * KM / 250.0) + 70.0 * _n(sh, 80, rng)); del dG, iy, ix
    ice = 1350.0 + (np.maximum(hg, 600.0) - 1000.0) * 0.5 + 8.0 * _n(sh, 25, rng)
    log("    plateau on Greenland's ice: %.1f%%, carried on from its edge: %.1f%%" % (100 * (gG & interior).sum() / interior.sum(), 100 * (~gG & interior).sum() / interior.sum()))
    # ranges buried under the ice: belts of wavy surface along meandering lines, peaks breaking through; basins as smooth lows
    br = _n(sh, 650, rng); br2 = _n(sh, 500, rng)
    belt = np.maximum(np.exp(-(br / 0.14) ** 2), np.exp(-(br2 / 0.11) ** 2) * _ss((_n(sh, 400, rng) + 0.2) / 0.6)) * _ss((x - 40.0) / 60.0)
    ice = ice + belt * (100.0 * (0.6 + 0.4 * _n(sh, 30, rng)) + 45.0 * _n(sh, 9, rng))
    bas = _ss((-_n(sh, 480, rng) - 1.0) / 0.6); ice = ice - 170.0 * bas
    ice = ice - 420.0 * np.exp(-np.maximum(dv, 0) / 140.0) * _ss((rc + 260.0 - Dg) / 120.0)   # drawn down toward the gaps
    # the katabatic wind blows downslope and southeast (image down-right); dunes form across it
    sm = ndi.gaussian_filter(ice, 30.0); gy2, gx2 = np.gradient(sm); g2 = np.maximum(np.hypot(gy2, gx2), 1e-6)
    wy = 0.6 * np.sqrt(0.5) - 0.4 * gy2 / g2; wx = 0.6 * np.sqrt(0.5) - 0.4 * gx2 / g2; wn = np.maximum(np.hypot(wy, wx), 1e-6); del sm, gy2, gx2, g2
    ice = _ice_surface(ice, icem, (u > 0.5) & icem & (x > 20.0), KM, rng, log, trunk=2500.0, keep=0.9, wind=(wy / wn, wx / wn))
    # bare rock: in the lows, where summer melt strips the ice off, rough and pitted ground
    lowness = _ss((ndi.gaussian_filter(ice, 60.0) - ice - 20.0) / 60.0) + 0.6 * bas
    bare = _ss((_n(sh, 70, rng) - 0.2) / 0.5) * _ss(1.5 * lowness) * interior
    ice = ice * (1 - bare) + (ice - 50.0 + 75.0 * _ridged(sh, 5, rng) + 35.0 * _n(sh, 3, rng) - 25.0 * _ss((_n(sh, 4, rng) - 1.0) / 0.4)) * bare
    ice = ice * _ss((x + 4.0) / 16.0)
    # nunataks: the tops of buried mountains, in rows along the buried ranges and in clusters behind the Wall
    nk = np.zeros(sh, np.float32); cl = _ss((_n(sh, 80, rng) - 0.3) / 0.6)
    bgy, bgx = np.gradient(ndi.gaussian_filter(np.where(np.abs(br) < np.abs(br2), br, br2), 20.0)); orient = np.arctan2(bgy, bgx) + np.pi / 2 + 0.5 * _n(sh, 150, rng)   # along the range
    pr = np.where(interior, 0.008 * _ss((belt - 0.4) / 0.4) + 0.0012 * cl * _ss((x - 15.0) / 20.0) * _ss((260.0 - x) / 100.0), 0)
    cand = np.argwhere(rng.random(sh) < pr); rng.shuffle(cand); npk = 0; pks = []
    for cy, cx in cand[:12000]:
        if npk >= 1400: break
        if any((cy - py) ** 2 + (cx - px) ** 2 < (9.0 / KM) ** 2 for py, px in pks[-60:]): continue
        pks.append((cy, cx)); h = 90.0 + rng.pareto(2.2) * 260.0 * (1.3 if belt[cy, cx] > 0.5 else 1.0); h = min(h, 1400.0)
        _cone(nk, cy, cx, h, h / 1000.0 * rng.uniform(7.0, 13.0) + 3.0, 0.0, False, KM, aspect=rng.uniform(1.3, 3.2), ang=float(orient[cy, cx])); npk += 1
    nk = nk * (0.8 + 0.2 * _ridged(sh, 3, rng)) + 30.0 * _n(sh, 2, rng) * _ss(nk / 100.0)
    z = np.maximum(z, ice + nk)
    # geothermal ground along the plateau's edge: ice cauldrons over buried vents, and volcanoes standing out of the ice
    zone = np.argwhere(interior & (x > 20.0) & (x < 230.0)); rng.shuffle(zone); nc = nv = 0; spots = []
    for cy, cx in zone[:5000]:
        if nc >= 24 and nv >= 11: break
        if any((cy - py) ** 2 + (cx - px) ** 2 < (45.0 / KM) ** 2 for py, px in spots): continue
        spots.append((cy, cx))
        if nv < 11 and rng.random() < 0.35:
            h = rng.uniform(500.0, 1300.0); _cone(z, cy, cx, h, h / 1000.0 * rng.uniform(14.0, 20.0), 0.1, rng.random() < 0.4, KM); nv += 1
        elif nc < 24:
            R = rng.uniform(4.0, 9.0); d = rng.uniform(60.0, 220.0); rp = int(R / KM) + 2
            y0, y1, x0, x1 = max(cy - rp, 0), min(cy + rp + 1, sh[0]), max(cx - rp, 0), min(cx + rp + 1, sh[1])
            yy, xx = np.mgrid[y0:y1, x0:x1]; r = np.hypot(yy - cy, xx - cx) * KM / R
            z[y0:y1, x0:x1] -= d * np.clip(1.0 - r * r, 0, 1) ** 1.5; nc += 1
    log("    plateau: %.1f%% over buried ranges, %.1f%% over buried basins, %.1f%% bare rock, %d nunataks, %d ice cauldrons, %d volcanoes through the ice"
        % (100 * ((belt > 0.5) & interior).sum() / interior.sum(), 100 * ((bas > 0.5) & interior).sum() / interior.sum(), 100 * ((bare > 0.5) & interior).sum() / interior.sum(), npk, nc, nv))
    m = float(z[P].max())                                                    # the highest summit is 4,187 m
    if m > 3000.0: z = np.where(z > 3000.0, 3000.0 + (z - 3000.0) * (1187.0 / (m - 3000.0)), z)
    # offshore: deep fjords behind shallow sills, the glaciers' troughs across the shelf, the trench the arc stands over
    fjd = (300.0 + 900.0 * _ss(Dg / 45.0)) * (0.8 + 0.2 * _n(sh, 30, rng)) * fj
    dtr = (ndi.distance_transform_edt(~trough) * KM).astype(np.float32) if trough.any() else np.full(sh, 1e4, np.float32)
    trd = (700.0 + 200.0 * _n(sh, 60, rng)) * np.exp(-((dtr + 3.0 * _n(sh, 15, rng)) / 16.0) ** 2) * _ss((160.0 - Do) / 40.0)
    Lb = ndi.gaussian_filter(land.astype(np.float32), 140) > 0.35; Db = (ndi.distance_transform_edt(~Lb) * KM).astype(np.float32)
    ta = 150.0 + 35.0 * np.clip(_n(sh, 500, rng), -1.6, 1.6)               # an arc, not a copy of the coastline
    seg = _ss(0.75 + 0.6 * _n(sh, 260, rng))                               # deep in some stretches, shoaling in others
    trench = (6200.0 + 1500.0 * seg) * np.exp(-0.5 * ((Db - ta) / (34.0 + 14.0 * seg)) ** 2) * _ss((Do - 50.0) / 60.0)
    sea = np.maximum(np.maximum(trench, fjd), trd)
    return np.maximum(z, 5.0), np.where(water, sea, 0).astype(np.float32)

ANT_KM = 1.75                         # Antarctica is reprojected at the pipeline's own scale
ANT_HALF = 2000                       # cells from the pole to the grid's edge: 3,500 km, past every coast

def _antarctic_grid(log, south=True):
    """ETOPO 2022 60s surface poleward of 58 degrees on a polar stereographic grid in true km. South: the Antarctic ice
    sheet as it stands, its mountains, and the floating shelves, which sit lower than grounded ice. North: the Arctic,
    Greenland's ice sheet in it."""
    import os, rasterio
    from rasterio.windows import Window
    here = os.path.dirname(os.path.abspath(__file__)); data = os.path.join(os.path.dirname(here), "data", "etopo")
    with rasterio.open(os.path.join(data, "ETOPO_2022_v1_60s_N90W180_surface.tif")) as ds:
        r0 = int(round((90 + 58) * 60)) if south else 0; nr = ds.height - r0 if south else int(round(32 * 60))
        E = ds.read(1, window=Window(0, r0, ds.width, nr)).astype(np.float32)
    n = 2 * ANT_HALF; yy, xx = np.mgrid[:n, :n].astype(np.float32); X = (xx - ANT_HALF + 0.5) * ANT_KM; Y = (yy - ANT_HALF + 0.5) * ANT_KM; del yy, xx
    R = 6371.0; c = np.degrees(2 * np.arctan(np.hypot(X, Y) / (2 * R))); lon = np.degrees(np.arctan2(X, -Y)); del X, Y
    row = (32.0 - c) * 60 - 0.5 if south else c * 60 - 0.5; del c
    H = ndi.map_coordinates(E, [row, ((lon + 180.0) * 60 - 0.5) % E.shape[1]], order=1, mode="nearest").astype(np.float32)
    log("    %s: ETOPO 2022 surface on a %dx%d polar grid at %.2f km, highest %.0f m" % ("Antarctica" if south else "the Arctic", n, n, ANT_KM, float(H.max())))
    return H

def _place(A, shape, f, ck, mir, s, th, sy, sx, ny, nx, order, cval):
    """sample A (Antarctic grid) for every cell of `shape`, a grid f times finer than the search's"""
    yy, xx = np.mgrid[:shape[0], :shape[1]].astype(np.float32)
    py = (yy / f + sy - ny) * ck * s; px = (xx / f + sx - nx) * ck * s; del yy, xx
    if mir: px = -px
    ax = np.cos(th) * px - np.sin(th) * py; ay = np.sin(th) * px + np.cos(th) * py; del px, py
    return ndi.map_coordinates(A, [ay / ANT_KM + ANT_HALF, ax / ANT_KM + ANT_HALF], order=order, mode="constant", cval=cval).astype(np.float32)

def _search(A, T, KM, f, mirs, scales, angles):
    """the rotation, mirror, scale and shift putting most of Antarctica's grounded ice on Tartarus's land and its sea on
    Tartarus's sea, scored over the crop (beyond the map's corner Tartarus is not drawn)"""
    Tc = T[::f, ::f].astype(np.float32) * 2 - 1; ny, nx = Tc.shape; ck = KM * f; G = None; best = (-1e18,)
    py0, px0 = np.mgrid[-ny:2 * ny, -nx:2 * nx].astype(np.float32) * ck
    for mir in mirs:
        for s in scales:
            for th in angles:
                py, px = py0 * s, px0 * s * (-1 if mir else 1)
                ax = np.cos(th) * px - np.sin(th) * py; ay = np.sin(th) * px + np.cos(th) * py
                C = ndi.map_coordinates(A, [ay / ANT_KM + ANT_HALF, ax / ANT_KM + ANT_HALF], order=0, mode="constant", cval=-1.0)
                if G is None: G = np.fft.rfft2(Tc[::-1, ::-1], C.shape)
                corr = np.fft.irfft2(np.fft.rfft2(C) * G, C.shape)[ny - 1:2 * ny + ny - 1, nx - 1:2 * nx + nx - 1]
                k = int(np.argmax(corr)); dy, dx = divmod(k, corr.shape[1]); sc = float(corr.flat[k]) / Tc.size
                if sc > best[0]: best = (sc, mir, float(s), float(th), dy, dx)
    return best

def _fit_antarctica(T, KM, log):
    H = _antarctic_grid(log)
    return _fit_ref(H, (H > 100.0), T, KM, log, "tartarus_fit.npy", np.arange(0.55, 1.26, 0.05), "Antarctica", "Tartarus")   # grounded ice; the shelves sit lower

def _fit_greenland(T, KM, log):
    """Greenland's ice sheet, the largest body of ground above 1,000 m in the Arctic"""
    H = _antarctic_grid(log, south=False); lab, _ = ndi.label(H > 1000.0); big = np.bincount(lab.ravel())[1:].argmax() + 1
    return _fit_ref(H, lab == big, T, KM, log, "hyperborea_fit.npy", np.arange(0.25, 0.71, 0.05), "Greenland", "Hyperborea's plateau")

def _fit_ref(H, mask, T, KM, log, cachename, scales, what, onto):
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from common import WORK
    cache = os.path.join(WORK, cachename); A = mask.astype(np.float32) * 2 - 1
    if os.path.exists(cache): sc, mir, s, th, f = [float(v) for v in np.load(cache)[:5]]; dy, dx = np.load(cache)[5:].astype(int)
    else:
        b = _search(A, T, KM, 8, (False, True), scales, np.radians(np.arange(0, 360, 5)))
        b = _search(A, T, KM, 4, (b[1],), np.arange(b[2] - 0.04, b[2] + 0.041, 0.02), np.arange(b[3] - np.radians(4), b[3] + np.radians(4.1), np.radians(1)))
        sc, mir, s, th, dy, dx = b; f = 4.0; np.save(cache, np.array([sc, float(mir), s, th, f, dy, dx]))
    f = int(f); ny, nx = T[::f, ::f].shape
    log("    %s laid over %s: agreement %.2f, turned %.0f deg%s, scale %.2f" % (what, onto, sc, np.degrees(th) % 360, ", mirrored" if mir else "", s))
    Hf = _place(H, T.shape, f, KM * f, bool(mir), s, th, dy, dx, ny, nx, 3, -3000.0)
    Hf = ndi.gaussian_filter(Hf, max(0.6 / s - 0.5, 0.0))                      # magnified, the source's cells would show as facets
    return Hf, ndi.gaussian_filter(_place(mask.astype(np.float32), T.shape, f, KM * f, bool(mir), s, th, dy, dx, ny, nx, 1, 0.0), max(0.6 / s - 0.5, 0.0))

def _tartarus(land, P, KM, rng, centre, log):
    sh = land.shape; water = ~land
    Lsm, Dg, Do = _coast_fields(land, KM)
    yy, xx = np.mgrid[:sh[0], :sh[1]].astype(np.float32); cy, cx = centre
    th = np.arctan2(yy - cy, xx - cx); rpx = np.hypot(yy - cy, xx - cx) * (1.0 + 0.05 * _n(sh, 160, rng)) + 16.0 * _n(sh, 45, rng); del yy, xx
    # crest radius px, scarp height m, width px: the three rings in the drawing and two more out on the land
    RINGS = ((380.0, 1500.0, 30.0), (600.0, 1350.0, 40.0), (1120.0, 1200.0, 55.0), (1650.0, 750.0, 70.0), (2300.0, 380.0, 90.0))
    rings = np.zeros(sh, np.float32)
    for rk, ak, wk in RINGS:                                                # inward-facing scarps: steep inside, long slope out
        q = rpx - rk; rings += ak * np.exp(-0.5 * (q / np.where(q < 0, 0.4 * wk, 1.4 * wk)) ** 2)
    rings *= (0.6 + 0.4 * _ridged(sh, 20, rng)) * (0.75 + 0.25 * _ss(0.6 + 0.5 * _n(sh, 140, rng)))
    rings += 70.0 * (_ridged(sh, 6, rng) - 0.4) * _ss(rings / 300.0)
    cw = _ss(1.0 - rpx / 280.0) ** 0.6
    central = cw * (1700.0 * (0.55 + 0.45 * _ridged(sh, 24, rng)) + 400.0 * _n(sh, 60, rng)) + 70.0 * cw * (_ridged(sh, 6, rng) - 0.4)
    ang = rng.uniform(-np.pi, np.pi, 7); frac = np.zeros(sh, np.float32)
    thw = th + 0.10 * _n(sh, 380, rng) + 0.03 * _n(sh, 90, rng)            # fractures wander, widen and die out
    wid = 32.0 + 22.0 * _n(sh, 300, rng)
    for a in ang:
        da = np.angle(np.exp(1j * (thw - a))); dp = rpx * np.abs(np.sin(da)) * KM; r1 = rng.uniform(1600.0, 3600.0)
        frac = np.maximum(frac, np.exp(-(dp / np.maximum(wid, 22.0)) ** 2) * (np.cos(da) > 0) * _ss((rpx - 300.0) / 300.0) * _ss((r1 - rpx) / 900.0))
    del th, thw, wid
    low = 30.0 + 110.0 * _ss(Dg / 45.0) + 25.0 * _n(sh, 18, rng) + 15.0 * _n(sh, 5, rng)
    rock = low + rings + central - 350.0 * frac
    rock = _valleys(rock, P & (rock > 200.0), water, KM, rng, keep=0.25, side=700.0, log=log)
    # the ice sheet is Antarctica's (user, 15 Nov 2026: "You COULD grab some Antarctic terrain for Tartarus"), laid over
    # Tartarus where the two outlines agree best; Tartarus land over Antarctic sea or shelf takes the nearest grounded
    # ground, fading, and everything comes down to Tartarus's own coast
    HA, wA = _fit_antarctica(land, KM, log); gA = wA > 0.5
    dA, (iy, ix) = ndi.distance_transform_edt(~gA, return_indices=True)
    ice = np.where(gA, HA, HA[iy, ix] * np.exp(-dA * KM / 220.0) + 120.0 * _n(sh, 40, rng)); del dA, iy, ix
    wl, _ = ndi.label(water); edge = np.unique(np.concatenate([wl[0], wl[-1], wl[:, 0], wl[:, -1]]))
    sea = np.isin(wl, edge[edge > 0]); del wl                               # lakes take their own level in terrain.py
    dco = (ndi.distance_transform_edt(~sea) * KM).astype(np.float32)
    ice = np.maximum(ice, 0) * _ss((dco + 6.0 * _n(sh, 30, rng)) / 45.0)
    log("    Tartarus land on Antarctica's grounded ground: %.1f%%, filled from the nearest: %.1f%%" % (100 * (gA & P).sum() / P.sum(), 100 * (~gA & P).sum() / P.sum()))
    # the ground under it shows through, softened: the rings and fractures as steps and troughs; thin over the Rift's heat
    ice = ice + 0.4 * ndi.gaussian_filter(rings, 4.0) - 200.0 * ndi.gaussian_filter(frac, 14.0)
    ice = np.maximum(ice, 0) * (0.2 + 0.8 * _ss((rpx - 720.0) / 420.0))
    z = np.maximum(rock, ice)
    log("    ice to %.0f m, %d rings, %d fractures from the Rift" % (float(ice[P].max()), len(RINGS), len(ang)))
    # the Rift's water: a deep moat round the central island, troughs between the arcs, each ring a ridge joining its islands
    g = lambda r0, w: np.exp(-0.5 * ((rpx - r0) / w) ** 2)
    T = 4000.0 + 2600.0 * g(300.0, 42.0) + 1300.0 * g(490.0, 60.0) + 700.0 * g(860.0, 110.0)
    crest = np.zeros(sh, np.float32)
    for rk, ak, wk in RINGS[:3]: crest = np.maximum(crest, np.exp(-0.5 * ((rpx - rk) / (0.75 * wk)) ** 2))
    T = T * (1.0 - 0.8 * crest * (0.8 + 0.2 * _ridged(sh, 25, rng)))
    T = T * (0.88 + 0.12 * _n(sh, 120, rng)) + 200.0 * _n(sh, 30, rng)
    vents = np.zeros(sh, np.float32); cand = np.argwhere(water & (T > 3800.0) & (rpx < 1300.0)); rng.shuffle(cand); nv = 0
    for vy_, vx_ in cand[:2000]:
        if nv >= 80: break
        _cone(vents, vy_, vx_, rng.uniform(150.0, 550.0), rng.uniform(4.0, 10.0), 0.15, False, KM); nv += 1
    T = T - vents
    dl = (ndi.distance_transform_edt(water) * KM).astype(np.float32)
    T = np.maximum(T, 0) * _ss((1500.0 - rpx) / 300.0) * _ss(dl / np.clip(28.0 + 18.0 * _n(sh, 90, rng), 8.0, 60.0))
    log("    Rift floor: %d hydrothermal vent cones" % nv)
    return np.maximum(z, 5.0), np.where(water, T, 0).astype(np.float32)

# crops of the 12000 grid, and which of their land is the continent: the corners hold the poles
REGIONS = (("Hyperborea", slice(0, 3400), slice(0, 3400), lambda yy, xx: yy + xx < 6000),
           ("Tartarus", slice(7800, 12000), slice(9000, 12000), lambda yy, xx: yy + xx > 17000))
RIFT = (10392, 11320)                 # the Rift's central island, 12000 grid (row, col), measured from the drawing

def build(land, has, KM, seed=23, log=print):
    out = []; polar_all = 0
    for name, rs, cs, corner in REGIONS:
        rng = np.random.default_rng(seed + len(out)); L = land[rs, cs]; yy, xx = np.mgrid[rs, cs]
        P = L & ~has[rs, cs] & corner(yy, xx); del yy, xx; polar_all += int(P.sum())
        log("  %s: %d px of land with nothing under it" % (name, int(P.sum())))
        if name == "Hyperborea": z, sea = _hyperborea(L, P, KM, rng, log)
        else: z, sea = _tartarus(L, P, KM, rng, (RIFT[0] - rs.start, RIFT[1] - cs.start), log)
        log("    land %.0f-%.0f m, median %.0f | sea floor set to at least %.0f m" % (float(z[P].min()), float(z[P].max()), float(np.median(z[P])), float(sea.max())))
        out.append((rs, cs, P, z.astype(np.float32), sea))
    rest = int((land & ~has).sum()) - polar_all
    log("  land with nothing under it outside the poles, left at the placeholder: %d px" % rest)
    return out

if __name__ == "__main__":
    # preview: the finished heights with the polar ground swapped in -> argv[1] (int16, 12000 grid)
    import sys, os, time
    sys.path.insert(0, os.path.dirname(__file__)); from common import WORK
    t0 = time.time(); land = np.load(os.path.join(WORK, "land12k.npy")); has = np.load(os.path.join(WORK, "ehas_adj.npy"))
    H = np.load(os.path.join(WORK, "height_raw.npy")).astype(np.int16)
    for rs, cs, P, z, sea in build(land, has, 1.75):
        Hc = H[rs, cs]; Hc[P] = np.round(z[P]).astype(np.int16); w = ~land[rs, cs]
        Hc[w] = np.minimum(Hc[w], -np.round(sea[w]).astype(np.int16)); H[rs, cs] = Hc
    np.save(sys.argv[1], H); print("preview written", round(time.time() - t0), "s")
