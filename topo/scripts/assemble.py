"""Sample real elevation through every region's warp onto the 12000px Avium grid.
Regions overlap by D px and are cross-faded, so borders between real neighbours are seamless and sutures are soft.
-> work/ereal.npy (float32 m), work/ehas.npy (bool)"""
import sys, pickle, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
OUT, K = 12000, 4               # output size; output px per 3000-grid px
D = 6                           # cross-fade half-width, 3000-grid px
EXT = 24                        # how far past overlay land a region's warp is trusted, 3000-grid px
STEP = 16                       # warp evaluated every STEP output px, then interpolated
t0 = time.time()
region = np.load(os.path.join(WORK, "region.npy")); warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
dem = np.load(os.path.join(WORK, "dem60.npy"))
dem = np.concatenate([dem[:, -1:], dem, dem[:, :1]], 1).astype(np.float32)        # wrap one column each side
# distance of every real sea cell from real land (in grid cells): ground that still lands just off a real coast samples
# the real terrain mirrored across that coast. The mirror point comes from the smooth distance field, not from the
# nearest cell, so it moves continuously and leaves no stripes.
sf = os.path.join(WORK, "seadist.npy")
if not os.path.exists(sf):
    np.save(sf, ndi.distance_transform_edt(dem[:, 1:-1] <= 0).astype(np.float32))
SD = np.load(sf); SD = np.concatenate([SD[:, -1:], SD, SD[:, :1]], 1)
fitted = np.isin(region, list(warps.keys()))
dist, (iy, ix) = ndi.distance_transform_edt(~fitted, return_indices=True)
own = np.where(dist <= EXT, region[iy, ix], 0).astype(np.int32)
np.save(os.path.join(WORK, "own.npy"), own)
RX = Relax(WORK)
acc = np.zeros((OUT, OUT), np.float32); wsum = np.zeros((OUT, OUT), np.float32)
objs = ndi.find_objects(own)
for n, (b, W) in enumerate(warps.items()):
    sl = objs[b - 1]
    if sl is None: continue
    r0, r1 = max(sl[0].start - D - 1, 0), min(sl[0].stop + D + 1, 3000)
    c0, c1 = max(sl[1].start - D - 1, 0), min(sl[1].stop + D + 1, 3000)
    m = own[r0:r1, c0:c1] == b
    w3 = np.clip(1 - ndi.distance_transform_edt(~m) / D, 0, 1).astype(np.float32)
    h, w = (r1 - r0) * K, (c1 - c0) * K
    # weights to output resolution (bilinear)
    yy = (np.arange(h) + 0.5) / K - 0.5; xx = (np.arange(w) + 0.5) / K - 0.5
    wt = ndi.map_coordinates(w3, np.meshgrid(yy, xx, indexing="ij"), order=1, mode="nearest")
    if wt.max() <= 0: continue
    # warp on a coarse lattice of output px
    gy = np.arange(0, h + STEP, STEP); gx = np.arange(0, w + STEP, STEP)
    GX, GY = np.meshgrid(gx, gy)
    x6 = (c0 * K + GX + 0.5) / 2; y6 = (r0 * K + GY + 0.5) / 2
    lon, lat = W(x6, y6)
    lon, lat = Relax.apply(RX.region(b), lon, lat, x6, y6)        # stretch cap and coast correction
    lo = np.radians(lon); la = np.radians(lat)
    V = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    py, px = np.meshgrid(np.arange(h) / STEP, np.arange(w) / STEP, indexing="ij")
    v = np.stack([ndi.map_coordinates(V[k], [py, px], order=1, mode="nearest") for k in range(3)])
    del py, px
    v /= np.maximum(np.sqrt((v ** 2).sum(0)), 1e-9)
    lat = np.degrees(np.arcsin(np.clip(v[2], -1, 1))); lon = np.degrees(np.arctan2(v[1], v[0]))
    del v
    row = (90 - lat) * 60 - 0.5; col = (lon + 180) * 60 - 0.5 + 1
    e = ndi.map_coordinates(dem, [row, col], order=1, mode="nearest")
    sea = (e <= 0) & (wt > 0)
    if sea.any():
        r_ = row[sea]; c_ = col[sea]
        d = ndi.map_coordinates(SD, [r_, c_], order=1, mode="nearest")
        gr = ndi.map_coordinates(SD, [r_ + 1.5, c_], order=1, mode="nearest") - ndi.map_coordinates(SD, [r_ - 1.5, c_], order=1, mode="nearest")
        gc = ndi.map_coordinates(SD, [r_, c_ + 1.5], order=1, mode="nearest") - ndi.map_coordinates(SD, [r_, c_ - 1.5], order=1, mode="nearest")
        gn = np.maximum(np.hypot(gr, gc), 1e-6); step = 2.0 * d + 1.5                       # across the coast and as far inland again
        mr = np.clip(r_ - gr / gn * step, 0, 10799); mc = (c_ - 1 - gc / gn * step) % 21600 + 1
        em = ndi.map_coordinates(dem, [mr, mc], order=1, mode="nearest")
        e[sea] = np.maximum(em, 1.0)
    sub = (slice(r0 * K, r1 * K), slice(c0 * K, c1 * K))
    acc[sub] += wt * e; wsum[sub] += wt
    if n % 20 == 0: print(n, "regions", round(time.time() - t0), "s", flush=True)
has = wsum > 1e-4
acc[has] /= wsum[has]; acc[~has] = 0
np.save(os.path.join(WORK, "ereal.npy"), acc); np.save(os.path.join(WORK, "ehas.npy"), has)
print("done", round(time.time() - t0), "s; covered", round(100 * has.mean(), 1), "% of the grid; elevation range", float(acc.min()), float(acc.max()))
