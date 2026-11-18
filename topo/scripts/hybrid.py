"""The Hybrid map's drawing, layers/hybrid.png, at 24000 px: twice the grid everything else here is built on.

The map opens two levels past the 12000 px drawings, and on a screen of double density a map pixel was three and four
screen pixels across where the names and lines over it are sharp (user, 17 Nov 2026: "Apple Maps overlaid on a PS2
game"). Everything the 12000 build was made of stops near 1.8 km: Blue Marble at 60 arc-seconds, elevation at 60. Both
exist finer, and this takes the finer ones: Blue Marble Next Generation at 500 m (data/bluemarble/
world.2004MM.3x21600x21600.<A-D><1-2>.jpg, July for real places north of Earth's equator and January south of it, from
assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/<month>/) and ETOPO 2022 at 30 arc-seconds.

Nothing the 12000 build decided is decided again. The satellite layer (colour.py) and the surface (height.npy) stand
for everything broader than a pixel and a half of theirs: which month a place shows, the ice Avium does not keep, the
ground Avium made, the grade. Only what is finer than that is new, and it is real:
- colour: every point's real place is found as assemble.py finds it (the warps, the relaxation, the cross-fade between
  regions, the river calibration), and the 500 m imagery is read there. Stretched ground takes its fine detail from
  cells laid true to scale, as in colour.py and from the same cells. Where the satellite layer shows the midsummer
  photograph as it is, the fine band is the photograph's; where the layer was made (ice painted over, a shore greened,
  ground recoloured to its new height) only the photograph's texture is laid on it, as light and dark.
- relief: the fine band of ETOPO 30s at the same place, away from shores and from ground Avium moved by more than its
  own detail. Ground whose real place lies below sea level is laid from across the nearest real shore, so its place
  jumps there and fine relief across a jump is a ruled crease: there the 12000 surface stands as it is.
- the ocean islands read the real island islands.py laid on them; the polar continents have nothing finer and are
  the 12000 build enlarged.
- land given up: hybrid_cuts.txt lists land this map alone shows as sea.
- the land's edge: land12k is a 6000 px mask doubled and steps in twos. Its smoothed edge is drawn at this size, with
  the smallest islets and lakes kept.
- the sea is seacolour.py's, asked at this size; it is a function of place, so nothing in it changes but its grain.

Run after colour.py and render.py: .venv/bin/python -I scripts/hybrid.py   (about a quarter of an hour on ten cores;
work/fine/ holds what it caches, some 20 GB). A window alone, for a look: hybrid.py --window r0 r1 c0 c1 out.png"""
import sys, os, pickle, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from geo import *
from scipy import ndimage as ndi
OUT, K, D, STEP = 12000, 4, 6, 16          # as assemble.py
F = 2                                      # this drawing's px per px of the 12000 grid
N = OUT * F
BLOCK, M = 480, 28                         # the land is drawn in blocks of this many 12000 px, each with this much round it
BAND = 400                                 # the sea in bands of this many rows
FINE = os.path.join(WORK, "fine"); BM = os.path.join(DATA, "bluemarble")
t0 = time.time()
def tick(s): print("  [%4.0f s] %s" % (time.time() - t0, s), flush=True)
def _ss(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
mm = lambda n: np.load(os.path.join(WORK, n), mmap_mode="r")
fm = lambda n, mode="r": np.load(os.path.join(FINE, n), mmap_mode=mode)
g = ndi.gaussian_filter

# ------------------------------------------------------------------ once, on the 12000 grid
def prepare():
    """work/fine/: col.npy (the satellite layer as render.py showed it: stray water out, and carried off the land so a new
    edge has colour under it), trust.npy (how far a pixel is the midsummer photograph as it is), soft.npy (the land mask,
    smoothed), ks.npy (the sea floor's light), isl_row/isl_col.npy (the ocean islands' real places), south.npy"""
    import satgrade, polar, colour as C
    os.makedirs(FINE, exist_ok=True)
    if all(os.path.exists(os.path.join(FINE, n)) for n in ("col.npy", "trust.npy", "soft.npy", "ks.npy", "isl_row.npy", "isl_col.npy", "landc.npy", "heightc.npy")): return
    # the land and the surface as this map draws them: the 12000 build's, less the land given up (hybrid_cuts.txt), which
    # becomes sea as deep as the sea beside it
    land = np.load(os.path.join(WORK, "land12k.npy")); H = np.load(os.path.join(WORK, "height.npy")); cut = np.zeros(land.shape, bool)
    for ln in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hybrid_cuts.txt")):
        if ln.strip() and not ln.startswith("#"): r, a, b = map(int, ln.split()); cut[r, a:b] = True
    cut &= land
    if cut.any():
        ys, xs = np.nonzero(cut); sl = (slice(max(ys.min() - 60, 0), ys.max() + 61), slice(max(xs.min() - 60, 0), xs.max() + 61))
        _, (jy, jx) = ndi.distance_transform_edt(land[sl], return_indices=True); Hs = H[sl]; cs = cut[sl]; Hs[cs] = Hs[jy[cs], jx[cs]]; land[cut] = False
    np.save(os.path.join(FINE, "landc.npy"), land); np.save(os.path.join(FINE, "heightc.npy"), H); tick("land given up: %d px" % int(cut.sum())); del cut
    pc = np.load(os.path.join(WORK, "polar_cache.npz")); made = np.zeros(land.shape, bool)
    for i, (_, rs, cs, _) in enumerate(polar.REGIONS): made[rs, cs] |= pc["P%d" % i]
    # the ocean islands' places, and which of Earth's summers each pixel shows (as colour.compose has it)
    has = np.load(os.path.join(WORK, "ehas_adj.npy")); iy, ix, ir, ic = C.island_places(land, has, made); del has
    row = np.full((OUT, OUT), np.nan, np.float32); col_ = np.full((OUT, OUT), np.nan, np.float32); row[iy, ix] = ir; col_[iy, ix] = ic
    np.save(os.path.join(FINE, "isl_row.npy"), row); np.save(os.path.join(FINE, "isl_col.npy"), col_); del row, col_
    pl = np.load(os.path.join(WORK, "place.npz")); rl = pl["lat"]; ok = np.isfinite(rl); _, ind = ndi.distance_transform_edt(~ok, return_indices=True)
    south = (rl[tuple(ind)] < 0).repeat(4, 0).repeat(4, 1); south[iy, ix] = ir > 5400; del rl, ok, ind
    # the layer as shown
    col = np.load(os.path.join(WORK, "colour.npy")); tick("stray water painted out: %d px" % satgrade.stray_water(col, land, made))
    d = np.zeros((OUT, OUT), np.float32)
    for r0 in range(0, OUT, 2000):
        s = slice(r0, r0 + 2000); ref = np.where(south[s, :, None], mm("colour_real_01.npy")[s], mm("colour_real_07.npy")[s])
        d[s] = np.abs(col[s].astype(np.int16) - ref.astype(np.int16)).max(-1)
    del south
    tr = np.where(land & ~made, 1 - _ss((d - 10.0) / 22.0), np.where(made, 0.0, 1.0)).astype(np.float32); del d
    np.save(os.path.join(FINE, "trust.npy"), np.round(g(tr, 1.0) * 255).astype(np.uint8)); del tr
    _, (jy, jx) = ndi.distance_transform_edt(~land, return_indices=True); col = col[jy, jx]; del jy, jx
    np.save(os.path.join(FINE, "col.npy"), col); del col; tick("the satellite layer as shown, carried off the land")
    # the land's edge. A smoothing wide enough to take the twos out of the edge takes a 2 px islet or lake out whole:
    # those are put back from a narrower one.
    Lb = land.astype(np.float32); soft = g(Lb, 1.1)
    lost = land & ~ndi.binary_dilation(soft > 0.5, iterations=2); soft = np.maximum(soft, g(lost.astype(np.float32), 0.6) * 1.25)
    lost = ~land & ~ndi.binary_dilation(soft < 0.5, iterations=2); soft = np.minimum(soft, 1 - g(lost.astype(np.float32), 0.6) * 1.25)
    np.save(os.path.join(FINE, "soft.npy"), np.round(np.clip(soft, 0, 1) * 255).astype(np.uint8)); del soft, Lb, lost
    H = H.astype(np.float32)
    ks = np.clip(1.0 + 0.75 * (shade_of(g(np.where(land, 0, H), 4.0), 5.0, 1750.0) - FLAT), 0.6, 1.18)     # as render.py had it
    np.save(os.path.join(FINE, "ks.npy"), ks.astype(np.float16)); tick("edge and sea floor light")

def tiles():
    """the 500 m mosaics as plain arrays, so a window of one is read without decoding the whole JPEG down to it"""
    for mmth, hemi in (("07", 1), ("01", 2)):
        for t in "ABCD":
            f = os.path.join(FINE, "bm500_%s%d.npy" % (t, hemi))
            if os.path.exists(f): continue
            with rasterio.open(os.path.join(BM, "world.2004%s.3x21600x21600.%s%d.jpg" % (mmth, t, hemi))) as ds: a = np.ascontiguousarray(np.moveaxis(ds.read(), 0, -1))
            np.save(f, a); del a; tick("tile %s%d" % (t, hemi))

FLAT = np.sin(np.radians(42))
def shade_of(z, zf, cell):
    """render.py's soft multi-directional hillshade"""
    gy, gx = np.gradient(z, cell); gx *= zf; gy *= zf; out = np.zeros(z.shape, np.float32); nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    for az, w in ((315, 0.55), (270, 0.15), (360, 0.15), (225, 0.15)):
        a = np.radians(az); alt = np.radians(42); lx, ly, lz = np.sin(a) * np.cos(alt), -np.cos(a) * np.cos(alt), np.sin(alt)
        out += w * np.clip((-gx * lx - gy * ly + lz) * nz, 0, 1)
    return out

# ------------------------------------------------------------------ a point's real place
class Places:
    """assemble.py and colour.through_warps, for any points"""
    def __init__(self):
        self.warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb")); self.own = np.load(os.path.join(WORK, "own.npy"))
        self.objs = ndi.find_objects(self.own); self.RX = Relax(WORK); self.Fd = np.load(os.path.join(WORK, "nudge_field.npy"))
        self.dem = mm("dem60.npy"); self.SD = mm("seadist.npy"); self.w3 = {}; self.rx = {}
    def unnudged(self, Y, X):
        gy = ((Y + 0.5) / 2 - 4) / 8; gx = ((X + 0.5) / 2 - 4) / 8
        return (Y - 2 * ndi.map_coordinates(self.Fd[..., 1], [gy, gx], order=1, mode="nearest"), X - 2 * ndi.map_coordinates(self.Fd[..., 0], [gy, gx], order=1, mode="nearest"))
    def region(self, b):
        if b not in self.w3:
            sl = self.objs[b - 1]; r0, r1 = max(sl[0].start - D - 1, 0), min(sl[0].stop + D + 1, 3000); c0, c1 = max(sl[1].start - D - 1, 0), min(sl[1].stop + D + 1, 3000)
            m = self.own[r0:r1, c0:c1] == b; self.w3[b] = (r0, r1, c0, c1, np.clip(1 - ndi.distance_transform_edt(~m) / D, 0, 1).astype(np.float32)); self.rx[b] = self.RX.region(b)
        return self.w3[b]
    def mirror(self, row, col):
        """ground on real sea (or real land below sea level) is laid from across the nearest real shore -> which points"""
        sea = np.zeros(len(row), bool)
        for half in (col < 10800, col >= 10800):                # never a window across the date line
            if not half.any(): continue
            r = row[half]; c = col[half]; ra = int(max(np.floor(r.min()) - 60, 0)); ca = int(max(np.floor(c.min()) - 60, 0))
            sl = (slice(ra, int(np.ceil(r.max())) + 61), slice(ca, int(np.ceil(c.max())) + 61))
            dm = np.asarray(self.dem[sl]).astype(np.float32); sd = np.asarray(self.SD[sl]); r = r - ra; c = c - ca
            s = ndi.map_coordinates(dm, [r, c], order=1, mode="nearest") <= 0
            if s.any():
                q = lambda a, b: ndi.map_coordinates(sd, [a, b], order=1, mode="nearest"); r_ = r[s]; c_ = c[s]
                d = q(r_, c_); gr = q(r_ + 1.5, c_) - q(r_ - 1.5, c_); gc = q(r_, c_ + 1.5) - q(r_, c_ - 1.5); gn = np.maximum(np.hypot(gr, gc), 1e-6); st = 2.0 * d + 1.5
                i = np.nonzero(half)[0][s]; row[i] = np.clip(row[i] - gr / gn * st, 0, 10799); col[i] = (col[i] - gc / gn * st) % 21600; sea[i] = True
        return sea
    def __call__(self, sy, sx):
        """-> [(index, weight, row60, col60, mirrored)] per region"""
        out = []
        for b, W in self.warps.items():
            if self.objs[b - 1] is None: continue
            sl = self.objs[b - 1]; r0, r1 = max(sl[0].start - D - 1, 0), min(sl[0].stop + D + 1, 3000); c0, c1 = max(sl[1].start - D - 1, 0), min(sl[1].stop + D + 1, 3000)
            ins = (sy >= r0 * K - 0.5) & (sy <= r1 * K - 0.5) & (sx >= c0 * K - 0.5) & (sx <= c1 * K - 0.5)
            if not ins.any(): continue
            w3 = self.region(b)[4]; idx = np.nonzero(ins)[0]; y = sy[idx]; x = sx[idx]
            wt = ndi.map_coordinates(w3, [(y - r0 * K + 0.5) / K - 0.5, (x - c0 * K + 0.5) / K - 0.5], order=1, mode="nearest"); keep = wt > 0
            if not keep.any(): continue
            idx = idx[keep]; y = y[keep]; x = x[keep]; wt = wt[keep]; h, w = (r1 - r0) * K, (c1 - c0) * K
            ly0 = max(int(np.floor((y.min() - r0 * K) / STEP)) - 1, 0); ly1 = min(int(np.ceil((y.max() - r0 * K) / STEP)) + 1, h // STEP)
            lx0 = max(int(np.floor((x.min() - c0 * K) / STEP)) - 1, 0); lx1 = min(int(np.ceil((x.max() - c0 * K) / STEP)) + 1, w // STEP)
            GX, GY = np.meshgrid(np.arange(lx0, lx1 + 1) * STEP, np.arange(ly0, ly1 + 1) * STEP); x6 = (c0 * K + GX + 0.5) / 2; y6 = (r0 * K + GY + 0.5) / 2
            lon, lat = W(x6, y6); lon, lat = Relax.apply(self.rx[b], lon, lat, x6, y6)
            lo = np.radians(lon); la = np.radians(lat); V = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
            v = np.stack([ndi.map_coordinates(V[k], [(y - r0 * K) / STEP - ly0, (x - c0 * K) / STEP - lx0], order=1, mode="nearest") for k in range(3)])
            v /= np.maximum(np.sqrt((v ** 2).sum(0)), 1e-9)
            row = (90 - np.degrees(np.arcsin(np.clip(v[2], -1, 1)))) * 60 - 0.5; col = ((np.degrees(np.arctan2(v[1], v[0])) + 180) * 60 - 0.5) % 21600
            out.append((idx, wt, row, col, self.mirror(row, col)))
        return out

# ------------------------------------------------------------------ the fine sources
def chunks(row, col, n=600):
    """points in groups that each fit a window of a few hundred 60s cells: two countries a block holds can lie far apart"""
    key = (np.floor(row / n).astype(np.int64) * 100 + np.floor(col / n).astype(np.int64)); order = np.argsort(key, kind="stable")
    cut = np.nonzero(np.diff(key[order]))[0] + 1
    return np.split(order, cut)

_tiles = {}
def bm500(row, col):
    """Blue Marble 500 m at places on the 60s grid, water painted over from the land beside it (as colour.month_bm does):
    July north of the equator, January south of it -> colour (n, 3), how much of it was water (n)"""
    out = np.zeros((len(row), 3), np.float32); wat = np.zeros(len(row), np.float32); lab = mm("real_lab.npy")
    for sel in chunks(row, col):
        r = np.clip(row[sel], 0, 10799); c = col[sel] % 21600; hemi = 2 if r.mean() > 5399.5 else 1; t = int(np.clip(c.mean() // 5400, 0, 3))
        name = "ABCD"[t] + str(hemi)
        if name not in _tiles: _tiles[name] = fm("bm500_%s.npy" % name)
        T = _tiles[name]; pr = np.clip((r + 0.5) * 4 - 0.5 - (hemi - 1) * 21600, 0, 21599); pc = np.clip((c + 0.5) * 4 - 0.5 - t * 21600, 0, 21599)
        ra = int(max(pr.min() - 40, 0)) // 4 * 4; rb = int(min(pr.max() + 44, 21600)) // 4 * 4; ca = int(max(pc.min() - 40, 0)) // 4 * 4; cb = int(min(pc.max() + 44, 21600)) // 4 * 4
        img = np.asarray(T[ra:rb, ca:cb]); i = img.astype(np.int16)
        r60 = (hemi - 1) * 5400 + ra // 4; c60 = t * 5400 + ca // 4
        water = (np.asarray(lab[r60:r60 + (rb - ra) // 4, c60:c60 + (cb - ca) // 4]) == 0).repeat(4, 0).repeat(4, 1) | (i.sum(-1) < 48) \
            | ((i[..., 2] * 20 > i[..., 1] * 23) & (i[..., 2] * 2 > i[..., 0] * 3) & (i[..., 0] < 40))
        # a river a px or two wide is neither black nor blue, only darker and bluer than its banks
        lum = (i[..., 0] * 30 + i[..., 1] * 59 + i[..., 2] * 11) / 100.0; br = (i[..., 2] - i[..., 0]).astype(np.float32)
        water |= (lum < ndi.uniform_filter(lum, 13) - 9.0) & (br > ndi.uniform_filter(br, 13) + 9.0); del lum, br, i
        f = img.astype(np.float32)
        if water.any() and not water.all():
            water = ndi.binary_dilation(water, iterations=1); _, (iy, ix) = ndi.distance_transform_edt(water, return_indices=True)
            for k in range(3): f[..., k] = np.where(water, g(f[..., k][iy, ix], 8.0), f[..., k])
        ws = g(water.astype(np.float32), 1.5)
        for k in range(3): out[sel, k] = ndi.map_coordinates(f[..., k], [pr - ra, pc - ca], order=1, mode="nearest")
        wat[sel] = ndi.map_coordinates(ws, [pr - ra, pc - ca], order=1, mode="nearest")
    return out, wat

def etopo30(row, col):
    """ETOPO 2022 30s bedrock at places on the 60s grid; real lakes as dem60 has them, levelled"""
    out = np.zeros(len(row), np.float32); dem = mm("dem60.npy")
    with rasterio.open(os.path.join(DATA, "etopo", "ETOPO_2022_v1_30s_N90W180_bed.tif")) as ds:
        for sel in chunks(row, col):
            r = np.clip(row[sel], 0, 10799); c = col[sel] % 21600
            ra, rb = int(max(r.min() - 6, 0)), int(min(r.max() + 7, 10800)); ca, cb = int(max(c.min() - 6, 0)), int(min(c.max() + 7, 21600))
            e = ds.read(1, window=((ra * 2, rb * 2), (ca * 2, cb * 2))).astype(np.float32); e[e < -20000] = 0; d60 = np.asarray(dem[ra:rb, ca:cb]).astype(np.float32)
            lake = ndi.binary_dilation(np.abs(e.reshape(rb - ra, 2, cb - ca, 2).mean(axis=(1, 3)) - d60) > 1.5, iterations=1).repeat(2, 0).repeat(2, 1)
            e[lake] = d60.repeat(2, 0).repeat(2, 1)[lake]
            out[sel] = ndi.map_coordinates(e, [(r + 0.5) * 2 - 0.5 - ra * 2, (c + 0.5) * 2 - 0.5 - ca * 2], order=3, mode="nearest")
    return out

class Cells:
    """colour.cells for any points: the same cells, the same ragged seams"""
    def __init__(self):
        import colour as C
        from scipy.spatial import cKDTree
        self.C = C; f = os.path.join(FINE, "cells.npz")
        if not os.path.exists(f):
            pl = np.load(os.path.join(WORK, "place.npz")); lat, lon, st = pl["lat"], pl["lon"], pl["stretch"]; ok = np.isfinite(lat)
            w3 = g((_ss((st - C.ISO_FROM) / (C.ISO_FULL - C.ISO_FROM)) * ok).astype(np.float32), 2.0)
            _, (iy, ix) = ndi.distance_transform_edt(~ok, return_indices=True); la = np.radians(lat[iy, ix]); lo = np.radians(lon[iy, ix])
            V = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)
            rng = np.random.default_rng(5); gg = np.arange(C.CELL / 2, OUT, C.CELL); sx, sy = [a.ravel() for a in np.meshgrid(gg, gg)]
            sy = sy + rng.uniform(-0.33, 0.33, sy.shape) * C.CELL; sx = sx + rng.uniform(-0.33, 0.33, sx.shape) * C.CELL
            at = lambda y, x: np.stack([ndi.map_coordinates(V[..., k], [(y - 2) / 4, (x - 2) / 4], order=1, mode="nearest") for k in range(3)], -1)
            V0 = at(sy, sx); V0 /= np.linalg.norm(V0, axis=-1, keepdims=True); d = 8.0
            dx = (at(sy, sx + d) - at(sy, sx - d)) * 6371.0 / (2 * d); dy = (at(sy + d, sx) - at(sy - d, sx)) * 6371.0 / (2 * d)
            la0 = np.arcsin(np.clip(V0[:, 2], -1, 1)); lo0 = np.arctan2(V0[:, 1], V0[:, 0])
            e = np.stack([-np.sin(lo0), np.cos(lo0), np.zeros_like(lo0)], -1); n = np.stack([-np.sin(la0) * np.cos(lo0), -np.sin(la0) * np.sin(lo0), np.cos(la0)], -1)
            J = np.stack([np.stack([(e * dx).sum(-1), (e * dy).sum(-1)], -1), np.stack([(n * dx).sum(-1), (n * dy).sum(-1)], -1)], -2)
            U, sv, Vt = np.linalg.svd(J); Q = U @ Vt; gs = np.clip(np.sqrt(sv[:, 0] * sv[:, 1]), 1.2, 2.3)
            ns = [C._noise((OUT // 4, OUT // 4), 9, rng), C._noise((OUT // 2, OUT // 2), 3, rng), C._noise((OUT // 4, OUT // 4), 9, rng), C._noise((OUT // 2, OUT // 2), 3, rng)]
            np.savez(f, w3=w3, sy=sy, sx=sx, Q=Q, gs=gs, la0=la0, lo0=lo0, **{"n%d" % (i + 1): a.astype(np.float16) for i, a in enumerate(ns)})
        self.d = dict(np.load(f)); self.tree = cKDTree(np.stack([self.d["sy"], self.d["sx"]], -1))
    def __call__(self, Y, X):
        """-> weight of the unstretched detail (before the land and real-sea tests), two places (row60, col60), their mix"""
        d = self.d; sy, sx, Q, gs, la0, lo0 = d["sy"], d["sx"], d["Q"], d["gs"], d["la0"], d["lo0"]
        w = np.clip(ndi.map_coordinates(d["w3"], [Y / 4, X / 4], order=1, mode="nearest"), 0, 1)
        def nz(a, f):                              # the noise as the 12000 build reads it at block centres, smooth between them
            ra, ca = max(int(Y.min() // f) - 2, 0), max(int(X.min() // f) - 2, 0); sub = a[ra:int(Y.max() // f) + 3, ca:int(X.max() // f) + 3].astype(np.float32)
            return ndi.map_coordinates(sub, [(Y - (f - 1) / 2) / f - ra, (X - (f - 1) / 2) / f - ca], order=1, mode="nearest")
        wy = 16.0 * nz(d["n1"], 4) + 5.0 * nz(d["n2"], 2); wx = 16.0 * nz(d["n3"], 4) + 5.0 * nz(d["n4"], 2)
        dd, sid = self.tree.query(np.stack([Y + wy, X + wx], -1), k=2)
        def where(s):
            ddy = Y - sy[s]; ddx = X - sx[s]
            te = gs[s] * (Q[s, 0, 0] * ddx + Q[s, 0, 1] * ddy); tn = gs[s] * (Q[s, 1, 0] * ddx + Q[s, 1, 1] * ddy)
            latp = np.degrees(la0[s]) + tn / 111.19; lonp = np.degrees(lo0[s]) + te / (111.19 * np.maximum(np.cos(la0[s]), 0.05))
            return np.clip((90 - latp) * 60 - 0.5, 0, 10799), ((lonp + 180) * 60 - 0.5) % 21600
        return w, where(sid[:, 0]), where(sid[:, 1]), _ss(0.5 + (dd[:, 1] - dd[:, 0]) / (2 * self.C.FEATHER))

# ------------------------------------------------------------------ the land, a block at a time
_S = {}
def state():
    if not _S:
        import satgrade, colour as C
        _S.update(P=Places(), cells=Cells(), grade=satgrade.grade, C=C)
    return _S

def land_window(r0, r1, c0, c1):
    """-> the land's colour, graded and shaded, float32 ((r1 - r0) * F, (c1 - c0) * F, 3); None if the window has no land.
    What it is made of and why is at the top of this file."""
    S = state(); C = S["C"]
    a0, a1, b0, b1 = max(r0 - M, 0), min(r1 + M, OUT), max(c0 - M, 0), min(c1 + M, OUT)
    land = np.asarray(fm("landc.npy")[a0:a1, b0:b1])
    if not land.any(): return None
    crop = lambda a: np.asarray(a[a0:a1, b0:b1])
    H = crop(fm("heightc.npy")).astype(np.float32); level = crop(mm("waterlevel_c.npy")).astype(np.float32); has = crop(mm("ehas_adj.npy"))
    col = crop(fm("col.npy")); tr12 = crop(fm("trust.npy")).astype(np.float32) / 255.0; irow = crop(fm("isl_row.npy")); icol = crop(fm("isl_col.npy"))
    nr, nc = (a1 - a0) * F, (b1 - b0) * F
    YL, XL = np.meshgrid((np.arange(nr) + 0.5) / F - 0.5, (np.arange(nc) + 0.5) / F - 0.5, indexing="ij")
    up = lambda a, o=1: ndi.map_coordinates(a.astype(np.float32), [YL, XL], order=o, mode="nearest")
    Y = (YL + a0).ravel(); X = (XL + b0).ravel(); n = Y.size
    # ground colour.paint_over laid from a piece of real ground elsewhere reads the photograph where that piece is from
    moved = np.zeros(n, bool); join = None; Y0, X0 = Y, X
    if os.path.exists(os.path.join(WORK, "paint_from.npy")):
        pf = mm("paint_from.npy"); oy = up(crop(pf[0]), 0); ox = up(crop(pf[1]), 0); moved = ((oy != 0) | (ox != 0)).ravel()
        if moved.any():
            # where two pieces meet, or a piece and the ground that was there, the photograph changes place between one px and
            # the next: its fine band has no meaning across that line and is left out for a px or two either side
            k_ = oy * 4096.0 + ox; join = np.zeros(k_.shape, bool)
            join[1:] |= k_[1:] != k_[:-1]; join[:-1] |= k_[1:] != k_[:-1]; join[:, 1:] |= k_[:, 1:] != k_[:, :-1]; join[:, :-1] |= k_[:, 1:] != k_[:, :-1]
            join = np.clip(g(ndi.binary_dilation(join, iterations=F).astype(np.float32), 0.75 * F) * 1.6, 0, 1); del k_
            Y = Y + oy.ravel(); X = X + ox.ravel()
        del oy, ox
    # every point's real place: through the warps, or the real island its ocean island was given
    regs = S["P"](*S["P"].unnudged(Y, X))
    isl = np.isfinite(irow)
    if isl.any():
        _, (iy, ix) = ndi.distance_transform_edt(~isl, return_indices=True); on = up(isl) > 0.5; i = np.nonzero(on.ravel())[0]
        if len(i):
            # an island's places run on smoothly past its edge; two islands' do not into each other, so each point reads its own
            rr = up(irow[iy, ix]).ravel()[i]; cc = up(icol[iy, ix]).ravel()[i]
            keep = ~on.ravel(); regs = [(a[keep[a]], w[keep[a]], r[keep[a]], c[keep[a]], s[keep[a]]) for a, w, r, c, s in regs]
            regs.append((i, np.ones(len(i), np.float32), rr.astype(np.float64), cc.astype(np.float64) % 21600, np.zeros(len(i), bool)))
    Xw = np.zeros((n, 3), np.float32); wat = np.zeros(n, np.float32); Z = np.zeros(n, np.float32); ws = np.zeros(n, np.float32); mir = np.zeros(n, np.float32)
    for idx, wt, row, cl, sea in regs:
        if not len(idx): continue
        c3, w_ = bm500(row, cl); Xw[idx] += wt[:, None] * c3; wat[idx] += wt * w_; Z[idx] += wt * etopo30(row, cl); ws[idx] += wt; mir[idx] += wt * sea
    ok = ws > 1e-4; Xw[ok] /= ws[ok][:, None]; wat[ok] /= ws[ok]; Z[ok] /= ws[ok]; mir[ok] /= ws[ok]
    # a real city painted out (colour.urban_mask) stands on real ground: the photograph is the piece's, the fine relief its own
    if moved.any() and os.path.exists(os.path.join(WORK, "urban.npy")):
        ub = np.nonzero(moved & (up(ndi.binary_dilation(crop(mm("urban.npy")), iterations=3), 0) > 0.5).ravel())[0]
        if len(ub):
            Zu = np.zeros(len(ub), np.float32); wu = np.zeros(len(ub), np.float32)
            for idx, wt, row, cl, _ in S["P"](*S["P"].unnudged(Y0[ub], X0[ub])): Zu[idx] += wt * etopo30(row, cl); wu[idx] += wt
            oku = wu > 1e-4; Z[ub[oku]] = Zu[oku] / wu[oku]; del Zu, wu
    Xw = Xw.reshape(nr, nc, 3); wat = wat.reshape(nr, nc); Z = Z.reshape(nr, nc); ok = ok.reshape(nr, nc); mir = mir.reshape(nr, nc)
    # stretched ground: fine detail from cells laid true to scale, over the warp's broad colour
    w, p1, p2, mix = S["cells"](Y, X); w = w.reshape(nr, nc) * np.clip(up(land & has), 0, 1) * ok; Xh = Xw
    if w.max() > 0.02:
        sel = np.nonzero(w.ravel() > 0.005)[0]; i1, w1 = bm500(p1[0][sel], p1[1][sel]); i2, w2 = bm500(p2[0][sel], p2[1][sel]); mx = mix[sel, None]
        iso = Xw.reshape(n, 3).copy(); iso[sel] = mx * i1 + (1 - mx) * i2; iso = iso.reshape(nr, nc, 3)
        dry = np.zeros(n, np.float32); dry[sel] = 1 - _ss(np.maximum(w1, w2) / 0.35); w = w * dry.reshape(nr, nc); s = C.SPLIT * F
        Xi = np.stack([g(Xw[..., k], s) + iso[..., k] - g(iso[..., k], s) for k in range(3)], -1); Xh = Xw + w[..., None] * (Xi - Xw)
    # colour
    s = 1.5 * F; B = np.stack([up(col[..., k]) for k in range(3)], -1); dryw = ok * (1 - _ss(wat / 0.4)); tr = np.clip(up(tr12), 0, 1) * dryw
    # ground with no photograph of ground (colour.seam_mask) has no texture or fine relief worth reading at its place
    # either, unless it was laid from a piece of real ground: that piece's photograph is its own
    mv = moved.reshape(nr, nc)
    if os.path.exists(os.path.join(WORK, "seam.npy")): dryw = dryw * (1 - _ss((g(up(crop(mm("seam.npy"))), 1.0 * F) - 0.15) / 0.5) * ~mv)
    tr = np.where(mv, dryw, tr * (dryw > 0.02))
    GB = np.stack([g(B[..., k], s) for k in range(3)], -1); GX = np.stack([g(Xh[..., k], s) for k in range(3)], -1); hb = Xh - GX
    if join is not None: hb = hb * (1 - join)[..., None]
    lum = lambda c: c @ np.array([0.30, 0.59, 0.11], np.float32)
    rel = np.clip(lum(hb) / np.maximum(lum(GX), 30.0), -0.22, 0.22) * dryw * ~C.snowlike(np.clip(GX, 0, 255))
    made = B * (1.0 + rel)[..., None]; colh = np.clip(made + tr[..., None] * (GB + hb - made), 0, 255)
    # relief
    Bh = up(np.where(land, H, level), 3); dco = up(ndi.distance_transform_edt(land).astype(np.float32))
    te = _ss((dco - 0.8) / 2.5) * ok * (1 - _ss(g(mir, 1.5 * F) / 0.06)) * (1 - _ss((np.abs(g(Bh, s) - g(Z, s)) - 60.0) / 140.0)); te = g(te * (dryw > 0.02), 1.0 * F)
    Zh = Bh + te * ((Z - g(Z, s)) - (Bh - g(Bh, s)))
    k = np.clip(1.0 + 1.25 * (shade_of(Zh, 7.0, 1750.0 / F) - FLAT), 0.5, 1.22)
    o = (slice((r0 - a0) * F, (r0 - a0 + r1 - r0) * F), slice((c0 - b0) * F, (c0 - b0 + c1 - c0) * F))
    lm = up(land)[o] > 0.5; nl = int(lm.sum())
    return (S["grade"](colh) * k[..., None])[o], nl, float(tr[o][lm].mean()) if nl else 0.0, float((w[o][lm] > 0.5).mean()) if nl else 0.0

def land_block(rc):
    r0, c0 = rc; r1, c1 = min(r0 + BLOCK, OUT), min(c0 + BLOCK, OUT); res = land_window(r0, r1, c0, c1)
    if res is None: return 0, 0.0, 0.0
    lnd, nl, tr, w = res; out = fm("land.npy", "r+"); out[r0 * F:r1 * F, c0 * F:c1 * F] = np.clip(np.round(lnd * 128.0), 0, 65535).astype(np.uint16); out.flush(); del out
    return nl, tr, w

# ------------------------------------------------------------------ the sea, and the two together
def sea_window(r0, r1, c0, c1):
    """-> the sea's colour, shaded, float32, at F; its ice and shoals; and the land's share of every px (the smoothed edge)"""
    import seacolour
    PAD = 30; a0, a1, b0, b1 = max(r0 - PAD, 0), min(r1 + PAD, OUT), max(c0 - PAD, 0), min(c1 + PAD, OUT); crop = lambda a: np.asarray(a[a0:a1, b0:b1])
    L = crop(fm("landc.npy")); H = crop(fm("heightc.npy")).astype(np.float32); wt = (~L).astype(np.float32)
    ds = g(np.where(L, 0, -H) * wt, 6.0) / np.maximum(g(wt, 6.0), 1e-3)
    YL, XL = np.meshgrid((np.arange((r1 - r0) * F) + 0.5) / F - 0.5 + r0 - a0, (np.arange((c1 - c0) * F) + 0.5) / F - 0.5 + c0 - b0, indexing="ij")
    up = lambda a, o=1: ndi.map_coordinates(a.astype(np.float32), [YL, XL], order=o, mode="nearest")
    t = crop(mm("sea_tint.npy")).astype(np.float32); a = up(t[..., 3])[..., None] / 255.0
    sea, still = seacolour.colour(up(ds), YL + a0, XL + b0, up(crop(mm("sea_off.npy"))), up(crop(mm("sea_polar.npy"))), np.clip(a[..., 0] * 5.0, 0, 1))
    sea *= (1.0 + (up(crop(fm("ks.npy"))) - 1.0) * (1 - still))[..., None]
    if a.max() > 0: sea = sea * (1 - a) + np.stack([up(t[..., k]) for k in range(3)], -1) * a
    A = np.clip((up(crop(fm("soft.npy")), 3) / 255.0 - 0.5) * 2.0 * F + 0.5, 0, 1)
    return sea, A

def band(r0):
    r1 = min(r0 + BAND, OUT); out = fm("out.npy", "r+"); lnd = fm("land.npy")
    for c0 in range(0, OUT, 3000):
        sea, A = sea_window(r0, r1, c0, c0 + 3000); o = (slice(r0 * F, r1 * F), slice(c0 * F, (c0 + 3000) * F))
        rgb = sea + A[..., None] * (np.asarray(lnd[o]).astype(np.float32) / 128.0 - sea)
        dr = np.random.default_rng([1, r0, c0])                  # dither: a slow gradient cut to 8 bits is a staircase
        rgb += (dr.random(rgb.shape, dtype=np.float32) - dr.random(rgb.shape, dtype=np.float32)) * 0.9 + 0.5
        out[o] = np.clip(rgb, 0, 255).astype(np.uint8)
    out.flush(); return r0

if __name__ == "__main__":
    import multiprocessing as mp
    if "--window" in sys.argv:
        i = sys.argv.index("--window"); r0, r1, c0, c1 = [int(v) for v in sys.argv[i + 1:i + 5]]; prepare(); tiles()
        lnd = land_window(r0, r1, c0, c1); sea, A = sea_window(r0, r1, c0, c1); rgb = sea if lnd is None else sea + A[..., None] * (lnd[0] - sea)
        write_png(sys.argv[i + 5], np.clip(rgb + 0.5, 0, 255).astype(np.uint8)); sys.exit(0)
    prepare(); tiles(); Cells()
    import seacolour, polar
    land = np.load(os.path.join(FINE, "landc.npy")); pc = np.load(os.path.join(WORK, "polar_cache.npz")); made = np.zeros(land.shape, bool)
    for i, (_, rs, cs, _) in enumerate(polar.REGIONS): made[rs, cs] |= pc["P%d" % i]
    seacolour.aux(WORK, land, made); del made, pc
    np.lib.format.open_memmap(os.path.join(FINE, "land.npy"), "w+", np.uint16, (N, N, 3)).flush()
    np.lib.format.open_memmap(os.path.join(FINE, "out.npy"), "w+", np.uint8, (N, N, 3)).flush()
    blocks = [(r, c) for r in range(0, OUT, BLOCK) for c in range(0, OUT, BLOCK) if land[max(r - M, 0):r + BLOCK + M, max(c - M, 0):c + BLOCK + M].any()]
    blocks.sort(key=lambda rc: -int(land[rc[0]:rc[0] + BLOCK, rc[1]:rc[1] + BLOCK].sum())); del land
    workers = max(2, min(8, (os.cpu_count() or 4) - 2))
    with mp.get_context("spawn").Pool(workers) as pool:
        px = tr = w = 0.0
        for i, (n, t, c) in enumerate(pool.imap_unordered(land_block, blocks)):
            px += n; tr += n * t; w += n * c
            if i % 40 == 39: tick("land: %d of %d blocks" % (i + 1, len(blocks)))
        tick("land: %d blocks; the photograph as it is on %.0f%% of the land, unstretched detail on %.1f%%" % (len(blocks), 100 * tr / max(px, 1), 100 * w / max(px, 1)))
        for i, _ in enumerate(pool.imap_unordered(band, range(0, OUT, BAND))):
            if i % 10 == 9: tick("sea and all: %d of %d bands" % (i + 1, OUT // BAND))
    write_png(os.path.join(LAYERS, "hybrid.png"), fm("out.npy"), zlevel=1); tick("wrote hybrid.png at %d px" % N)
    os.remove(os.path.join(FINE, "land.npy")); os.remove(os.path.join(FINE, "out.npy"))
