"""A coast Earth does not have. Where Avium's shore cuts through ground that is high on Earth (the Himalayan Sea against Tibet
and the Tarim basin), the real relief would stand as a wall at the water. Such a shore is known by what lies off it: the real
elevation carries on under the sea as high ground. Behind it the land is brought down the way a coastal range comes down:
lowland at the shore, foothills, a range front, and the full height only about 300 km in, cut by the valleys of the rivers
that would drain it. Real coasts, however mountainous, have real sea off them and are left alone."""
import heapq, numpy as np
from scipy import ndimage as ndi
def _ss(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
def _field(shape, sig, rng):
    g = ndi.gaussian_filter(rng.standard_normal(shape).astype(np.float32), sig); return g / np.abs(g).max()
def _up(a, shape):
    yy = (np.arange(shape[0]) + 0.5) * a.shape[0] / shape[0] - 0.5; xx = (np.arange(shape[1]) + 0.5) * a.shape[1] / shape[1] - 0.5
    return ndi.map_coordinates(a, np.meshgrid(yy, xx, indexing="ij"), order=1, mode="nearest")
def envelope(u): return 40.0 + 260.0 * _ss(u / 45.0) + 1300.0 * _ss((u - 30.0) / 110.0) + 3600.0 * _ss((u - 110.0) / 170.0)

def descend(h, land, ocean, E, has, KM, seed=5, log=print):
    """h: land heights; ocean: the sea proper, not lakes; E, has: real elevation and where there is any. -> lowered heights"""
    rng = np.random.default_rng(seed); shp = h.shape; S = 2; cs = (shp[0] // S, shp[1] // S); m = cs[1]
    d_oc, (oy, ox) = ndi.distance_transform_edt(~ocean, return_indices=True)
    # how high the real ground stands under the sea off each stretch of shore
    off = ocean & has; num = ndi.gaussian_filter(np.where(off, np.maximum(E, 0), 0).astype(np.float32), 10.0); den = ndi.gaussian_filter(ocean.astype(np.float32), 10.0)
    made = _ss(((num / np.maximum(den, 1e-3))[oy, ox] - 150.0) / 350.0); del num, den, off, oy, ox
    made = ndi.gaussian_filter(made, 20.0)
    u = (d_oc * KM).astype(np.float32) / (1.15 * np.exp(0.35 * _up(_field((shp[0] // 8, shp[1] // 8), 6.0, rng), shp))); del d_oc   # distance inland, in km of envelope
    # Valleys. The flank gets a drainage of its own: the bare envelope, roughened, is flooded from the sea inland (lowest ground
    # first), which gives every cell the neighbour it drains to. The more ground drains through a cell the further down its
    # valley is cut, so along a trunk stream the lowland reaches far into the range, and the cut dies out toward each headwater.
    uc = np.ascontiguousarray(u[::S, ::S][:cs[0], :cs[1]]); band = land[::S, ::S][:cs[0], :cs[1]] & (made[::S, ::S][:cs[0], :cs[1]] > 0.02) & (uc < 450.0)
    band[0], band[-1], band[:, 0], band[:, -1] = False, False, False, False
    f3 = _field(cs, 1.2, rng); fb = 0.55 * _field(cs, 8.0, rng) + 0.3 * _field(cs, 3.0, rng) + 0.15 * f3
    ur = uc * (1.0 + 0.25 * fb)                                           # the hills between the valleys: the front is not a straight line
    z0 = (envelope(ur) + 40.0 * f3).ravel(); bf = band.ravel(); seen = np.zeros(bf.size, bool); pred = np.full(bf.size, -1, np.int32); del f3
    seeds = np.flatnonzero((ndi.binary_dilation(uc == 0) & band).ravel()); seen[seeds] = True
    heap = [(float(z0[i]), int(i)) for i in seeds]; heapq.heapify(heap); order = []; nb = (-m - 1, -m, -m + 1, -1, 1, m - 1, m, m + 1)
    while heap:
        z, i = heapq.heappop(heap); order.append(i)
        for o in nb:
            j = i + o
            if bf[j] and not seen[j]: seen[j] = True; pred[j] = i; heapq.heappush(heap, (max(float(z0[j]), z), j))
    order = np.array(order, np.int64); pos = np.full(bf.size, -1, np.int32); pos[order] = np.arange(len(order)); pp = np.where(pred[order] >= 0, pos[pred[order]], -1).tolist(); acc = [1] * len(order)
    for k in range(len(order) - 1, -1, -1):
        if pp[k] >= 0: acc[pp[k]] += acc[k]
    A = np.ones(bf.size, np.float32); A[order] = acc; wv = _ss(np.log(A / 2.0) / np.log(300.0)).reshape(cs) * band; del A, acc, pp, pos, pred, seen, z0
    ue = np.where(band, ur * (1.0 - 0.5 * wv * (1.0 - 0.6 * _ss((uc - 150.0) / 250.0))), uc); del ur
    for _ in range(8):                                       # valley sides: the cut widens away from the stream
        for dy, dx, c in ((0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0), (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)):
            ue = np.minimum(ue, np.roll(ue, (dy, dx), (0, 1)) + 4.5 * KM * S * c)
    u = _up(ndi.gaussian_filter(ue, 0.7), shp); del ue, uc
    env = envelope(u); del u
    lf = land.astype(np.float32); hlp = ndi.gaussian_filter(np.where(land, h, 0), 30.0 / KM) / np.maximum(ndi.gaussian_filter(lf, 30.0 / KM), 1e-3); del lf
    sc = np.clip(env / np.maximum(hlp, 1.0), 0, 1); del env
    low = hlp * sc + (h - hlp) * np.sqrt(sc); del hlp
    lowered = land & (made > 0.05) & (sc < 0.97)
    log("high ground brought down to a coast Earth does not have: %.2f%% of land, drained by %d valley cells" % (100 * lowered.sum() / max(land.sum(), 1), int((wv > 0.5).sum())))
    return np.where(land, np.maximum(h + made * (low - h), 2.0), h)
