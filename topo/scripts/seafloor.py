"""The floor of every body of water on the map. The Avium article gives the inventory: continental shelves and shelf seas,
abyssal plains, seamounts and submarine volcanoes, trenches, canyons, oceanic plateaus and a planet-spanning mid-ocean ridge.
Nothing here is carried over from Earth's oceans: a real floor brings real islands with it, and Avium already has those as land.
- Open ocean: generated, and from noise, never from cells or from distances between points (those came out as rings and as a
  honeycomb). The ridge is where a broad field of noise changes sign. The crust sinks as it ages away from the crest. Fracture
  zones are noise smeared along the spreading direction, abyssal hills fine noise smeared the other way, and near the continents
  sediment buries both. On top: a few plateaus, scattered seamounts in provinces, and chains of volcanoes. Every group of small
  Avium islands standing out in the ocean is the young end of such a chain, which runs on from its smaller islands.
- Enclosed and marginal seas: how deep a sea can be follows from how wide it is at that place (the half-width field), so a
  strait is a sill, a gulf is shallower than the sea it opens on, and a wide sea has deep basins parted by rises. Sunk real land
  (the Sahara, Greenland, the western Amazon) keeps its relief: that ground is on the overlay, so it is that real place.
- Continental margins: the shelf is wide off low coasts and in embayments, narrow off mountains and capes, and never a fixed
  band; its edge wanders and is notched by canyon heads. A high coast on open ocean is an active margin with a trench.
- Islands: a small island is a volcano. It has almost no shelf and falls straight to the deep floor; islands in a chain or a
  cluster stand on a shared ridge. Only a large island carries a shelf of its own, in proportion to its size.
- Lakes: a bowl as deep as the lake is wide allows.
Everything is seeded: the same map gives the same floor."""
import os, numpy as np
from scipy import ndimage as ndi
SHELF_MED, SHELF_SPREAD = 9.0, 2.3        # shelf width: median in km, and the spread of its logarithm
def _noise(n, scales, rng):
    out = np.zeros((n, n), np.float32)
    for s, a in scales:
        g = ndi.gaussian_filter(rng.standard_normal((n, n)).astype(np.float32), s); out += a * g / (g.std() + 1e-9)
    return out / np.abs(out).max()
def _ss(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
def _up(a, rows, N):
    k = N // a.shape[0]; yy = (rows + 0.5) / k - 0.5; xx = (np.arange(N) + 0.5) / k - 0.5
    return ndi.map_coordinates(a, np.meshgrid(yy, xx, indexing="ij"), order=1, mode="nearest")
def _edt(mask, scale): return (ndi.distance_transform_edt(mask) * scale).astype(np.float32)

def _lf(n, s, rng):
    """smooth noise with a grain of s cells, within -1..1: made small and stretched, since nothing in it is finer than s"""
    f = max(int(s // 6), 1); k = n // f + 3; g = ndi.gaussian_filter(rng.standard_normal((k, k)).astype(np.float32), s / f)
    yy = (np.arange(n) + 0.5) / f; g = ndi.map_coordinates(g, np.meshgrid(yy, yy, indexing="ij"), order=1, mode="nearest"); return g / np.abs(g).max()

def _lic(texs, vy, vx, steps, h=1.5):
    """Smear textures along a direction field (line integral convolution): what is left of each runs in streaks down the field."""
    n = vy.shape[0]; gy, gx = np.mgrid[:n, :n].astype(np.float32); acc = [t.copy() for t in texs]; ws = 1.0
    for sg in (1.0, -1.0):
        py, px = gy.copy(), gx.copy()
        for k in range(1, steps + 1):
            dy = ndi.map_coordinates(vy, [py, px], order=1, mode="nearest"); dx = ndi.map_coordinates(vx, [py, px], order=1, mode="nearest")
            py += sg * h * dy; px += sg * h * dx; w = 0.5 + 0.5 * np.cos(np.pi * k / (steps + 1)); ws += w
            for a, t in zip(acc, texs): a += w * ndi.map_coordinates(t, [py, px], order=1, mode="nearest")
    return [(a / ws - (a / ws).mean()) / (a / ws).std() for a in acc]

def _deep(Wc, Gm, dkg, wo, mainreg, isl, active, n4, ck, seed, log):
    """The deep floor, generated on the coarse grid. -> zt: depth in m were no coast near; de: km from the ridge crest; rw: how rough;
    ax: how much of an axial valley; mounts: volcanoes to stand on it"""
    n = Wc.shape[0]; rng = np.random.default_rng(seed + 7)
    # Nothing here is constructed from distances between points or from cells: every such construction came out regular (a ridge
    # ringing the continent, fracture zones fanning from corners, plates as a honeycomb of bowls). The big shapes are noise.
    # The ridge is where a broad field of noise changes sign: a few long lines wandering across the ocean, owing nothing to the land.
    phi = _lf(n, 380, rng) + 0.25 * _lf(n, 160, rng); sgp = phi > 0; del phi
    zc = np.zeros((n, n), bool); zc[:, 1:] |= sgp[:, 1:] != sgp[:, :-1]; zc[1:] |= sgp[1:] != sgp[:-1]
    zl, kz = ndi.label(zc, structure=np.ones((3, 3))); zs = np.bincount(zl.ravel()); zc &= (zs >= 500)[zl]; del zl               # no ridge short enough to close into a ring
    nr = (np.where(sgp, 1.0, -1.0) * _edt(~zc, ck)).astype(np.float32) if zc.any() else np.full((n, n), 9e4, np.float32); del zc, sgp          # km from the ridge, signed by side
    live = np.ones((n, n), np.float32)
    # a narrow ocean between two great land masses opened between them: there the ridge runs down the middle, and dies where it is a strait
    lab, k = ndi.label(ndi.binary_dilation(Gm, iterations=int(150 / ck))); area = np.bincount(lab.ravel()) * ck * ck; area[0] = 0
    ids = [int(i) for i in np.argsort(-area) if area[i] >= 3e6]
    if len(ids) > 1:
        D = np.stack([_edt(~(Gm & (lab == i)), ck) for i in ids]); o = np.argsort(D, 0)[:2]; c1 = np.take_along_axis(D, o[:1], 0)[0]; c2 = np.take_along_axis(D, o[1:2], 0)[0]; del D
        ch = _ss((2300 - (c1 + c2) / 2) / 800); nr = (ch * np.where(o[0] < o[1], 1.0, -1.0) * (c2 - c1) / 2 + (1 - ch) * nr).astype(np.float32)
        live = (1 - ch + ch * _ss(((c1 + c2) / 2 - 250) / 450)).astype(np.float32); del o, c1, c2, ch
    del lab
    live = (live * _ss((dkg - 200) / 500)).astype(np.float32)                                      # a ridge fades out as it nears a continent
    sed = 1 - _ss((dkg - 150) / 650)                                                              # sediment off the continents buries the grain: abyssal plains
    # the grain. Crust moves away from the ridge, so everything it carries is smeared along that direction: two fields of noise drawn
    # out into streaks. The broad one sets each stretch of ridge off sideways from the next, which leaves a step in age all the way
    # down the streak: a fracture zone, as irregular as the noise it came from. The fine one is the lesser lineation beside it.
    uy, ux = np.gradient(ndi.gaussian_filter(nr, 25.0)); um = np.maximum(np.hypot(uy, ux), 1e-6); uy /= um; ux /= um; del um
    n2 = n // 2; S1, S2 = _lic([ndi.gaussian_filter(rng.standard_normal((n2, n2)).astype(np.float32), 5.0), ndi.gaussian_filter(rng.standard_normal((n2, n2)).astype(np.float32), 1.5)],
                               np.ascontiguousarray(uy[::2, ::2]), np.ascontiguousarray(ux[::2, ::2]), 60)
    yy = (np.arange(n) + 0.5) / 2 - 0.5; S1, S2 = (ndi.map_coordinates(a, np.meshgrid(yy, yy, indexing="ij"), order=1, mode="nearest") for a in (S1 + 0.85 * (np.round(1.6 * S1) / 1.6 - S1), S2))
    off = (110 * np.clip(S1, -1.5, 1.5)).astype(np.float32); del S1                                          # km the crest is set off, the same all the way down a streak
    de = np.abs(nr - off).astype(np.float32); age = de / 32.0                                      # million years, at 32 km a million years each side
    z = 2600 + 3300 * (1 - np.exp(-np.sqrt(age) / 6.0))                                           # crust sinks as it cools
    z = 5300 + live * (z - 5300) + 240 * _lf(n, 90, rng)
    fzw = live * (1 - 0.8 * sed) * (0.15 + 0.85 * np.exp(-np.abs(nr) / 800.0))
    z += fzw * (300 * _ss(np.hypot(*np.gradient(off)) / 25.0) * (0.6 + 0.4 * np.clip(S2, -1.5, 1.5)) - 140 * S2); del off, S2, fzw     # a trough where the step is, lineations beside it
    # abyssal hills: fine noise drawn out the other way, along the ridge
    hills = _lic([ndi.gaussian_filter(rng.standard_normal((n, n)).astype(np.float32), 0.8)], -ux, uy, 5, 1.0)[0]; del uy, ux
    # plateaus: a few broad, rough-topped rises on older floor
    pl = _lf(n, 50, rng) + 0.5 * _lf(n, 16, rng) + 0.3 * _lf(n, 5, rng) + 0.15 * _lf(n, 2, rng); pl /= pl.std(); plat = _ss((pl - 1.5) / 0.7) * _ss((age - 8) / 20) * wo; dome = 0.55 + 0.45 * _ss((pl - 1.5) / 1.5); del pl
    z -= plat * dome * (2800 * (0.7 + 0.3 * _lf(n, 8, rng)) + 170 * _lf(n, 3, rng))
    # volcanoes: (row, column) in coarse cells, height m, base radius km, the shallowest its top may stand (m), lobes, phase
    mounts = []; okc = Wc & mainreg & (dkg > 300) & (active < 0.2); gy, gx = np.gradient(ndi.gaussian_filter(np.abs(nr), 6.0)); trail = np.zeros((n, n), np.float32)
    def mount(y, x, h, cap): mounts.append((float(y), float(x), float(h), float(h / 1000 * rng.uniform(11, 17)), float(cap), int(rng.integers(2, 5)), float(rng.uniform(0, 6.28))))
    def chain(y, x, a, length, h0):
        """a line of volcanoes from (y, x) on heading a, close enough to stand on one ridge: the further along, the older and lower"""
        s_ = 0.0; bend = rng.uniform(0.4, 0.7) * length if rng.random() < 0.6 else 9e9; turn = rng.choice([-1.0, 1.0]) * rng.uniform(0.4, 1.0)
        while s_ < length:
            st = rng.uniform(28, 55); s_ += st
            if s_ > bend: a += turn; bend = 9e9
            a += rng.normal(0, 0.05); y += np.sin(a) * st / ck; x += np.cos(a) * st / ck; iy, ix = int(y), int(x)
            if not (0 <= iy < n and 0 <= ix < n) or dkg[iy, ix] < 300 or not mainreg[iy, ix] or active[iy, ix] > 0.2: break
            trail[iy, ix] += 1; mount(y + rng.normal(0, 10 / ck), x + rng.normal(0, 10 / ck), h0 * np.exp(-1.2 * s_ / length) * rng.uniform(0.35, 1.15), rng.uniform(150, 500) + 1400 * s_ / length)
    # every group of small Avium islands out in the ocean is the young end of a chain: it runs on from the end with the smaller islands
    gl, kg = ndi.label(ndi.binary_dilation(isl > 0.02, iterations=6)); grown = 0
    for i, sl in enumerate(ndi.find_objects(gl), 1):
        yy, xx = np.nonzero((gl[sl] == i) & (isl[sl] > 0.02)); yy = yy + sl[0].start; xx = xx + sl[1].start; w = isl[yy, xx].astype(np.float64); cy, cx = (yy * w).sum() / w.sum(), (xx * w).sum() / w.sum()
        if dkg[int(cy), int(cx)] < 350 or not mainreg[int(cy), int(cx)]: continue
        ev, evec = np.linalg.eigh(np.cov(np.stack([yy - cy, xx - cx]), aweights=w) + 1e-6 * np.eye(2)) if len(yy) > 2 else (np.array([1.0, 1.0]), np.eye(2))
        if ev[1] > 9 * ev[0] and np.sqrt(ev[1]) * ck > 25:                                         # a line of islands: on from its lighter end
            ax_ = evec[:, 1]; t = (yy - cy) * ax_[0] + (xx - cx) * ax_[1]; sg = -1.0 if w[t > 0].sum() > w[t < 0].sum() else 1.0
            y0, x0, a = cy + sg * ax_[0] * np.abs(t).max(), cx + sg * ax_[1] * np.abs(t).max(), np.arctan2(sg * ax_[0], sg * ax_[1])
        else: y0, x0, a = cy, cx, np.arctan2(gy[int(cy), int(cx)], gx[int(cy), int(cx)]) + rng.uniform(-0.6, 0.6)
        chain(y0, x0, a, rng.uniform(900, 2600), 4000.0); grown += 1
    cells = np.nonzero(okc & (wo > 0.9)); free = 0
    for j in rng.choice(len(cells[0]), min(30, len(cells[0])), replace=False):                    # chains whose young end never reached the surface
        y0, x0 = cells[0][j], cells[1][j]; chain(float(y0), float(x0), np.arctan2(gy[y0, x0], gx[y0, x0]) + rng.uniform(-0.5, 0.5), rng.uniform(500, 2200), rng.uniform(2400, 3800)); free += 1
    inchain = len(mounts); prov = np.where(okc & (wo > 0.9), np.clip(_lf(n, 40, rng), 0, 1) ** 2 + 0.04, 0).ravel().astype(np.float64)
    if prov.sum() > 0:
        for c in rng.choice(n * n, 1800, p=prov / prov.sum()): mount(c // n + rng.random(), c % n + rng.random(), min(600 + rng.exponential(700), 3600), rng.uniform(250, 1800))
    z -= 380 * np.clip(ndi.gaussian_filter(trail, 8.0) * (2 * np.pi * 64), 0, 1.5); del trail                 # the swell a chain stands on
    log("  generated ocean floor: ridge within 400 km of %.1f%% of the open ocean | %d island groups carry a chain on, %d chains more | %d volcanoes in chains, %d scattered | plateaus on %.1f%% of the open ocean"
        % (100 * (de[okc] < 400).mean(), grown, free, inchain, len(mounts) - inchain, 100 * (plat[okc] > 0.5).mean()))
    # an enclosed sea has no ridge of its own: broad basins parted by rises
    ze = 4700 - 700 * _lf(n, 45, rng) - 2100 * ndi.gaussian_filter((1 - np.abs(n4)) ** 3, 1.5)
    zt = np.where(mainreg, np.maximum(z, 900), np.maximum(ze, 1500)).astype(np.float32)
    # how rough the floor is: most at the ridge, where the crust is new and bare; least under the sediment off the continents
    rw = ((1 - 0.85 * sed) * (1 + 2.2 * live * np.exp(-de / 120.0) + 0.5 * plat) * mainreg).astype(np.float32)
    zt = (zt + rw * 85 * hills).astype(np.float32)
    return dict(zt=zt, de=de, rw=rw, ax=(live * wo * (1 - sed) * mainreg).astype(np.float32), mounts=mounts)

def build(land, sea, hland, E, drowned, KM, seed=11, log=print):
    """land, sea: bool (N, N); sea is the water joined to the world ocean, the rest of the water is lakes. hland: land heights
    before any coastal lowering. E: real elevation; drowned: water that is real land sunk. -> depth in m, positive down, (N, N)"""
    N = land.shape[0]; C = max(int(round(7.0 / KM)), 1); n = N // C; ck = KM * C; rng = np.random.default_rng(seed)
    blk = lambda a: a.reshape(n, C, n, C)
    # ---- land bodies by size: a volcano, a larger island, or ground that carries a margin
    lab, k = ndi.label(land); area = np.bincount(lab.ravel(), minlength=k + 1) * KM * KM; area[0] = 0
    cls = np.zeros(k + 1, np.uint8); cls[(area > 0) & (area < 1500)] = 1; cls[(area >= 1500) & (area < 25000)] = 2; cls[area >= 25000] = 3
    cl = cls[lab]; del lab
    log("  land bodies: %d small islands, %d larger islands, %d with a margin of their own" % ((cls == 1).sum(), (cls == 2).sum(), (cls == 3).sum()))
    km_all = _edt(~land, KM); km_t = _edt(cl != 1, KM) if (cls == 1).any() else np.full((N, N), 9e4, np.float32); km_s = _edt(cl != 2, KM) if (cls == 2).any() else np.full((N, N), 9e4, np.float32)
    Lc = blk(land).mean((1, 3)) > 0.5; Wc = ~Lc; Bc = blk(cl == 3).mean((1, 3)) > 0.5; isl = blk((cl == 1) | (cl == 2)).mean((1, 3)).astype(np.float32); del cl
    # ---- how wide the water is at each place: the radius of the largest circle of open water that covers it
    dkall = _edt(Wc, ck); hw = np.zeros((n, n), np.float32); t = 20.0
    while True:
        core = dkall >= t
        if not core.any(): break
        hw[(ndi.distance_transform_edt(~core) * ck <= t) & Wc] = t; t *= 1.2
    hw = ndi.gaussian_filter(hw, 15.0)                                                            # it comes in steps; left as steps they show on the floor as rings
    # ---- which sea a place belongs to: bodies of water that only narrow straits join are separate seas
    cores, kc = ndi.label(dkall >= 110.0); csz = np.bincount(cores.ravel()); csz[0] = 0; main = csz.argmax()
    _, (ry, rx) = ndi.distance_transform_edt(cores == 0, return_indices=True); reg = cores[ry, rx]; del ry, rx, cores
    log("  seas apart from the world ocean: %d, the widest %s km across" % (kc - 1, [int(2 * v) for v in sorted(ndi.maximum(hw, reg, [i for i in range(1, kc + 1) if i != main]) if kc > 1 else [], reverse=True)[:6]]))
    nA, nB, nC, nD, n3, n4, nL = (_noise(n, sc, rng) for sc in (((110, 1.0), (40, 0.5)), ((20, 1.0),), ((6, 1.0),), ((120, 1.0),), ((35, 1.0),), ((50, 1.0), (15, 0.4)), ((2.5, 1.0),)))
    # ---- the margin: distance from the run of the coast (large land only, generalised), and what kind of coast it is
    Gm = ndi.gaussian_filter(Bc.astype(np.float32), 24.0 / ck) > 0.5
    dg, (iy, ix) = ndi.distance_transform_edt(~Gm, return_indices=True); dkg = (dg * ck).astype(np.float32); del dg
    cnt = blk(land).sum((1, 3)); hc = np.where(land, hland, 0).reshape(n, C, n, C).sum((1, 3)) / np.maximum(cnt, 1)
    num = ndi.gaussian_filter(np.where(Lc, hc, 0).astype(np.float32), 120 / ck); den = ndi.gaussian_filter(Lc.astype(np.float32), 120 / ck)
    back = ndi.gaussian_filter((num / np.maximum(den, 1e-3))[iy, ix], 5.0); del num, den, hc, cnt                    # how high the land stands behind this coast
    bay = ndi.gaussian_filter(ndi.gaussian_filter(Gm.astype(np.float32), 150 / ck)[iy, ix], 5.0)                    # 0.5 a straight coast, more in a bay, less off a cape
    gl, kg = ndi.label(Gm); ga = np.bincount(gl.ravel()) * ck * ck; capb = ndi.gaussian_filter((0.3 * np.sqrt(ga[gl[iy, ix]])).astype(np.float32), 15.0); del gl
    # shelf width, km. Earth's own spread (measured off the real elevation: half of all coast has under 15 km of shelf, a tenth
    # has over 125 km, a fiftieth over 250 km), so most coast drops straight off and a few stretches carry a broad platform. A shelf
    # of much the same width on every coast is a halo. Low coasts and bays lean wide, mountain coasts narrow.
    sw = SHELF_MED * np.exp(SHELF_SPREAD * (nA / nA.std() + ndi.gaussian_filter(0.3 * np.clip((bay - 0.5) / 0.15, -1.5, 2.0) - 0.9 * _ss((back - 200) / 1200), 15.0)))      # what is read off the nearest coast jumps where the nearest coast changes: smoothed, or the jump shows as a ruled edge
    sw = np.clip(np.minimum(sw, capb), 2.0, 450.0).astype(np.float32); del capb, bay
    de = np.maximum(dkg + (12 + 0.35 * sw) * nB * np.clip(dkg / 20, 0, 1) + (16 + 0.25 * sw) * nC * np.clip(dkg / 30, 0, 1), 0)                      # the shelf edge wanders, more the wider the shelf
    # canyon heads: each stretch of coast carries a value, the water off it shares it, so the notches run down the slope
    wob = np.clip(dkg / 60, 0, 1) * 3.0; jy = np.clip(iy + (nC * wob).astype(np.int64), 0, n - 1); jx = np.clip(ix + (np.roll(nC, 977, 1) * wob).astype(np.int64), 0, n - 1)
    cn = _noise(n, ((3.0, 1.0),), rng); gate = _ss(0.5 + 1.2 * _noise(n, ((25, 1.0),), rng))
    gul = ndi.gaussian_filter(((1 - np.abs(cn[jy, jx])) ** 6 * gate[jy, jx]).astype(np.float32), 0.8); del cn, gate, jy, jx, wob, iy, ix
    dec = (de + 16 * gul * np.clip(de / (0.5 * sw + 1), 0, 1)).astype(np.float32); del gul
    bd = (110 * np.exp(0.9 * nD)).astype(np.float32); ws = np.minimum(np.maximum(50 * np.exp(0.7 * n3 / n3.std()), 25.0), 0.5 * hw + 10).astype(np.float32)        # depth of the shelf break; how fast the floor falls away below it, km
    active = (_ss((back - 700) / 900) * _ss((hw - 500) / 400) * (reg == main)).astype(np.float32)
    # ---- how deep the basin is: by its width, lifted where sunk highlands stand
    # what kind of sea it is follows from the land round it: ringed by mountains the crust is broken and even a narrow sea is deep
    # (the Red Sea, the Black Sea); in lowland a narrow sea is flooded plain and stays shallow (the Baltic, the Persian Gulf)
    kset = 1 + 1.25 * _ss((ndi.gaussian_filter(back, 30.0) - 300) / 900)
    Dw = (3900 * (1 - np.exp(-np.maximum(hw - 45 / kset, 0) * kset / 260)) * (0.85 + 0.2 * nA) * (0.7 + 0.3 * (1 - np.exp(-2.0 * ndi.gaussian_filter(dkall, 2.0) / np.maximum(hw, 1))))).astype(np.float32)
    Dc = blk(drowned).mean((1, 3)) > 0.5; dl, kd = ndi.label(ndi.binary_dilation(Dc, iterations=3) & Wc); dsz = np.bincount(dl.ravel()); bigd = np.r_[False, dsz[1:] >= 18000 / (ck * ck)][dl]
    Ec = np.where(drowned, E, 0).reshape(n, C, n, C).sum((1, 3)) / np.maximum(blk(drowned).sum((1, 3)), 1)
    Elp = ndi.gaussian_filter(np.where(bigd & Dc, Ec, 0).astype(np.float32), 35 / ck) / np.maximum(ndi.gaussian_filter((bigd & Dc).astype(np.float32), 35 / ck), 1e-3); del Ec
    ref = np.zeros(kd + 1, np.float32)
    for i in np.nonzero(dsz >= 18000 / (ck * ck))[0]:
        if i: ref[i] = np.percentile(Elp[dl == i], 25)
    rise = np.where(bigd, Elp - ref[dl], 0).astype(np.float32); fadeD = _ss(_edt(bigd, ck) / 200.0); del dl; q = rise / 2500.0
    lf = (np.where(rise > 0, 0.8 * np.tanh(1.6 * q), -0.2 * np.tanh(-3 * q)) * fadeD).astype(np.float32); del q                # highlands are rises, lowlands the deeps: a share of whatever depth the sea has there
    log("  sunk real land: %.1f%% of the water; its highlands lift the floor by up to %d%% of its depth, its lowlands sink it by up to %d%%" % (100 * bigd.sum() / max(Wc.sum(), 1), int(100 * lf.max()), int(-100 * lf.min())))
    # open ocean is judged by the great land masses alone: an island group out at sea does not make the ocean round it a narrow sea
    dkb = _edt(~Bc, ck); hwo = np.zeros((n, n), np.float32); t = 20.0
    while True:
        core = dkb >= t
        if not core.any(): break
        hwo[(ndi.distance_transform_edt(~core) * ck <= t) & Wc] = t; t *= 1.12
    hwo = ndi.gaussian_filter(hwo, 15.0); del dkb                                                # it comes in steps, each the arc of a circle: left sharp they show on the floor
    # one rule for all water: the wider it is, the nearer its floor comes to an ocean's. Whether straits or a broad mouth join a sea
    # to the ocean changes nothing about how deep it is.
    wo = _ss((hwo - 350) / 450).astype(np.float32)
    # ---- islands: a shared ridge under a chain or a cluster
    swell = _ss(ndi.gaussian_filter(isl, 24 / ck) / 0.3).astype(np.float32)

    deep = _deep(Wc, Gm, dkg, wo, reg == main, isl, active, n4, ck, seed, log); del isl
    # the texture of the deep floor. Nothing on it is a drawn line: it is rough everywhere, and the plates only say which way the grain runs
    r9 = np.random.default_rng(seed + 9); gw = lambda shape, sg: (lambda g: g / g.std())(ndi.gaussian_filter(r9.standard_normal(shape).astype(np.float32), sg, mode="wrap"))
    tile = sum(a_ * gw((1024, 1024), sg) for sg, a_ in ((2, 0.5), (5, 0.7), (12, 1.0), (30, 1.0))); tile /= tile.std()   # grainless roughness, repeating every 1024 cells
    fields = dict(active=active, n3=n3, n4=n4, nL=nL, zt=deep["zt"], rd=deep["de"], rw=deep["rw"], ax=deep["ax"], sw=sw, de=de.astype(np.float32), dec=dec, bd=bd, ws=ws, hw=hw, Dw=Dw.astype(np.float32), wo=wo, lf=lf, swell=swell, Elp=Elp, fadeD=(fadeD * bigd).astype(np.float32))
    depth = np.empty((N, N), np.float32); xs = np.arange(N, dtype=np.float32); R = max(750 * N // 12000, 100)
    for r0 in range(0, N, R):
        rows = np.arange(r0, min(r0 + R, N)); f = {k_: _up(v, rows, N) for k_, v in fields.items()}; sl = slice(r0, r0 + len(rows))
        km = km_all[sl]
        # the deep floor: the coarse build, then what only shows at full size: the valley along the ridge crest and the abyssal hills beside it
        yk, xk = np.meshgrid(rows.astype(np.float32) * KM, xs * KM, indexing="ij"); lk = lambda t, a, b: ndi.map_coordinates(t, [a % t.shape[0], b % t.shape[1]], order=1, mode="grid-wrap")
        tA = lk(tile, yk / 1.75, xk / 1.75); tB = lk(tile, (0.6 * xk + 0.8 * yk) / 6.1, (0.6 * yk - 0.8 * xk) / 6.1); del yk, xk
        rd = f["rd"] + 5 * tA + 14 * tB                                                            # shaken, so the crest is no clean line
        zt = np.maximum(f["zt"] + f["ax"] * (150 * np.exp(-(rd / 18.0) ** 2) - 60 * np.exp(-((rd - 40) / 18.0) ** 2)) + f["rw"] * (45 * tA + 80 * tB), 300.0); del rd
        dp = np.maximum((f["wo"] * zt + (1 - f["wo"]) * f["Dw"] * np.minimum(1.2 * (zt / 5400.0) ** 0.7, 1.25)) * (1 - f["lf"]), 30.0)   # the deep floor this place would have, were no coast near
        # passive margin: shelf, slope, rise
        # the margin is one surface from the shore to the deep floor. Its parts meet at the same depth and the same slope, and where the
        # shelf ends is ragged at every scale down to the cell: a break that is a clean curve with a step or a knee on it reads as a ruled line
        swf, wsf = f["sw"], f["ws"]; e0 = np.maximum(f["bd"] * (1 + 0.4 * tB), 12.0)                # how deep the shelf is at its edge, here
        dj = f["dec"] + (5 + 0.12 * swf) * tB + (6 + 0.08 * swf) * tA; s = dj - swf; del tA
        shelf = 6 + (e0 - 6) * (1 - np.exp(-3 * np.clip(dj / swf, 0, 1))) / 0.9502               # levels off toward the edge, so no crease runs down the middle of a wide one
        u = np.maximum(s, 0) / wsf; g = u * u / (u + 0.35)                                         # the break is rounded: the fall starts gently
        pas = np.where(s <= 0, shelf, e0 + (np.maximum(dp, e0) - e0) * (1 - 0.7 * np.exp(-g) - 0.3 * np.exp(-g / 5.0))) + 0.06 * dp * tB * (1 - np.exp(-g)) * np.exp(-g / 4.0); del tB, u, g, dj, e0
        # active margin: narrow shelf, trench, outer rise
        d_ = f["de"]; dt = 70 + 60 * (0.5 + 0.5 * f["n3"]); td = np.maximum(7200 + 1700 * f["n4"], dp + 1500)
        act = np.where(d_ < dt, 40 + (td - 40) * np.clip(d_ / dt, 0, 1) ** 1.7, dp + (td - dp) * np.exp(-((d_ - dt) / 50.0) ** 2) - 350 * np.exp(-((d_ - dt - 200) / 95.0) ** 2))
        out = pas + (act - pas) * f["active"]
        # islands: the ridge they share, then each volcano's own flank
        out = out * (1 - 0.36 * f["swell"] * (0.8 + 0.35 * f["nL"]) * np.clip((out - 300) / 1500, 0, 1)); lobe = 1 + 0.35 * f["nL"]
        for kmi, s0, L in ((km_t[sl], 2.5, 16.0), (km_s[sl], 5.0, 30.0)):
            x = kmi * lobe; top = 4 + 70 * np.clip(x / s0, 0, 1) ** 1.3
            out = np.where(x < s0, np.minimum(out, top), np.minimum(out, 74 + (out - 74) * (1 - np.exp(-np.maximum(x - s0, 0) / L))))
        out = np.minimum(out, 5 + 45 * km + 300 * np.maximum(km - 2.5, 0) ** 1.5)                     # the last few km off any shore
        # sunk real land keeps its ridges and valleys
        dr = drowned[sl] & (f["fadeD"] > 0.02)
        if dr.any():
            tex = np.clip(E[sl][dr] - f["Elp"][dr], -500, 900) * f["fadeD"][dr] * np.clip(out[dr] / 200, 0.3, 1); out[dr] = np.maximum(out[dr] - tex, np.minimum(out[dr], 25.0))
        depth[sl] = out
    del km_t, km_s
    # ---- volcanoes on the deep floor: a cone with a lobed base; one that would break the surface is planed off as a bank
    for yc, xc, h, R, cap, nl, ph in deep["mounts"]:
        y, x = yc * C, xc * C; r = int(R * 1.4 / KM) + 2; y0, y1, x0, x1 = max(int(y) - r, 0), min(int(y) + r + 1, N), max(int(x) - r, 0), min(int(x) + r + 1, N)
        if y1 <= y0 or x1 <= x0: continue
        gy, gx = np.ogrid[y0:y1, x0:x1]; dy, dx = (gy - y) * KM, (gx - x) * KM; th = np.arctan2(dy, dx)
        nz = np.clip(tile[np.ix_((np.arange(y0, y1) * KM / 1.75).astype(int) % 1024, ((np.arange(x0, x1) * KM / 1.75).astype(int) + 7 * nl * 131) % 1024)], -2, 2)   # no two have the same outline
        p = h * np.clip(1 - np.hypot(dy, dx) / (R * (1 + 0.1 * np.cos(nl * th + ph) + 0.2 * nz)), 0, 1) ** 1.4; old = depth[y0:y1, x0:x1]
        depth[y0:y1, x0:x1] = np.where(sea[y0:y1, x0:x1] & (p > 0), np.maximum(old - p, np.minimum(old, cap)), old)
    # ---- lakes: a bowl, as deep as the lake is wide allows
    lake = ~land & ~sea; ll, kl = ndi.label(lake)
    if kl:
        hwl = np.maximum(ndi.maximum(km_all, ll, np.arange(1, kl + 1)), KM); u = np.random.default_rng(seed + 1).random(kl)
        Dl = np.clip(2.2 * hwl ** 1.15, 12, 900) * (0.4 + 0.6 * u); i = ll[lake] - 1
        depth[lake] = np.maximum(Dl[i] * (1 - (1 - np.minimum(km_all[lake] / hwl[i], 1)) ** 2), 2.0)
    depth[land] = 0
    return depth
