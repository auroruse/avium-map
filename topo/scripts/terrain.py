"""Condition sampled elevation to Avium: land where Avium has land, sea where it has sea.
-> work/height_raw.npy (int16 metres, 12000x12000; land >= 1, sea <= -1)"""
import sys, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
OUT = 12000
KM = 1.75                       # real km per output px, typical for this overlay
FLAT = 60.0                     # placeholder height for land with no Earth counterpart that polar.py does not cover
t0 = time.time()
E = np.load(os.path.join(WORK, "ereal_adj.npy")); has = np.load(os.path.join(WORK, "ehas_adj.npy"))
mono = read_png(os.path.join(LAYERS, "mono.png"))[:, :, 0] > 0
land = ndi.gaussian_filter(mono.repeat(2, 0).repeat(2, 1).astype(np.float32), 1.8) > 0.5
del mono
region = np.load(os.path.join(WORK, "region.npy"))
ovland = (region != 0).repeat(4, 0).repeat(4, 1)
print("avium land %.2f%% | with real elevation %.2f%% of land" % (100 * land.mean(), 100 * (land & has).sum() / land.sum()))

# ---------------- ground that landed on real water
# Where the fit is a little off at a coast, Avium land samples the real sea and would come out as a dead-flat strip.
# Those pixels take the relief of the valid ground next to them, mirrored across the edge of the strip, so the
# terrain carries on to the shore. Counted and reported; it is a repair, the georeference is what is being repaired.
def tick(what): print("  [%4.0f s] %s" % (time.time() - t0, what), flush=True)
tick("inputs loaded")
valid = land & has & (E >= 2.0)
dist, (iy, ix) = ndi.distance_transform_edt(~valid, return_indices=True)
fill = land & ~valid & (dist <= 80)
yy, xx = np.nonzero(fill)
qy, qx = iy[yy, xx], ix[yy, xx]
my = np.clip(2 * qy - yy, 0, OUT - 1); mx = np.clip(2 * qx - xx, 0, OUT - 1)
near = E[qy, qx]; mir = np.where(valid[my, mx], E[my, mx], near)
E[yy, xx] = np.maximum(0.7 * mir + 0.3 * near, 2.0); has[yy, xx] = True
E[yy, xx] = np.maximum(ndi.gaussian_filter(E, 1.2)[yy, xx], 2.0)      # take the facets out of the repaired ground
print("land repaired by mirroring: %.2f%% of Avium land (of which landed on real water: %.2f%%)" % (100 * fill.sum() / land.sum(), 100 * (fill & np.load(os.path.join(WORK, "ehas_adj.npy"))).sum() / land.sum()))
del dist, iy, ix, valid, fill

# ---------------- land
tick("repair")
h = np.where(has, np.maximum(E, 2.0), FLAT).astype(np.float32)
# the polar continents have no Earth under them: their ground is made from their Talopedia articles (polar.py)
import polar
pol = polar.build(land, has, KM); hasl = has.copy()
for rs, cs, P, z, _ in pol:
    hc = h[rs, cs]; hc[P] = z[P]; hl = hasl[rs, cs]; hl |= P
# Eivorie has its own ground, made from the Eivorian map (eivorie.py); its rivers are fictional and drawn
tick("polar continents")
import eivorie
h = eivorie.build(h, land, KM)
wl, nw = ndi.label(~land); wsz = np.bincount(wl.ravel()); ocean = wsz[1:].argmax() + 1
# a coast Earth does not have: high ground at an Avium-made shore comes down to the sea like a coastal range (flank.py)
tick("Eivorie")
import flank
h_pre = h.copy(); h = flank.descend(h, land, wl == ocean, E, has, KM)
# every inland water body is a lake at the height of its own shore, not a piece of sea
level = np.zeros((OUT, OUT), np.float32); nlake = 0
for i, sl in enumerate(ndi.find_objects(wl), 1):
    if i == ocean or sl is None: continue
    sl = (slice(max(sl[0].start - 6, 0), sl[0].stop + 6), slice(max(sl[1].start - 6, 0), sl[1].stop + 6))
    m = wl[sl] == i; ring = ndi.binary_dilation(m, iterations=5) & land[sl] & hasl[sl]
    if ring.sum() < 5: continue
    lv = float(max(np.percentile(h[sl][ring], 30), 0.0)); level[sl][m] = lv; nlake += 1
tick("flank and lakes")
print("lakes given their own level:", nlake, "| highest", float(level.max()), "m")
d_in, (iy, ix) = ndi.distance_transform_edt(land, return_indices=True)   # px to the nearest water, and which water
base = level[iy, ix]; del iy, ix
t = np.clip(d_in.astype(np.float32) / 4.0, 0, 1) ** 0.8
h = h * t + (base + 1.0) * (1 - t)                 # within 4 px of water the ground comes down (or up) to that water's level; beyond, untouched
del t
del d_in, base
np.save(os.path.join(WORK, "waterlevel.npy"), level); lake = (~land) & (wl != ocean); del wl

# ---------------- sea
tick("shore levels")
import seafloor
depth = seafloor.build(land, (~land) & ~lake, h_pre, E, (~land) & ovland & has, KM); del h_pre
depth = np.maximum(depth, 1.0)
for rs, cs, P, _, sea in pol:                      # Hyperborea's trench, the Tartarean Rift's troughs
    dc = depth[rs, cs]; np.maximum(dc, sea, out=dc)
del pol, hasl
H = np.where(land, h, -depth)
tick("sea floor")
np.save(os.path.join(WORK, "height_raw.npy"), np.round(H).astype(np.int16)); np.save(os.path.join(WORK, "land12k.npy"), land)
print("done", round(time.time() - t0), "s | land max", float(h[land].max()), "| sea min", float(-depth[~land].max()))
