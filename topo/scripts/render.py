"""height.npy -> the drawings the map tiles: layers/relief.png, terrain.png, hybrid.png, tint.png, contours.png (12000px).
Name some of them (render.py hybrid) to write only those; with no names it writes all five."""
import sys, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
t0 = time.time()
ONLY = set(sys.argv[1:])
def want(name): return not ONLY or name in ONLY
Hi = np.load(os.path.join(WORK, "height.npy")); land = np.load(os.path.join(WORK, "land12k.npy"))
H = Hi.astype(np.float32); del Hi
CELL = 1750.0                       # real metres per px
LAND = np.array([180, 179, 191], np.float32); OCEAN = np.array([62, 78, 111], np.float32); COAST = np.array([43, 51, 72], np.float32)

def shade_of(z, zf):
    """soft multi-directional hillshade, 0..1, 0.5-ish on flat ground"""
    gy, gx = np.gradient(z, CELL); gx *= zf; gy *= zf
    out = np.zeros(z.shape, np.float32)
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    for az, w in ((315, 0.55), (270, 0.15), (360, 0.15), (225, 0.15)):
        a = np.radians(az); alt = np.radians(42)
        lx, ly, lz = np.sin(a) * np.cos(alt), -np.cos(a) * np.cos(alt), np.sin(alt)     # image y points down
        out += w * np.clip((-gx * lx - gy * ly + lz) * nz, 0, 1)
    return out
level = np.load(os.path.join(WORK, "waterlevel_c.npy"))
Hl = np.where(land, H, level)                       # the land surface, with each lake filled to its level
sh_l = shade_of(Hl, 7.0)
flat = np.sin(np.radians(42))
k = np.where(land, 1.0 + 1.25 * (sh_l - flat), 1.0 + 1.1 * (shade_of(np.where(land, 0, H), 5.0) - flat)).astype(np.float32)
del sh_l
k = np.clip(k, 0.5, 1.22)
print("shading", round(time.time() - t0), "s", flush=True)

coast = ndi.binary_dilation(land, iterations=1) & ~ndi.binary_erosion(land, iterations=2)
# land12k is the drawn ground plus the strip of the white coastline that tile.mjs inks on the base map,
# and the nation fills in borders.PNG stop where the drawn ground stops. All of that strip is coast here
# too, or it shows as bare land between the fills and the coast (grey on relief, green on terrain).
b = read_png(os.path.join(LAYERS, "base.PNG"))[..., :3].astype(np.int16)
ground = (np.abs(b - np.array([180, 179, 191], np.int16)) < 14).all(-1).repeat(2, 0).repeat(2, 1); del b
coast |= land & ~ground
print("coast strip inked:", int((land & ~ground).sum()), "px", flush=True); del ground

def ramp(v, stops):
    xs = [s[0] for s in stops]
    return np.stack([np.interp(v, xs, [s[1][c] for s in stops]).astype(np.float32) for c in range(3)], -1)
SEA = [(-9000, (26, 35, 62)), (-6200, (38, 50, 82)), (-5000, (49, 63, 96)), (-3800, (62, 78, 111)), (-2600, (74, 93, 128)), (-1200, (88, 109, 145)), (-200, (101, 123, 159)), (0, (110, 133, 168))]
def finish(rgb, path, ink=True):
    if not want(os.path.basename(path)[:-4]): return
    if ink: rgb[coast] = COAST
    write_png(path, np.clip(rgb, 0, 255).astype(np.uint8), zlevel=1)   # an intermediate for the tiler: speed over size
    print("wrote", os.path.basename(path), round(time.time() - t0), "s", flush=True)

# ---- relief: the base map's own grey and navy, modelled by the terrain
sea_rgb = ramp(H, SEA) * k[..., None]
rgb = np.where(land[..., None], LAND[None, None] * k[..., None], sea_rgb)
finish(rgb, os.path.join(LAYERS, "relief.png"))
# ---- terrain: elevation tints
TINT = [(0, (116, 148, 122)), (150, (138, 162, 124)), (400, (170, 176, 128)), (800, (196, 180, 128)), (1400, (192, 158, 118)),
        (2200, (170, 132, 108)), (3200, (150, 124, 118)), (4200, (190, 182, 186)), (5200, (232, 232, 238)), (9000, (250, 250, 252))]
# Hyperborea and Tartarus in a palette of their own, so their coasts and heights do not read as farmland and steppe
# (user, 15 Nov 2026): at every height the main ramp's CIELAB lightness less 10, in slate, blue-grey and violet-grey
POLAR = [(0, (104, 116, 128)), (150, (117, 131, 144)), (400, (134, 147, 163)), (800, (144, 154, 171)), (1400, (131, 137, 156)),
         (2200, (111, 113, 134)), (3200, (107, 102, 124)), (4200, (164, 153, 175)), (5200, (211, 201, 216)), (9000, (225, 220, 227))]
import polar
def landtint(shade):
    t = ramp(H, TINT)
    has = np.load(os.path.join(WORK, "ehas_adj.npy"), mmap_mode="r")
    for _, rs, cs, corner in polar.REGIONS:                  # the polar continents: land with no Earth under it, in their corners
        yy, xx = np.mgrid[rs, cs]; m = (land[rs, cs] & ~np.asarray(has[rs, cs]) & corner(yy, xx))[..., None]; del yy, xx
        t[rs, cs] = np.where(m, ramp(H[rs, cs], POLAR), t[rs, cs])
    return t * k[..., None] if shade else t
rgb = np.where(land[..., None], landtint(True), sea_rgb)
del sea_rgb
finish(rgb, os.path.join(LAYERS, "terrain.png"))
# ---- hybrid: the terrain's land over a deep blue sea, for the Hybrid map. No line is inked at the coast: this sea is
# dark and blue enough against any land beside it to make the shore by itself, where the slate sea above is not. The
# shore is eased over a pixel instead, since land12k is a 6000 px mask and its edge would otherwise step in twos.
if want("hybrid"):
    HSEA = [(-9000, (10, 28, 58)), (-5000, (17, 42, 78)), (-3000, (24, 56, 96)), (-1200, (32, 72, 112)), (-200, (44, 92, 128)), (0, (58, 110, 140))]
    rgb = np.where(land[..., None], landtint(True), ramp(H, HSEA) * k[..., None])
    shore = ndi.binary_dilation(land, iterations=1) & ~ndi.binary_erosion(land, iterations=1)
    for c in range(3): rgb[..., c][shore] = ndi.gaussian_filter(rgb[..., c], 0.7)[shore]
    del shore
    finish(rgb, os.path.join(LAYERS, "hybrid.png"), ink=False)
# ---- tint: the terrain's colours with no shading, for the Terrain map with Relief switched off
rgb = np.where(land[..., None], landtint(False), ramp(H, SEA))
finish(rgb, os.path.join(LAYERS, "tint.png"))
del rgb, k

if not want("contours"): sys.exit(0)
# ---- contours: analytic, anti-aliased, from a lightly smoothed surface
Zl = ndi.gaussian_filter(Hl, 1.6); Zs = ndi.gaussian_filter(np.where(land, 0, H), 1.6); del H, Hl
Z = Zl
gy, gx = np.gradient(Z); g = np.maximum(np.hypot(gx, gy), 1e-3); del gx, gy
alpha = np.zeros(Z.shape, np.float32); col = np.zeros(Z.shape + (3,), np.uint8)
def lines(levels, width, a, colour, where):
    global alpha
    for L in levels:
        d = np.abs(Z - L) / g
        la = np.clip(width / 2 + 0.5 - d, 0, 1) * a
        la[~where] = 0
        m = la > alpha
        alpha[m] = la[m]; col[m] = colour
land_in = ndi.binary_erosion(land, iterations=3); sea_in = ~ndi.binary_dilation(land, iterations=3)
lines([200] + list(range(500, 8500, 500)), 1.3, 0.42, (74, 58, 46), land_in)
lines(range(1000, 9000, 1000), 2.0, 0.62, (64, 48, 38), land_in)
Z = Zs; gy, gx = np.gradient(Z); g = np.maximum(np.hypot(gx, gy), 1e-3); del gx, gy
lines([-200, -1000, -2000, -3000, -4000, -5000, -6000, -8000], 1.3, 0.34, (150, 172, 208), sea_in)
out = np.dstack([col, np.clip(alpha * 255, 0, 255).astype(np.uint8)])
write_png(os.path.join(LAYERS, "contours.png"), out, zlevel=1)
print("wrote contours.png", round(time.time() - t0), "s")
