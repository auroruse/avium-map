"""The Hybrid map's sea: the old shaded sea, as varied as the land beside it (user, 17 Nov 2026: "The sea should be just
as varied as land ... the Tartarus red sea, Hyperborean Ocean being very cold").

- Depth sets the tone, read off a smoothed depth: the sea floor carries a flat shelf a few metres deep right along every
  shore, and coloured as it stands that is a pale band round every coast, which looked drawn beside photographed land.
- Temperature sets the hue. The Hyperborean Ocean and the water under the katabatic corridor off it (hyperborea.md: the
  winds reach Spatrya, Kanada and the Arctic Sea) are slate and grey-green; the belt round the meteorological equator,
  which Avium's tilt puts well south of the geographic one (avium.md), is bluer with teal over its shoals; Tartarus's
  seas are cold again.
- The Hyperborean summer's plankton (hyperborea.md: "massive phytoplankton blooms") marbles its water milky green.
- Ice adrift off both polar continents: brash and floes drawn out in the eddies of the cold water, thickest under the
  coast, gone a few hundred km out, and none in the Rift's warm water.
- Reefs and banks where warm water is shallow (the east of the Sahara Sea above all): pale sand and darker coral in a
  mottle, in stretches, never a band of one width.
(user, 17 Nov 2026: "Drifting ice, reefs and banks in the tropics (Sahara Sea?)". Silt plumes off the big rivers' mouths
were built at the same asking and taken out again at the user's word the same day.)
- The red water of the Tartarean Rift is laid over all of it by render.py (work/sea_tint.npy, colour.py).
Everything here is a function of where a pixel is on the whole map, so a crop and the whole come out the same."""
import numpy as np
from scipy import ndimage as ndi
OUT = 12000
def _ss(x): x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)

_grids = {}
def noise(yy, xx, scale, seed):
    """smooth noise in about -1..1, features `scale` px across, the same wherever it is asked for"""
    k = (scale, seed)
    if k not in _grids:
        g = np.random.default_rng(1000 + seed).standard_normal((OUT // scale + 6, OUT // scale + 6)).astype(np.float32); _grids[k] = g / 0.62
    return ndi.map_coordinates(_grids[k], [yy / scale + 2, xx / scale + 2], order=3, mode="nearest") * 0.62

BASE = [(-9000, (9, 26, 54)), (-5000, (15, 40, 76)), (-3000, (21, 52, 92)), (-1200, (28, 66, 106)), (-200, (36, 82, 118)), (0, (46, 96, 128))]
COLD = [(-9000, (12, 22, 38)), (-5000, (19, 33, 52)), (-3000, (26, 44, 63)), (-1200, (33, 54, 72)), (-200, (41, 65, 80)), (0, (50, 77, 88))]
WARM = [(-9000, (7, 28, 62)), (-5000, (12, 44, 86)), (-3000, (17, 58, 104)), (-1200, (24, 76, 120)), (-200, (34, 98, 134)), (0, (50, 120, 142))]
BLOOM = np.array([92, 142, 132], np.float32)
FLOE = np.array([238, 242, 247], np.float32)
LAGOON, SAND, CORAL = [np.array(c, np.float32) for c in ((56, 146, 158), (148, 206, 194), (34, 104, 116))]
ICE_REACH = 230.0      # px from a polar coast at which the drift ice has thinned to a third

def aux(work, land, polar):
    """What the sea needs to know that a pixel alone does not, on the whole map (cached in work/): px to the nearest
    land and px to the nearest polar coast -> two arrays, memory-mapped"""
    import os
    f = [os.path.join(work, "sea_%s.npy" % n) for n in ("off", "polar")]
    if not all(os.path.exists(p) for p in f):
        np.save(f[0], np.minimum(ndi.distance_transform_edt(~land), 65535).astype(np.uint16))
        np.save(f[1], np.minimum(ndi.distance_transform_edt(~polar), 65535).astype(np.uint16))
    return [np.load(p, mmap_mode="r") for p in f]

def ramp(v, stops):
    xs = [s[0] for s in stops]; return np.stack([np.interp(v, xs, [s[1][c] for s in stops]).astype(np.float32) for c in range(3)], -1)

def fields(yy, xx):
    """-> Avium latitude, how cold (0..1) and how warm (0..1) the water is"""
    lat = 90.0 * (1 - (xx + yy + 1) / OUT); th = np.degrees(np.arctan2(yy + 0.5, xx + 0.5))
    wob = 4.0 * noise(yy, xx, 900, 1) + 2.0 * noise(yy, xx, 300, 2)                  # no isotherm is a ruled line
    cor = 18.0 * np.exp(-((th - 43.0) / 17.0) ** 2)                                # the katabatic corridor carries the cold south
    cold = np.maximum(_ss((lat + wob + cor - 36.0) / 22.0), _ss((-lat + wob - 50.0) / 14.0))
    warm = _ss(1.0 - np.abs(lat + wob + 12.0) / 30.0) * (1 - cold)
    return lat, cold, warm

def colour(depth, yy, xx, offshore, polar, warmth=None):
    """depth: metres below the surface, smoothed; yy, xx: map px (12000 grid); offshore, polar: px to the nearest land and
    to the nearest polar coast; warmth: 0..1 where the water is too warm for ice (the
    Rift's) -> float RGB, unshaded, and how much of it is ice or
    shoal and should not take the sea floor's shading (0..1)"""
    lat, cold, warm = fields(yy, xx); z = -depth
    c = ramp(z, BASE); c += cold[..., None] * (ramp(z, COLD) - c); c += warm[..., None] * (ramp(z, WARM) - ramp(z, BASE))
    # plankton in the Hyperborean summer: marbled, in fields, thinning southward
    wy = yy + 70.0 * noise(yy, xx, 170, 3) + 22.0 * noise(yy, xx, 60, 4); wx = xx + 70.0 * noise(yy, xx, 170, 5) + 22.0 * noise(yy, xx, 60, 6)
    marble = np.clip(0.5 + 0.9 * (noise(wy, wx, 70, 7) + 0.5 * noise(wy, wx, 28, 8) + 0.25 * noise(wy, wx, 11, 11)), 0, 1) ** 1.5      # wisps, never shapes with an edge
    where = _ss((lat + 3.0 * noise(yy, xx, 500, 9) - 47.0) / 10.0) * _ss((noise(yy, xx, 420, 10) + 0.15) / 0.5)
    where = where * _ss((offshore - 90.0 + 30.0 * noise(yy, xx, 200, 12)) / 110.0)      # out in the open water, clear of the coast and its shelf
    c += (0.17 * marble * where)[..., None] * (BLOOM - c)
    # reefs and banks: warm water, shallow, in stretches
    bank = warm * _ss((85.0 - depth) / 60.0) * _ss((noise(yy, xx, 520, 13) + 0.6 * noise(yy, xx, 150, 14) + 0.3) / 0.5)
    m1 = noise(yy, xx, 10, 15); m2 = noise(yy, xx, 4, 16)
    reef = LAGOON + _ss(0.5 + 0.9 * m1 + 0.5 * m2)[..., None] * (SAND - LAGOON)
    reef += (_ss((m2 - 0.3 * m1 - 0.25) / 0.3) * 0.6)[..., None] * (CORAL - reef)
    bank = bank * (0.55 + 0.45 * _ss(0.5 + 0.8 * noise(yy, xx, 26, 17)))                  # thinning and thickening along its length
    c += (0.82 * bank)[..., None] * (reef - c)
    # ice adrift off the polar coasts: smoke-like in the eddies, in fields
    smoke = np.clip(0.5 + 1.1 * (noise(wy, wx, 80, 22) + 0.5 * noise(wy, wx, 30, 23) + 0.3 * noise(wy, wx, 12, 24)), 0, 1) ** 2.6
    grain = _ss(0.5 + 0.9 * noise(yy, xx, 16, 25))                                      # a little thicker and thinner: any finer and it is a maze
    dens = np.exp(-polar / (ICE_REACH * (0.6 + 0.8 * _ss(0.5 + 0.7 * noise(yy, xx, 380, 26))))) * cold
    ice = np.clip(1.9 * dens * smoke * (0.86 + 0.14 * grain), 0, 0.94)
    if warmth is not None: ice = ice * (1 - warmth)
    c += ice[..., None] * (FLOE - c)
    return c, np.clip(np.maximum(ice, 0.6 * bank), 0, 1)
