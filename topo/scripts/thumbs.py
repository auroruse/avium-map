"""Mode-tile thumbnails for the Map sheet: Satellite (hybrid.png), Political, Terrain and Time Zones, all cut from one box
(6000 grid) so the four tiles show the same place at the same scale, each drawn as the app draws that map with its
default switches: Political is the shaded relief with the borders at 0.75 and the rivers, Terrain the terrain with the
rivers (borders and contour lines start off there), Satellite its own ground with its fine rivers and the borders as
lines, Time Zones the zone layer over the black page. Run after the layers change."""
import sys, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi

W, H = 264, 165                       # the tile's own size
X0, Y0, K = 2150.0, 381.0, 5.45       # the box: the Nichirin coast as the Political tile has shown it since October

def shrink(a, k, x0, y0):
    """Area mean of a k x k footprint per thumbnail px, box corner (x0, y0) in a's own px"""
    a = a.astype(np.float32); out = np.empty((H, W, a.shape[2]), np.float32)
    ys = y0 + (np.arange(H) + 0.5) * k - 0.5; xs = x0 + (np.arange(W) + 0.5) * k - 0.5
    yy, xx = np.meshgrid(ys, xs, indexing="ij")
    r = slice(int(y0) - 2 * int(k), int(y0 + H * k) + 2 * int(k)); c = slice(int(x0) - 2 * int(k), int(x0 + W * k) + 2 * int(k))
    for ch in range(a.shape[2]):
        f = ndi.uniform_filter(a[r, c, ch], int(round(k)))
        out[..., ch] = ndi.map_coordinates(f, [yy - r.start, xx - c.start], order=1)
    return out

def over(under, top, opacity=1.0):
    al = top[..., 3:4].astype(np.float32) / 255 * opacity
    return under.astype(np.float32) * (1 - al) + top[..., :3].astype(np.float32) * al

def crop12(name):
    a = read_png(os.path.join(LAYERS, name)); r = slice(int(2 * Y0) - 40, int(2 * (Y0 + H * K)) + 40)
    c = slice(int(2 * X0) - 40, int(2 * (X0 + W * K)) + 40); return a[r, c], r.start, c.start

rv, ry, rx = crop12("rivers.PNG")
bd = read_png(os.path.join(LAYERS, "borders.PNG")).repeat(2, 0).repeat(2, 1)[ry:ry + rv.shape[0], rx:rx + rv.shape[1]]
for name, ground, borders in (("political", "relief.png", 0.75), ("terrain", "terrain.png", 0.0)):
    g = crop12(ground)[0][..., :3]
    img = over(g, bd, borders) if borders else g.astype(np.float32)
    img = over(img, rv)
    t = shrink(img, 2 * K, 2 * X0 - rx, 2 * Y0 - ry)
    write_png(os.path.join(MAP, "src", "assets", "map-modes", name + ".png"), np.clip(np.round(t), 0, 255).astype(np.uint8))
# Hybrid: the border lines are a hairline on the map (dark plum, BORDER_LINE in main.ts), so here they are drawn a thumbnail
# pixel wide or they average away
rf, gy, gx = crop12("rivers-fine.png")
with rasterio.open(os.path.join(LAYERS, "hybrid.png")) as ds:        # 24000 px: its window, taken down to the 12000 grid
    g = np.moveaxis(ds.read(window=((2 * gy, 2 * (gy + rf.shape[0])), (2 * gx, 2 * (gx + rf.shape[1])))), 0, -1)[..., :3].astype(np.float32)
g = g.reshape(rf.shape[0], 2, rf.shape[1], 2, 3).mean(axis=(1, 3)); img = over(g, rf)
m = np.ones(g.shape[:2], bool)
for l in json.load(open(os.path.join(MAP, "src", "data", "borderlines.json"))):
    p = np.array(l, np.float64).reshape(-1, 2) * 2; s = np.r_[0, np.cumsum(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])))]
    t = np.arange(0, s[-1] + 0.5, 0.5); xs = np.round(np.interp(t, s, p[:, 0]) - gx).astype(int); ys = np.round(np.interp(t, s, p[:, 1]) - gy).astype(int)
    ok = (xs >= 0) & (xs < m.shape[1]) & (ys >= 0) & (ys < m.shape[0]); m[ys[ok], xs[ok]] = False
a = np.clip(K + 0.5 - ndi.distance_transform_edt(m), 0, 1)[..., None] * 0.65
t = shrink(img * (1 - a) + np.array([255, 255, 255], np.float32) * a, 2 * K, 2 * X0 - gx, 2 * Y0 - gy)
write_png(os.path.join(MAP, "src", "assets", "map-modes", "hybrid.png"), np.clip(np.round(t), 0, 255).astype(np.uint8))
z = read_png(os.path.join(LAYERS, "zones.png"))
t = shrink(over(np.zeros(z.shape[:2] + (3,), np.uint8), z), K, X0, Y0)
write_png(os.path.join(MAP, "src", "assets", "map-modes", "zones.png"), np.clip(np.round(t), 0, 255).astype(np.uint8))
print("thumbs: political, terrain, hybrid, zones at %dx%d from x %d-%d, y %d-%d (6000 grid)" % (W, H, X0, X0 + W * K, Y0, Y0 + H * K))
