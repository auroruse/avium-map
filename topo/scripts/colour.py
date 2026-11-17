"""The land's colour from space, for the Hybrid map (user, 16 Nov 2026: "making hybrid like an actual satellite image").
-> work/colour.npy (uint8, 12000x12000x3: the land as displayed) and work/sea_tint.npy (uint8 RGBA: what lies on the sea)

Every pixel of land is a real pixel wherever one exists. NASA Blue Marble Next Generation (base, 2004, twelve monthly
mosaics at 60 arc-seconds, data/bluemarble/world.2004MM.3x21600x10800.jpg from
assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/<month>/) is carried through the same warps as
the elevation: sampled per region through its warp and the relaxation, cross-faded where regions meet, mirrored across
a real coast where ground lands on real sea, then moved by the river calibration (work/nudge_field.npy).

The picture is of summer everywhere: each real place in its own midsummer month. What the imagery cannot be trusted for
is Earth's climate, which comes with it: the Canadian Arctic's ice caps stand at 21-24 N on Avium (user: "if northern
canada has ice then so would a lot of northern nichirin, rudania"). So ice and snow that last the real summer stay only
where the ground stands above Avium's own permanent snow line (permanent()); below it a pixel shows the nearest month
in which the real place is bare, and ice that is never bare is painted over with real bare ground from beside it.
Avium's rules choose WHICH real pixel is shown, never what a pixel looks like.

Two things were tried and taken back, both on the user's word after seeing them:
- procedural stand-ins (snow from noise, a hillshade over everything): "Doesn't look good enough to be a satellite
  image at all." Set beside real imagery at the same scale the reasons were plain: real imagery has no relief shading at
  this scale, and land cover has its own edges. Compare with a real crop before showing anything made.
- a northern winter (snow north of a line carried south down the katabatic corridor, each pixel from a real snowy
  month): it worked where the real place has a snowy month and not where it has none, which was northern Nichirin.
  "The original snowless satellite images would've worked if northern Canada just didn't have snow."

The overlay stretches ground up to threefold in places (Guandong, parts of Nichirin), which smears a photograph into
streaks where it only softens elevation. There the fine detail is taken from the imagery unstretched, in cells a few
tens of km across each laid true to scale (place.py says where and how much), over the broad colour the warp gives.

What Avium made itself has no place on Earth:
- the ocean islands take the imagery of the real island islands.py laid on them;
- ground flank.py brought down to an Avium-made sea takes the colour land round it has at its new height (flank_colour);
- Tartarus takes Antarctica's imagery through the fit its ice surface was laid by; the Rift's warm ground is bare, and
  its water is red (tartarus.md); Hyperborea is its ice sheet inside the Wall and, outside it, bare basalt and tundra
  below the snow (hyperborea.md; user: "Outer Hyperborea could've been relatively snowless").
Eivorie's ground is its own too, but with no shading on the land nothing of it shows, so its imagery stays as it is.
"""
import sys, pickle, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
OUT, K, D, STEP = 12000, 4, 6, 16      # as assemble.py
KM = 1.75
BM = os.path.join(DATA, "bluemarble")
t0 = time.time()
def tick(what): print("  [%4.0f s] %s" % (time.time() - t0, what), flush=True)
def _ss(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)

MONTHS = ["%02d" % m for m in range(1, 13)]

def month_bm(mm):
    """One month's mosaic with all water painted over from the land beside it"""
    with rasterio.open(os.path.join(BM, "world.2004%s.3x21600x10800.jpg" % mm)) as ds: img = np.moveaxis(ds.read(), 0, -1).copy()
    # water: outside every country, a lake, or as dark as the imagery paints water (small lakes, wide rivers)
    sm = img.astype(np.int16).sum(-1); b = img[..., 2].astype(np.int16)
    water = (np.load(os.path.join(WORK, "real_lab.npy")) == 0) | (sm < 48) | ((b * 20 > img[..., 1].astype(np.int16) * 23) & (b * 2 > img[..., 0].astype(np.int16) * 3) & (img[..., 0] < 40))
    del sm, b
    _, (iy, ix) = ndi.distance_transform_edt(water, return_indices=True)
    for c in range(3):
        fill = img[..., c][iy, ix].astype(np.float32); soft = ndi.gaussian_filter(fill, 3.0)     # nearest-land fill streaks
        img[..., c] = np.where(water, np.round(soft), img[..., c]); del fill, soft
    return img

def through_warps(bm):
    """assemble.py, with colour in place of elevation -> float32 (OUT, OUT, 3), and where there was anything"""
    region = np.load(os.path.join(WORK, "region.npy")); warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
    own = np.load(os.path.join(WORK, "own.npy"))
    dem = np.load(os.path.join(WORK, "dem60.npy")); dem = np.concatenate([dem[:, -1:], dem, dem[:, :1]], 1)
    SD = np.load(os.path.join(WORK, "seadist.npy")); SD = np.concatenate([SD[:, -1:], SD, SD[:, :1]], 1)
    ch = [np.ascontiguousarray(np.concatenate([bm[:, -1:, c], bm[:, :, c], bm[:, :1, c]], 1)) for c in range(3)]
    RX = Relax(WORK)
    acc = np.zeros((OUT, OUT, 3), np.float32); wsum = np.zeros((OUT, OUT), np.float32); objs = ndi.find_objects(own)
    for n, (b, W) in enumerate(warps.items()):
        sl = objs[b - 1]
        if sl is None: continue
        r0, r1 = max(sl[0].start - D - 1, 0), min(sl[0].stop + D + 1, 3000)
        c0, c1 = max(sl[1].start - D - 1, 0), min(sl[1].stop + D + 1, 3000)
        m = own[r0:r1, c0:c1] == b
        w3 = np.clip(1 - ndi.distance_transform_edt(~m) / D, 0, 1).astype(np.float32)
        h, w = (r1 - r0) * K, (c1 - c0) * K
        yy = (np.arange(h) + 0.5) / K - 0.5; xx = (np.arange(w) + 0.5) / K - 0.5
        wt = ndi.map_coordinates(w3, np.meshgrid(yy, xx, indexing="ij"), order=1, mode="nearest")
        if wt.max() <= 0: continue
        gy = np.arange(0, h + STEP, STEP); gx = np.arange(0, w + STEP, STEP)
        GX, GY = np.meshgrid(gx, gy)
        x6 = (c0 * K + GX + 0.5) / 2; y6 = (r0 * K + GY + 0.5) / 2
        lon, lat = W(x6, y6)
        lon, lat = Relax.apply(RX.region(b), lon, lat, x6, y6)
        lo = np.radians(lon); la = np.radians(lat)
        V = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
        py, px = np.meshgrid(np.arange(h) / STEP, np.arange(w) / STEP, indexing="ij")
        v = np.stack([ndi.map_coordinates(V[k], [py, px], order=1, mode="nearest") for k in range(3)])
        del py, px
        v /= np.maximum(np.sqrt((v ** 2).sum(0)), 1e-9)
        lat = np.degrees(np.arcsin(np.clip(v[2], -1, 1))); lon = np.degrees(np.arctan2(v[1], v[0]))
        del v
        row = (90 - lat) * 60 - 0.5; col = (lon + 180) * 60 - 0.5 + 1
        e = ndi.map_coordinates(dem, [row, col], order=1, mode="nearest", output=np.float32)
        sea = (e <= 0) & (wt > 0)
        if sea.any():                                             # the same point the elevation was mirrored from
            r_ = row[sea]; c_ = col[sea]
            d = ndi.map_coordinates(SD, [r_, c_], order=1, mode="nearest")
            gr = ndi.map_coordinates(SD, [r_ + 1.5, c_], order=1, mode="nearest") - ndi.map_coordinates(SD, [r_ - 1.5, c_], order=1, mode="nearest")
            gc = ndi.map_coordinates(SD, [r_, c_ + 1.5], order=1, mode="nearest") - ndi.map_coordinates(SD, [r_, c_ - 1.5], order=1, mode="nearest")
            gn = np.maximum(np.hypot(gr, gc), 1e-6); step = 2.0 * d + 1.5
            row[sea] = np.clip(r_ - gr / gn * step, 0, 10799); col[sea] = (c_ - 1 - gc / gn * step) % 21600 + 1
        sub = (slice(r0 * K, r1 * K), slice(c0 * K, c1 * K))
        for c in range(3): acc[sub + (c,)] += wt * ndi.map_coordinates(ch[c], [row, col], order=1, mode="nearest", output=np.float32)
        wsum[sub] += wt
        if n % 40 == 0: tick("%d regions" % n)
    has = wsum > 1e-4
    acc[has] /= wsum[has][:, None]
    return acc, has

def nudged(acc):
    """nudge.py's shift, on the colour"""
    F = np.load(os.path.join(WORK, "nudge_field.npy")); out = np.empty_like(acc)
    for r0 in range(0, OUT, 1500):
        yy, xx = np.meshgrid(np.arange(r0, r0 + 1500, dtype=np.float32), np.arange(OUT, dtype=np.float32), indexing="ij")
        gy = ((yy + 0.5) / 2 - 4) / 8; gx = ((xx + 0.5) / 2 - 4) / 8
        fx = ndi.map_coordinates(F[..., 0], [gy, gx], order=1, mode="nearest"); fy = ndi.map_coordinates(F[..., 1], [gy, gx], order=1, mode="nearest")
        sy = yy - 2 * fy; sx = xx - 2 * fx
        for c in range(3): out[r0:r0 + 1500, :, c] = ndi.map_coordinates(acc[..., c], [sy, sx], order=1, mode="nearest")
    return out

def _noise(shape, scale, rng, order=3):
    """smooth noise in about -1..1 with features `scale` px across"""
    n = rng.standard_normal((shape[0] // scale + 3, shape[1] // scale + 3)).astype(np.float32)
    z = ndi.zoom(n, scale, order=order)[:shape[0], :shape[1]]
    return z / max(float(np.abs(z).max()), 1e-6) * 1.6

def _slope(z):
    gy, gx = np.gradient(z, KM * 1000.0); return np.degrees(np.arctan(np.hypot(gx, gy)))

def _lum(c): return c @ np.array([0.30, 0.59, 0.11], np.float32)

ICE = np.array([236, 240, 246], np.float32)

def snowlike(c):
    """white or blue-white and not sand: snow, ice, cloud left in the mosaic"""
    c = c.astype(np.int16); mx = c.max(-1); mn = c.min(-1)
    return (mx > 168) & (mx - mn < 46) & (c[..., 2] > c[..., 0] - 12)

# ------------------------------------------------------------------ ground Avium made lower than Earth has it
EDGES = (0, 150, 400, 800, 1300, 2000, 3000, 4200, 9000)

def flank_colour(col, land, has, H, E):
    """flank.py brings a coast Earth does not have down to the sea (Tibet and the Tarim on the Himalayan Sea, user 16 Nov
    2026: "didnt really take some of avium's different topography from earth into [account], see xinjiang & tibet's
    coasts"). The imagery there is still the plateau's: bare high ground and glaciers at the water's edge. Such ground
    takes the colour the land round it has at the height it now stands at, and greens toward the new sea."""
    d = np.where(land & has, E - H, 0).astype(np.float32); w = _ss((d - 120.0) / 380.0); del d
    ys, xs = np.nonzero(w > 0.02)
    if not len(ys): return
    f = 8; U = (land & has & (w < 0.02) & ~snowlike(col))
    c8 = [ndi.zoom(np.where(U, col[..., k], 0).astype(np.float32), 1 / f, order=1) for k in range(3)]
    u8 = ndi.zoom(U.astype(np.float32), 1 / f, order=1); e8 = ndi.zoom(np.where(land, E, 0).astype(np.float32), 1 / f, order=1); del U
    fields = []
    for lo, hi in zip(EDGES[:-1], EDGES[1:]):
        m = u8 * ((e8 >= lo) & (e8 < hi)); out = None
        for sg in (20.0, 70.0, 250.0):                               # the land nearby at this height, or further off
            wg = ndi.gaussian_filter(m, sg); cg = np.stack([ndi.gaussian_filter(c8[k] * ((e8 >= lo) & (e8 < hi)), sg) for k in range(3)], -1) / np.maximum(wg, 1e-6)[..., None]
            ok = _ss((wg - 0.002) / 0.02)[..., None]
            out = cg if out is None else out * okp + cg * (1 - okp)
            okp = ok if sg == 20.0 else np.maximum(okp, ok)
        fields.append(out)
    cen = np.array([(a + b) / 2 for a, b in zip(EDGES[:-1], EDGES[1:])], np.float32); cen[-1] = 5000.0
    h = np.maximum(H[ys, xs].astype(np.float32), 0); pos = np.interp(h, cen, np.arange(len(cen))); i0 = np.clip(pos.astype(int), 0, len(cen) - 2); t = (pos - i0)[:, None]
    A = np.zeros((len(ys), 3), np.float32); cy = ys / f; cx = xs / f
    for b in range(len(cen)):
        sel0 = i0 == b; sel1 = i0 + 1 == b
        for sel, wt in ((sel0, 1 - t), (sel1, t)):
            if sel.any():
                A[sel] += wt[sel] * np.stack([ndi.map_coordinates(fields[b][..., k], [cy[sel], cx[sel]], order=1, mode="nearest") for k in range(3)], -1)
    # the grain a smooth field lacks: wooded hollows, paler crests, rock on the steep
    rng = np.random.default_rng(17); r0, r1, q0, q1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    z = np.where(land[r0:r1, q0:q1], H[r0:r1, q0:q1], 0).astype(np.float32)
    rel = (z - ndi.gaussian_filter(z, 7.0))[ys - r0, xs - q0]; sl = _slope(z)[ys - r0, xs - q0]
    # toward the sea the air is wet: dry ground greens within about a hundred km of the shore, less the higher it stands
    dsea = ndi.distance_transform_edt(land)[ys, xs].astype(np.float32) * KM
    dry = 1 - np.clip((A[:, 1] - A[:, 0]) / 30.0 + 0.5, 0, 1)
    # ...and not evenly: further up some valleys than others, and little of it over the first high ground
    nb = _noise((r1 - r0, q1 - q0), 130, rng)[ys - r0, xs - q0]; hs = ndi.gaussian_filter(z, 14.0)[ys - r0, xs - q0]
    g = 0.66 * np.exp(-dsea / (110.0 * (0.45 + 1.1 * _ss(0.5 + 0.6 * nb)))) * np.exp(-np.maximum(hs - 250.0, 0) / 1100.0) * _ss((2400.0 - h) / 1600.0) * dry
    g *= 1.0 + 0.35 * np.clip(-rel / 60.0, -1, 1)
    A += g[:, None] * (np.array([64, 88, 50], np.float32) - A)
    n = _noise((r1 - r0, q1 - q0), 6, rng)[ys - r0, xs - q0]
    A *= (1.0 + 0.07 * np.clip(rel / 70.0, -1, 1) + 0.05 * n)[:, None]
    A += (_ss((sl - 16.0) / 14.0) * 0.4)[:, None] * (np.array([118, 106, 92], np.float32) - A)
    # ...and the photograph's own, off the ground that stood here (its glaciers aside)
    orig = col[r0:r1, q0:q1].astype(np.float32); orig[snowlike(col[r0:r1, q0:q1])] = np.nan
    lumo = np.nan_to_num(_lum(orig), nan=0.0); okm = np.isfinite(orig[..., 0]).astype(np.float32); del orig
    fine = (lumo - ndi.gaussian_filter(lumo, 3.0) / np.maximum(ndi.gaussian_filter(okm, 3.0), 1e-3)) * okm; del lumo, okm
    A *= (1.0 + np.clip(fine[ys - r0, xs - q0], -40, 40) / 110.0)[:, None]; del fine
    ww = w[ys, xs][:, None]; col[ys, xs] = np.clip(col[ys, xs] + ww * (A - col[ys, xs]), 0, 255)
    tick("ground lowered from the real place's: %d px recoloured from its own height" % len(ys))

# ------------------------------------------------------------------ snow and ice by Avium's rules
def permanent(lat): return 5200.0 - 48.0 * np.abs(lat)      # m: the height above which snow lasts the summer at an Avium latitude

# ------------------------------------------------------------------ the months, through the warps
CELL = 64                        # px between the centres of the cells that are laid true to scale
ISO_FROM, ISO_FULL = 1.7, 2.2    # stretch at which the unstretched detail starts to be used, and at which it is all that is
FEATHER = 2.5                    # px either side of a seam over which two cells cross-fade
SPLIT = 6.0                      # px: colour broader than this follows the warp; finer comes from the cells

def cells(land, has):
    """For ground the overlay stretches: each pixel's place on the imagery if its neighbourhood were laid on the map true
    to scale and unstretched. The map is cut into cells with ragged edges; each has one rigid placement, turned as the
    warp turns there and scaled as it scales on average. -> ys, xs, (row, col) on the 60s grid in its own cell and in the
    next nearest, how much of its own, weight"""
    from scipy.spatial import cKDTree
    pl = np.load(os.path.join(WORK, "place.npz")); lat, lon, st = pl["lat"], pl["lon"], pl["stretch"]; ok = np.isfinite(lat)
    w3 = ndi.gaussian_filter((_ss((st - ISO_FROM) / (ISO_FULL - ISO_FROM)) * ok).astype(np.float32), 2.0)
    wz = np.clip(ndi.zoom(w3, 4, order=1), 0, 1) * (land & has); del w3
    ys, xs = np.nonzero(wz > 0.02)
    _, (iy, ix) = ndi.distance_transform_edt(~ok, return_indices=True); la = np.radians(lat[iy, ix]); lo = np.radians(lon[iy, ix]); del iy, ix
    V = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
    rng = np.random.default_rng(5); g = np.arange(CELL / 2, OUT, CELL); sx, sy = [a.ravel() for a in np.meshgrid(g, g)]
    sy = sy + rng.uniform(-0.33, 0.33, sy.shape) * CELL; sx = sx + rng.uniform(-0.33, 0.33, sx.shape) * CELL
    at = lambda y, x: np.stack([ndi.map_coordinates(V[..., k], [(y - 2) / 4, (x - 2) / 4], order=1, mode="nearest") for k in range(3)], -1)
    V0 = at(sy, sx); V0 /= np.linalg.norm(V0, axis=-1, keepdims=True); d = 8.0
    dx = (at(sy, sx + d) - at(sy, sx - d)) * 6371.0 / (2 * d); dy = (at(sy + d, sx) - at(sy - d, sx)) * 6371.0 / (2 * d)
    la0 = np.arcsin(np.clip(V0[:, 2], -1, 1)); lo0 = np.arctan2(V0[:, 1], V0[:, 0])
    e = np.stack([-np.sin(lo0), np.cos(lo0), np.zeros_like(lo0)], -1); n = np.stack([-np.sin(la0) * np.cos(lo0), -np.sin(la0) * np.sin(lo0), np.cos(la0)], -1)
    J = np.stack([np.stack([(e * dx).sum(-1), (e * dy).sum(-1)], -1), np.stack([(n * dx).sum(-1), (n * dy).sum(-1)], -1)], -2)      # km east, north per px right, down
    U, sv, Vt = np.linalg.svd(J); Q = U @ Vt; gs = np.clip(np.sqrt(sv[:, 0] * sv[:, 1]), 1.2, 2.3)                     # the turn (or turn and flip) and the mean scale
    # ragged cell edges at every scale, so a seam reads as the edge of a wood or a field and never as a ruled line
    wy = 16.0 * _noise((OUT // 4, OUT // 4), 9, rng)[ys // 4, xs // 4] + 5.0 * _noise((OUT // 2, OUT // 2), 3, rng)[ys // 2, xs // 2]
    wx = 16.0 * _noise((OUT // 4, OUT // 4), 9, rng)[ys // 4, xs // 4] + 5.0 * _noise((OUT // 2, OUT // 2), 3, rng)[ys // 2, xs // 2]
    dd, sid = cKDTree(np.stack([sy, sx], -1)).query(np.stack([ys + wy, xs + wx], -1), k=2, workers=-1); del wy, wx
    def where(sid):
        ddy = ys - sy[sid]; ddx = xs - sx[sid]
        te = gs[sid] * (Q[sid, 0, 0] * ddx + Q[sid, 0, 1] * ddy); tn = gs[sid] * (Q[sid, 1, 0] * ddx + Q[sid, 1, 1] * ddy)
        latp = np.degrees(la0[sid]) + tn / 111.19; lonp = np.degrees(lo0[sid]) + te / (111.19 * np.maximum(np.cos(la0[sid]), 0.05))
        return ((90 - latp) * 60 - 0.5).astype(np.float32), (((lonp + 180) * 60 - 0.5) % 21600).astype(np.float32)
    mix = _ss(0.5 + (dd[:, 1] - dd[:, 0]) / (2 * FEATHER)).astype(np.float32)        # 1 inside its own cell, 0.5 on the seam
    p1 = where(sid[:, 0]); p2 = where(sid[:, 1])
    # a cell laid true to scale can run off the real coast, where the imagery is only paint: there the warp's own colour stays
    sea = ndi.gaussian_filter((np.load(os.path.join(WORK, "real_lab.npy")) == 0).astype(np.float32), 2.0)
    dry = lambda q: 1 - _ss(ndi.map_coordinates(sea, [np.clip(q[0], 0, 10799), q[1]], order=1, mode="grid-wrap") / 0.35)
    w = wz[ys, xs].astype(np.float32) * np.minimum(dry(p1), dry(p2)); del sea
    return ys, xs, p1, p2, mix, w

def island_places(land, has, pm):
    """(y, x, row, col): where on the 60s grid each ocean island's pixels lie, from islands.py's fits (cached)"""
    f = os.path.join(WORK, "island_places.npz")
    if os.path.exists(f): q = np.load(f); return q["y"], q["x"], q["row"], q["col"]
    import islands
    real = has & (np.load(os.path.join(WORK, "ereal_adj.npy")) >= 2.0)      # as terrain.py counts ground that is not real sea
    places = []; islands.build(np.zeros((OUT, OUT), np.float32), land, has, pm, KM, log=lambda *a: None, places=places, real=real); del real
    y = np.concatenate([np.nonzero(t)[0] + sl[0].start for sl, t, _, _ in places]); x = np.concatenate([np.nonzero(t)[1] + sl[1].start for sl, t, _, _ in places])
    row = np.concatenate([p[2] for p in places]).astype(np.float32); col = np.concatenate([p[3] for p in places]).astype(np.float32)
    np.savez(f, y=y, x=x, row=row, col=col); return y, x, row, col

def polar_mask():
    import polar
    pc = np.load(os.path.join(WORK, "polar_cache.npz")); pm = np.zeros((OUT, OUT), bool)
    for i, (_, rs, cs, _) in enumerate(polar.REGIONS): pm[rs, cs] |= pc["P%d" % i]
    return pm

def prep(months, land, has):
    """-> work/colour_real_MM.npy for each month: the mosaic on Avium's land. The two slow halves are kept (work/bm_MM.npy,
    the month with its water painted over; work/warp_MM.npy, that through the warps) so the cells can be redone alone."""
    todo = [m for m in months if not os.path.exists(os.path.join(WORK, "colour_real_%s.npy" % m))]
    if not todo: return
    pm = polar_mask(); ys, xs, p1, p2, mix, wz = cells(land, has); tick("cells laid true to scale: %.1f%% of land" % (100 * len(ys) / land.sum()))
    isl = island_places(land, has, pm); tick("island places")
    painted = land & has; painted[isl[0], isl[1]] = True
    _, (fy, fx) = ndi.distance_transform_edt(~painted, return_indices=True); miss = land & ~painted; my, mx = np.nonzero(miss); fy = fy[my, mx]; fx = fx[my, mx]; del miss, painted
    for mm in todo:
        fb = os.path.join(WORK, "bm_%s.npy" % mm); fw = os.path.join(WORK, "warp_%s.npy" % mm)
        if os.path.exists(fb): bm = np.load(fb)
        else: bm = month_bm(mm); np.save(fb, bm)
        if os.path.exists(fw): acc = np.load(fw).astype(np.float32)
        else: acc, _ = through_warps(bm); acc = nudged(acc); np.save(fw, np.clip(np.round(acc), 0, 255).astype(np.uint8))
        for k in range(3):
            smp = lambda q: ndi.map_coordinates(bm[..., k], [np.clip(q[0], 0, 10799), q[1]], order=1, mode="grid-wrap")
            iso = acc[..., k].copy(); iso[ys, xs] = mix * smp(p1) + (1 - mix) * smp(p2)
            fine = iso[ys, xs] - ndi.gaussian_filter(iso, SPLIT)[ys, xs]; del iso
            broad = ndi.gaussian_filter(acc[..., k], SPLIT)[ys, xs]
            acc[ys, xs, k] += wz * (broad + fine - acc[ys, xs, k])
            acc[isl[0], isl[1], k] = ndi.map_coordinates(bm[..., k], [np.clip(isl[2], 0, 10799), isl[3] % 21600], order=1, mode="grid-wrap")
        out = np.clip(np.round(acc), 0, 255).astype(np.uint8); del acc, bm
        out[my, mx] = out[fy, fx]                                 # land with no place on Earth and none given: its neighbour's, for now
        np.save(os.path.join(WORK, "colour_real_%s.npy" % mm), out); del out; tick("month " + mm)

# ------------------------------------------------------------------ which month each pixel shows
NEAREST = (0, 1, -1, 2, -2)      # months from midsummer, in the order they are tried

def compose(land, has, H, pm):
    """-> the land's colour outside the polar continents (uint8 image), and a mask of ice Avium would not keep that no
    month near summer shows bare"""
    Lr = land & ~pm; iy, ix = np.nonzero(Lr); N = len(iy)
    M = np.empty((12, N, 3), np.uint8); snow = np.empty((12, N), bool)
    for i, mm in enumerate(MONTHS):
        a = np.load(os.path.join(WORK, "colour_real_%s.npy" % mm)); M[i] = a[iy, ix]; del a
    # Under snow: white outright, or (forest and scrub, which stay dark under it) clearly bluer than the same ground is
    # when bare without having turned yellow: snow lifts the blue most, dry grass the red. Bare is the third lowest blue of
    # its twelve months, which a shadow or a flood does not reach.
    bare = np.partition(M[..., 2], 2, axis=0)[2].astype(np.int16)
    for i in range(12):
        c = M[i].astype(np.int16)
        snow[i] = snowlike(M[i]) | ((c[:, 2] - bare > 20) & (c[:, 2] > c[:, 0] - 14) & (c.max(-1) - c.min(-1) < 60))
    del bare
    tick("twelve months gathered: %d px of land" % N)
    # the real place's own midsummer: July, or January if it lies south of Earth's equator
    pl = np.load(os.path.join(WORK, "place.npz")); rl = pl["lat"]; ok = np.isfinite(rl); _, ind = ndi.distance_transform_edt(~ok, return_indices=True)
    south = (rl[tuple(ind)] < 0)[np.minimum(iy // 4, 2999), np.minimum(ix // 4, 2999)]; del rl, ok, ind
    isl = island_places(land, has, pm); tmp = np.zeros((OUT, OUT), np.int8); tmp[isl[0], isl[1]] = np.where(isl[2] > 5400, 2, 1); t = tmp[iy, ix]; south = np.where(t > 0, t == 2, south); del tmp, t
    ar = np.arange(N); slot = lambda j: np.where(south, j % 12, (6 + j) % 12)
    lat = 90.0 * (1 - (ix + iy + 1) / OUT).astype(np.float32); z = np.maximum(H[iy, ix].astype(np.float32), 0)
    # Snow that lasts the summer is the real place's own, and only ever taken away: kept where the ground stands above
    # Avium's permanent line, gone below it.
    keep = snow[slot(0), ar] & (z > permanent(lat) - 200.0)
    # Below it, the month near midsummer in which the country round the pixel lies barest, so a stretch of ground is one
    # month's photograph and not a speckle of five...
    Lf = ndi.gaussian_filter(Lr.astype(np.float32), 5.0)[iy, ix]; best = np.full(N, 9.0, np.float32); pick = np.zeros(N, np.int8); tmp = np.zeros((OUT, OUT), np.float32)
    for d in NEAREST:
        tmp[iy, ix] = snow[slot(d), ar] & ~keep; sc = ndi.gaussian_filter(tmp, 5.0)[iy, ix] / np.maximum(Lf, 1e-3) + 0.03 * abs(d)
        pick = np.where(sc < best - 1e-6, d, pick); best = np.minimum(best, sc)
    del tmp, Lf, best
    # ...then, pixel by pixel, any of them in which what is still under snow there is bare
    NONE = 9; alt = np.full(N, NONE, np.int8)
    for d in reversed(NEAREST): alt = np.where(~snow[slot(d), ar], d, alt)
    pick = np.where(keep, 0, np.where(snow[slot(pick), ar], alt, pick)); gone = pick == NONE
    c = M[slot(np.where(gone, 0, pick)), ar]
    tick("midsummer as it is: %.1f%% | another month, for bare ground: %.2f%% | ice to paint over: %.2f%% | summer snow kept: %.2f%%"
         % (100 * (pick == 0).mean(), 100 * ((pick != 0) & ~gone).mean(), 100 * gone.mean(), 100 * keep.mean()))
    col = np.zeros((OUT, OUT, 3), np.uint8); col[iy, ix] = c
    bad = np.zeros((OUT, OUT), bool); bad[iy[gone], ix[gone]] = True
    return col, bad

BLOCK = 40
GRAIN = 6.0                      # px: what of a copied piece is finer than this is copied; its tone is not
def paint_over(col, land, bad, pm, nosrc=None, tonal=False, came=None):
    """Ground under ice that Avium would not keep takes real bare ground from beside it: piece by ragged piece, a place
    nearby where the same shape of ground lies bare is copied across, so what goes in is a piece of the photograph and
    not a smear of its nearest edge. Pieces that find no such place take the nearest bare pixel's colour. `nosrc`:
    ground that is not to be copied from. -> px painted

    `tonal`: only the grain of a piece is copied (what is finer than GRAIN px of it), and its tone is the bare ground's
    round where it goes, carried in smoothly from every side. Copied whole, each piece brings its own tone with it, and
    where the ice is many pieces wide, as over the islands east of Dyche Bay, they stood side by side as a quilt of
    squares, dark tundra against pale rock (user, 17 Nov 2026: "Possible texture glitches?"). Kemet's shore, a strip one
    piece wide that the user has passed, is still copied whole.

    `came`: an int16 array (2, OUT, OUT) to receive, for every px painted from a piece, how far away (down, right) the
    ground it was copied from lies. hybrid.py reads the 500 m photograph there, so painted ground is as sharp as the
    photograph beside it and not this layer enlarged."""
    bad = ndi.binary_dilation(bad, iterations=2) & land & ~pm
    if not bad.any(): return 0
    good = land & ~pm & ~bad & ~snowlike(col)
    if nosrc is not None: good &= ~nosrc
    src = col.copy(); rng = np.random.default_rng(11); n = 0
    ys, xs = np.nonzero(bad)
    if tonal:
        # the grain of the bare ground, and the tone it has round each place to be painted: from near if there is any near,
        # from further off if not
        gw = good.astype(np.float32); nb = np.maximum(ndi.gaussian_filter(gw, GRAIN), 1e-3)
        grain = np.zeros(col.shape, np.int8); tone = np.zeros((len(ys), 3), np.float32)
        w4 = gw.reshape(OUT // 4, 4, OUT // 4, 4).mean((1, 3)); cy = (ys - 1.5) / 4; cx = (xs - 1.5) / 4
        for k in range(3):
            v = src[..., k].astype(np.float32); grain[..., k] = np.clip(np.round(v - ndi.gaussian_filter(v * gw, GRAIN) / nb), -127, 127) * good
            c4 = (v * gw).reshape(OUT // 4, 4, OUT // 4, 4).mean((1, 3)); out = None; del v
            for sg in (8.0, 24.0, 80.0):
                wg = ndi.gaussian_filter(w4, sg); cg = ndi.gaussian_filter(c4, sg) / np.maximum(wg, 1e-6); ok = _ss((wg - 0.01) / 0.08)
                out = cg if out is None else out * okp + cg * (1 - okp)
                okp = ok if sg == 8.0 else np.maximum(okp, ok)
            tone[:, k] = ndi.map_coordinates(out, [cy, cx], order=1, mode="nearest")
        del gw, nb, w4, c4, cy, cx, out
    offs = np.array([(dy, dx) for dy in range(-420, 421, 10) for dx in range(-420, 421, 10) if (dy or dx)])
    offs = offs[np.lexsort((rng.random(len(offs)), np.round(np.hypot(offs[:, 0], offs[:, 1]) / 90.0)))]       # nearer first, any direction
    wy = 14.0 * _noise((OUT // 4, OUT // 4), 6, rng)[ys // 4, xs // 4]; wx = 14.0 * _noise((OUT // 4, OUT // 4), 6, rng)[ys // 4, xs // 4]
    lab = ((ys + wy) // BLOCK).astype(np.int64) * 100000 + ((xs + wx) // BLOCK).astype(np.int64); del wy, wx
    order = np.argsort(lab, kind="stable"); cuts = np.flatnonzero(np.diff(lab[order])) + 1; left = np.zeros((OUT, OUT), bool)
    for g in np.split(order, cuts):
        py, px = ys[g], xs[g]
        for dy, dx in offs:
            qy = py + dy; qx = px + dx
            if qy.min() < 0 or qx.min() < 0 or qy.max() >= OUT or qx.max() >= OUT: continue
            if good[qy, qx].all():
                col[py, px] = np.clip(np.round(tone[g] + grain[qy, qx]), 0, 255) if tonal else src[qy, qx]; n += 1
                if came is not None: came[0][py, px] = dy; came[1][py, px] = dx
                break
        else:
            left[py, px] = True
            if tonal: col[py, px] = np.clip(np.round(tone[g]), 0, 255)
    if left.any() and not tonal:
        _, (iy, ix) = ndi.distance_transform_edt(~good, return_indices=True); ly, lx = np.nonzero(left); col[ly, lx] = src[iy[ly, lx], ix[ly, lx]]; del iy, ix
    # the joins: a pixel of give where a copied piece meets what was there
    edge = ndi.binary_dilation(bad, iterations=1) & ~ndi.binary_erosion(bad, iterations=1) & land
    r0, r1, q0, q1 = max(ys.min() - 2, 0), ys.max() + 3, max(xs.min() - 2, 0), xs.max() + 3
    for k in range(3):
        cc = col[r0:r1, q0:q1, k]; sm = ndi.gaussian_filter(cc.astype(np.float32), 0.8); e = edge[r0:r1, q0:q1]; cc[e] = np.round(sm[e])
    tick("painted over: %d px, in %d pieces of real ground copied in and %d px from their nearest neighbour" % (len(ys), n, int(left.sum())))
    return len(ys)

# ------------------------------------------------------------------ ground with no photograph of ground
def seam_mask(land, has, pm):
    """Where the overlay presses apart pieces of Earth together (Borneo, Sulawesi and Java are one land in Cahaya), the
    ground between them has no photograph of ground. Either its real place is real sea, which shows "the water painted
    over from the nearest land": a smear of the coast, or far out whatever land is nearest, off Vietnam one hazy pixel of
    an islet spread grey over half an island of Kienam. Or it is a real shore stretched many times over to fill the gap,
    where the cells laid true to scale cannot stand in because they run off that shore. 2.5% of the land, in blotches
    hundreds of km across (user, 17 Nov 2026: "Possible texture glitches?", then of Cahaya "Pretty rough patch").
    -> the mask, also written to work/seam.npy for hybrid.py. paint_over(tonal=True) lays real ground on it: the tone
    of the photographed ground round it and the grain of pieces of that ground."""
    isl = island_places(land, has, pm); own = np.zeros((OUT, OUT), bool); own[isl[0], isl[1]] = True
    E = np.load(os.path.join(WORK, "ereal_adj.npy"))
    sea = land & ~pm & ~own & ((has & (E < 2.0)) | ~has)             # ...and ground the overlay puts nowhere at all
    sea |= ndi.binary_dilation(sea, iterations=3) & land & ~pm & ~own & (E < 10.0); del E      # the shore blended toward the paint
    ys, xs, _, _, _, w = cells(land, has)
    pl = np.load(os.path.join(WORK, "place.npz")); ok = np.isfinite(pl["lat"])
    w3 = ndi.gaussian_filter((_ss((pl["stretch"] - ISO_FROM) / (ISO_FULL - ISO_FROM)) * ok).astype(np.float32), 2.0)
    wz = np.clip(ndi.zoom(w3, 4, order=1), 0, 1) * (land & has); del w3
    smear = np.zeros((OUT, OUT), bool); smear[ys, xs] = wz[ys, xs] - w > 0.5; del wz
    seam = sea | (smear & ~pm & ~own)
    np.save(os.path.join(WORK, "seam.npy"), seam); tick("ground with no photograph of ground: %.2f%% of the land" % (100.0 * seam.sum() / (land & ~pm).sum()))
    return seam

# ------------------------------------------------------------------ Kemet's shore
KEMET = (slice(6840, 7560), slice(6860, 7340))      # rows, cols (12000 grid): the Sea of Kemet's east shore, from the neck south
NECK = 6905                                         # the row south of which the valley's ribbon runs beside that sea
APEX = 6878                                         # the row the delta's green ends at: the ribbon below it goes, link across the neck and all

def kemet_shore(col, land, level, H, pm):
    """The real Nile cannot exist on Avium: Aswan, Khartoum and Lake Victoria are under its sea, and what is left of the
    valley (Cairo to Luxor) lies along the Sea of Kemet's east shore. The imagery still has the valley as a green ribbon
    with a river's bends, some 17 km inland for most of its length, beside a sea it knows nothing of. The user's call
    (17 Nov 2026, after I had argued both for a fertile shore and, when asked how salt water would fertilise anything,
    for bare desert): "Make the shore line up with the lower nile but make the delta it's own branch." So the lower
    valley's green lies on the shore: the ribbon south of the neck is taken off (real desert copied in from beside it)
    and its own colours are laid as a band along the water, as wide as the ribbon was, narrowing where the ground rises.
    The delta is left exactly as it is, green and rivers both: its two branches on the rivers layer are a river of their
    own and are not joined to the Sea of Kemet. The piece of ribbon that ran from its apex across the neck to the shore
    goes too (user: "Take the link out"), so the delta stands apart from the band."""
    rs, cs = KEMET; L = land[rs, cs]; sea = ~L & (level[rs, cs] <= 0); c = col[rs, cs].astype(np.float32); lum = _lum(c)
    d = ndi.distance_transform_edt(~sea).astype(np.float32); yy = np.mgrid[rs, cs][0].astype(np.float32)
    ribbon = L & (lum < ndi.median_filter(np.where(L, lum, 160.0), size=41) - 28.0) & (d < 60.0) & (yy > APEX)
    if ribbon.sum() < 500: return
    # what the valley's green is, down its length
    rows = np.arange(rs.start, rs.stop); G = np.zeros((len(rows), 3), np.float32); ok = np.zeros(len(rows), bool)
    for i in range(0, len(rows), 30):
        m = ribbon[i:i + 30]
        if m.sum() >= 20: G[i:i + 30] = np.median(c[i:i + 30][m], 0); ok[i:i + 30] = True
    for k in range(3): G[:, k] = np.interp(rows, rows[ok], ndi.gaussian_filter1d(G[ok, k], 20.0))
    bad = np.zeros(land.shape, bool); bad[rs, cs] = ribbon
    nosrc = np.zeros(land.shape, bool); nd = (c[..., 1] - c[..., 0]) / (c[..., 1] + c[..., 0] + 1.0)
    nosrc[rs, cs] = ndi.binary_dilation(ribbon | (nd > 0.03), iterations=4)                # nothing green is copied back in
    gone = paint_over(col, land, bad, pm, nosrc); del nosrc, bad
    assert gone >= ribbon.sum(), "the valley's ribbon was not taken off"
    c = col[rs, cs].astype(np.float32); rng = np.random.default_rng(29); sh = L.shape
    wide = (8.0 + 3.0 * _noise(sh, 70, rng) + 1.5 * _noise(sh, 16, rng)) * (0.35 + 0.65 * _ss((140.0 - np.maximum(H[rs, cs], 0)) / 110.0))
    ends = _ss((yy - NECK) / 30.0) * _ss((rows[ok].max() + 15.0 - yy) / 40.0)
    w = (_ss((wide - d + 0.6) / 1.4) * ends * L)[..., None]
    green = G[:, None, :] * (1.0 + 0.05 * _noise(sh, 5, rng))[..., None]
    cc = col[rs, cs]; cc[...] = np.clip(c + w * (green - c), 0, 255)
    tick("Kemet: %d px of valley ribbon taken off, %d px of shore greened" % (int(ribbon.sum()), int((w[..., 0] > 0.5).sum())))

# ------------------------------------------------------------------ the polar continents
def _shade(z, zf=2.2, az=315.0, alt=38.0):
    """the light a low sun puts on snow and bare rock: 1 on level ground"""
    gy, gx = np.gradient(z, KM * 1000.0); gx *= zf; gy *= zf; a = np.radians(az); al = np.radians(alt)
    return np.clip((-gx * np.sin(a) * np.cos(al) + gy * np.cos(a) * np.cos(al) + np.sin(al)) / np.sqrt(gx * gx + gy * gy + 1.0), 0, 1) / np.sin(al)

ROCK = np.array([74, 66, 60], np.float32)      # bare polar rock as the imagery has it (Greenland's and Svalbard's coasts)

def hyperborea(col, land, H, rs, cs, P, rng):
    """Hyperborea in its summer (hyperborea.md): the ice sheet inside the Northern Wall, white; outside it, the ground
    bare below the snow (user: "Outer Hyperborea could've been relatively snowless"): black basalt, tundra on the low
    ground and green in the valleys, snow on the Wall's heights and its pole-facing slopes. Drawn as Tartarus's Rift is,
    which the user passed: its ground is made, so its light is too, a low sun and far less of it than a relief map's."""
    L = land[rs, cs]; z = np.where(L, H[rs, cs], 0).astype(np.float32); sh = P.shape
    zs = ndi.gaussian_filter(z, 0.7); k = 1.0 + 0.5 * (_shade(zs) - 1.0)
    dco = ndi.distance_transform_edt(ndi.gaussian_filter(L.astype(np.float32), 10.0) > 0.5).astype(np.float32) * KM      # from the coast as a whole, fjords filled
    n1, n2, n3 = _noise(sh, 110, rng), _noise(sh, 23, rng), _noise(sh, 5, rng)
    # the Wall's crest stands about 160 km in: behind it everything is the ice sheet, whatever its height
    inner = _ss((dco * (1.0 + 0.12 * n1 + 0.05 * n2) - 158.0) / 10.0)
    gy, gx = np.gradient(zs, KM * 1000.0); shady = np.clip((gx + gy) * 9.0, -1, 1); del gy, gx       # slopes that face the pole (the top-left corner) keep their snow lower
    snow = np.maximum(_ss((z - 1150.0 * (1.0 - 0.35 * shady) + 70.0 * n3 + 120.0 * n2) / 110.0), inner)
    rel = np.clip((zs - ndi.gaussian_filter(zs, 9.0)) / 180.0, -1, 1)
    # the Rift's recipe: dark rock, darker in its hollows and paler on its crests, lit harder than the snow
    ground = np.array([50, 48, 50], np.float32) + 11.0 * rel[..., None] + 5.0 * n2[..., None] + 3.0 * n3[..., None]      # black basalt (hyperborea.md)
    # tundra where the ground is low, greenest on the valley floors (the article's sheltered valleys): by the ground's
    # own shape, so it has the ground's edges
    low = _ss((330.0 - z) / 260.0); vale = low * _ss((0.1 - rel) / 0.35)
    ground += (0.4 * low)[..., None] * (np.array([78, 78, 58], np.float32) - ground); ground += (0.55 * vale)[..., None] * (np.array([64, 80, 50], np.float32) - ground)
    ground *= np.clip(1.0 + 1.6 * (k - 1.0), 0.5, 1.3)[..., None]
    white = (ICE[None, None] - (2.0 * n1)[..., None]) * np.clip(k, 0.75, 1.03)[..., None]
    # The ice sheet's own face (hyperborea.md; user, 17 Nov 2026: "Hyperborean topography"), all of it read off the
    # ground's shape. Blue in its hollows, where the firn is thin and the meltwater gathers:
    white += (0.32 * _ss(-rel * 1.6) * inner)[..., None] * (np.array([190, 216, 238], np.float32) - white)
    # the summer's melt: ponds in the dips of the gentle ice behind the Wall ("vast supraglacial lake systems"), the
    # ice round them greyed and stained rose and green by its algae
    melt = inner * _ss((330.0 - dco * (1.0 + 0.2 * n1)) / 120.0)                                     # a belt behind the Wall, of uneven width
    dip = (zs - ndi.gaussian_filter(zs, 3.0)) < -6.0; sl = _slope(zs)
    pond = melt * dip * _ss((0.7 - sl) / 0.4) * _ss((n3 * 0.7 + n2 * 0.6 - 0.2) / 0.3)          # a pond here and there, never a net of them
    stain = melt * _ss((n2 * 0.8 + n1 * 0.5 + 0.1) / 0.6)
    white += (0.13 * stain)[..., None] * (np.where((n1 > 0.15)[..., None], np.array([176, 196, 170], np.float32), np.array([214, 172, 170], np.float32)) - white)
    white += (0.75 * pond)[..., None] * (np.array([92, 160, 206], np.float32) - white)
    # rock through the ice where it is too steep to lie: the Wall's inner faces, the tops of buried ranges
    snow = snow * (1 - 0.9 * _ss((sl - 13.0) / 5.0) * inner)
    out = ground + snow[..., None] * (white - ground)
    # outlet glaciers: the ice sheet running out through the Wall's gaps, down the valley floors to the fjord heads
    vale2 = (inner < 0.5) & (rel < -0.1) & (z < 950.0) & L
    tongue = ndi.gaussian_filter(ndi.binary_propagation(vale2 & ndi.binary_dilation(inner > 0.5, iterations=8), mask=vale2).astype(np.float32), 1.0)
    glacier = (np.array([218, 228, 238], np.float32) - (5.0 * n3)[..., None]) * np.clip(k, 0.75, 1.03)[..., None]
    out += _ss((tongue - 0.3) / 0.4)[..., None] * (glacier - out)
    cc = col[rs, cs]; cc[P] = np.clip(out[P], 0, 255)
    tick("Hyperborea: bare ground on %.1f%%, melt ponds on %.2f%%, outlet glaciers on %.2f%%" % (100 * float((1 - snow)[P].mean()), 100 * float((pond > 0.5)[P].mean()), 100 * float((tongue > 0.5)[P].mean())))

def tartarus(col, land, H, rs, cs, P, rng):
    """Tartarus in its summer: Antarctica's January imagery as it is, through the fit its ice surface was laid by. Round
    the Rift the ground is warm: bare below a snow line that stands highest at its heart, rust where the red water
    washes it (tartarus.md)."""
    import polar
    bm = month_bm("01"); L = land[rs, cs]; z = np.where(L, H[rs, cs], 0).astype(np.float32); sh = P.shape
    zs = ndi.gaussian_filter(z, 0.7); sl = _slope(zs); k = 1.0 + 0.5 * (_shade(zs) - 1.0)
    dco = ndi.distance_transform_edt(L).astype(np.float32) * KM; n1, n2, n3 = _noise(sh, 110, rng), _noise(sh, 23, rng), _noise(sh, 5, rng)
    fit = np.load(os.path.join(WORK, "tartarus_fit.npy")); sc, mir, s, th, f = [float(v) for v in fit[:5]]; dy, dx = fit[5:].astype(int); f = int(f)
    ny, nx = L[::f, ::f].shape; n = 2 * polar.ANT_HALF; yy, xx = np.mgrid[:n, :n].astype(np.float32)
    X = (xx - polar.ANT_HALF + 0.5) * polar.ANT_KM; Y = (yy - polar.ANT_HALF + 0.5) * polar.ANT_KM; del yy, xx
    cl = np.degrees(2 * np.arctan(np.hypot(X, Y) / (2 * 6371.0))); lon = np.degrees(np.arctan2(X, -Y)); del X, Y
    row = (180.0 - cl) * 60 - 0.5; cc = ((lon + 180.0) * 60 - 0.5) % 21600; del cl, lon
    ice = np.stack([polar._place(ndi.map_coordinates(bm[..., c], [row, cc], order=1, mode="nearest").astype(np.float32),
                                 sh, f, KM * f, bool(mir), s, th, dy, dx, ny, nx, 1, float(ICE[c])) for c in range(3)], -1)
    # Where Tartarus's coast runs out past Antarctica's the imagery is no longer ice but "the water painted over from the
    # nearest land": every dark rock on the real shore drawn out to sea in a stripe, a curtain of them along Tartarus's
    # north coast (user, 17 Nov 2026: "Tartarus?"). That ground is the ice sheet's seaward edge and is drawn as its ice.
    off = polar._place(ndi.map_coordinates((np.load(os.path.join(WORK, "real_lab.npy")) == 0).astype(np.float32), [row, cc], order=1, mode="nearest"),
                       sh, f, KM * f, bool(mir), s, th, dy, dx, ny, nx, 1, 0.0)
    # ...with the few px of real shore beside it, which are the dark the stripes were drawn from
    off = _ss((ndi.gaussian_filter(ndi.maximum_filter(off, 9), 1.5) - 0.3) / 0.4)[..., None]
    del row, cc, bm
    cy, cx = polar.RIFT[0] - rs.start, polar.RIFT[1] - cs.start; yy, xx = np.mgrid[:sh[0], :sh[1]].astype(np.float32)
    rw = np.hypot(yy - cy, xx - cx) * (1.0 + 0.2 * n1 + 0.06 * n2); del yy, xx
    line = 1900.0 * (1 - _ss((rw - 300.0) / 800.0))                              # m: the snow line the Rift's heat holds up
    gy, gx = np.gradient(zs, KM * 1000.0); shady = np.clip((gx + gy) * -9.0, -1, 1); del gy, gx      # slopes that face the pole (the bottom-right corner) keep their snow lower
    snow = _ss((z - line * (1.0 - 0.35 * shady) + 60.0 * n3) / 90.0)
    rel = np.clip((zs - ndi.gaussian_filter(zs, 9.0)) / 180.0, -1, 1)                # hollows hold the dark, crests the pale ash
    ground = (ROCK - 8.0 + 13.0 * rel[..., None] + 6.0 * n2[..., None] + 4.0 * n3[..., None] + np.array([10, 4, -2], np.float32) * _ss((z - 300.0) / 900.0)[..., None]) * np.clip(1.0 + 1.6 * (k - 1.0), 0.5, 1.3)[..., None]
    red = _ss((1500.0 - rw) / 500.0) * np.exp(-dco / (22.0 * (0.6 + 0.8 * _ss(n2 + 0.5)))) * _ss((450.0 - z) / 350.0)
    ground += (0.7 * red)[..., None] * (np.array([128, 62, 44], np.float32) - ground)
    white = ICE[None, None] * np.clip(k, 0.75, 1.03)[..., None]
    ice = ice + off * (white - ice); del off
    warm = _ss((1500.0 - rw) / 350.0)[..., None]                                 # past the warm ground it is Antarctica's own ice again
    out = ice + warm * ((ground + snow[..., None] * (white - ground)) - ice)
    c_ = col[rs, cs]; c_[P] = np.clip(out[P], 0, 255)
    tick("Tartarus: bare ground on %.1f%%" % (100 * float(((1 - snow) * warm[..., 0])[P].mean())))

# ------------------------------------------------------------------ what lies on the water
def red_water(land, rng):
    """-> uint8 (OUT, OUT, 4): the water of the Tartarean Rift, red with iron from its vents (tartarus.md: ferric
    oxyhydroxides, "a persistent regional red turbidity", discharged northward), over the gulf inside the rings and out
    in a plume that thins as it is carried north and is one surface with the gulf at its mouth."""
    import polar
    out = np.zeros((OUT, OUT, 4), np.uint8); box = (slice(7000, OUT), slice(7400, OUT)); W = ~land[box]; sh = W.shape
    cy, cx = polar.RIFT[0] - box[0].start, polar.RIFT[1] - box[1].start
    yy, xx = np.mgrid[:sh[0], :sh[1]].astype(np.float32); rpx = np.hypot(yy - cy, xx - cx)
    n1, n2, n3 = _noise(sh, 150, rng), _noise(sh, 40, rng), _noise(sh, 11, rng)
    gulf = W & (rpx < 1230.0 + 60.0 * n1)
    f = 6; Wc = W[::f, ::f].copy(); Wc[0] = Wc[-1] = False; Wc[:, 0] = Wc[:, -1] = False       # np.roll must not carry water round the edge
    d = np.where(gulf[::f, ::f] & Wc, 0.0, np.inf).astype(np.float32); cost = (1.0 + 0.5 * n2[::f, ::f]).astype(np.float32)
    for _ in range(2):                                                            # how far the water has run from the gulf, through water only
        for sy, sx in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            for i in range(420):
                nd = np.minimum(np.minimum(np.roll(d, sy, 0), np.roll(d, sx, 1)) + cost, np.roll(np.roll(d, sy, 0), sx, 1) + 1.414 * cost)
                nd = np.where(Wc, np.minimum(d, nd), np.inf)
                if not (nd < d).any(): break
                d = nd
    dg = ndi.zoom(np.where(np.isfinite(d), d, 1e4), f, order=1)[:sh[0], :sh[1]] * f; del d
    ang = np.arctan2(-(yy - cy), -(xx - cx)); bear = np.cos(ang - np.radians(45.0)); del yy, xx       # north is away from the bottom-right corner
    fil = _ss(0.5 + 0.5 * np.sin(14.0 * ang + 3.0 * n1 + 1.6 * n2 + dg / 400.0)); eddy = _ss((n2 + 0.5 * n1 + 0.35) / 0.9); del ang
    far = _ss(dg / 320.0)
    plume = np.exp(-dg / 620.0) * (1 - far * (1 - _ss((bear + 0.1) / 0.7))) * (1 - far * (1 - (0.3 + 0.7 * fil) * (0.55 + 0.45 * eddy)))
    core = np.clip((0.97 - 0.2 * _ss((rpx - 350.0) / 850.0)) * (0.92 + 0.08 * n3), 0, 1)
    inten = ndi.gaussian_filter(np.where(gulf, core, np.clip(plume, 0, 1) * core) * W, 3.5) * W
    # darkest over the deep moat and troughs, rust-bright over the shoals and the ring crests, with the vents' water swirling in it
    dep = np.clip(-np.load(os.path.join(WORK, "height.npy"), mmap_mode="r")[box].astype(np.float32), 0, None)
    sw = _ss(0.5 + 0.5 * np.sin(rpx / 46.0 + 2.6 * n2 + 1.4 * n3 + 3.0 * n1))
    deep = np.array([78, 12, 14], np.float32); shoal = np.array([158, 54, 30], np.float32); thin = np.array([104, 52, 40], np.float32)
    body = deep + (np.exp(-dep / 900.0) * (0.7 + 0.3 * sw))[..., None] * (shoal - deep); del dep
    colr = thin + _ss((inten - 0.25) / 0.6)[..., None] * (body - thin) + (5.0 * n3)[..., None] * np.array([1.0, 0.4, 0.3], np.float32)
    o = out[box]; a = np.clip(inten * 1.05, 0, 0.95)
    o[..., :3] = np.where(a[..., None] > 0.004, np.clip(colr, 0, 255), 0); o[..., 3] = np.round(a * 255)
    tick("red water: gulf of %.0f thousand km2" % (float(gulf.sum()) * KM * KM / 1e3))
    return out

if __name__ == "__main__":
    import polar
    land = np.load(os.path.join(WORK, "land12k.npy")); has = np.load(os.path.join(WORK, "ehas_adj.npy"))
    prep(MONTHS, land, has)
    if "--prep" in sys.argv: sys.exit(0)
    H = np.load(os.path.join(WORK, "height.npy")); pm = polar_mask()
    col, bad = compose(land, has, H, pm)
    came = np.zeros((2, OUT, OUT), np.int16)
    paint_over(col, land, bad | seam_mask(land, has, pm), pm, tonal=True, came=came)
    np.save(os.path.join(WORK, "paint_from.npy"), came); del came
    flank_colour(col, land, has, H, np.load(os.path.join(WORK, "ereal_adj.npy")))
    kemet_shore(col, land, np.load(os.path.join(WORK, "waterlevel_c.npy"), mmap_mode="r"), H, pm)
    pc = np.load(os.path.join(WORK, "polar_cache.npz"))
    # Tartarus and its water are as the user passed them ("Tartarus looks pretty great", 17 Nov 2026), down to the noise:
    # the generator is brought to the state it was in when they were drawn (the draws that then came before them)
    rng_t = np.random.default_rng(41)
    for n in (31, 83, 150, 683, 24): rng_t.standard_normal((n, n))
    for i, (name, rs, cs, _) in enumerate(polar.REGIONS):
        if name == "Hyperborea": hyperborea(col, land, H, rs, cs, pc["P%d" % i], np.random.default_rng(43))
        else: tartarus(col, land, H, rs, cs, pc["P%d" % i], rng_t)
    np.save(os.path.join(WORK, "colour.npy"), col); tick("wrote colour.npy"); del col
    np.save(os.path.join(WORK, "sea_tint.npy"), red_water(land, rng_t)); tick("wrote sea_tint.npy")
