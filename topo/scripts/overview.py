"""Four quadrant overviews of the finished terrain + rivers, for a whole-map look."""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
T = rasterio.open(os.path.join(LAYERS, "terrain.png")); Rv = rasterio.open(os.path.join(LAYERS, "rivers.PNG"))
for name, x0, y0 in (("nw", 1800, 600), ("ne", 6000, 600), ("sw", 1800, 5400), ("se", 5400, 5400)):
    win = rasterio.windows.Window(x0, y0, 4800, 4800)
    t = np.moveaxis(T.read(window=win), 0, -1)[..., :3].astype(np.float32); r = np.moveaxis(Rv.read(window=win), 0, -1).astype(np.float32)
    al = r[..., 3:4] / 255; img = t * (1 - al) + r[..., :3] * al
    write_png(os.path.join(WORK, f"ov_{name}.png"), img.reshape(1200, 4, 1200, 4, 3).mean(axis=(1, 3)).astype(np.uint8))
