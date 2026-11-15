"""look.py out.png City[:halfwidth] ... — contact sheet of the finished terrain + rivers around named cities (2 columns)"""
import sys, csv; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
rows = {c["NAME"]: c for c in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if c["X"]}
T = rasterio.open(os.path.join(LAYERS, "terrain.png")); Rv = rasterio.open(os.path.join(LAYERS, "rivers.PNG"))
tiles = []
for a in sys.argv[2:]:
    n, hw = (a.split(":") + ["350"])[:2]; hw = int(hw); c = rows[n]; x, y = int(float(c["X"]) * 2), int(float(c["Y"]) * 2)
    x0 = int(np.clip(x - hw, 0, 12000 - 2 * hw)); y0 = int(np.clip(y - hw * 0.7, 0, 12000 - int(1.4 * hw)))
    win = rasterio.windows.Window(x0, y0, 2 * hw, int(1.4 * hw))
    t = np.moveaxis(T.read(window=win), 0, -1)[..., :3].astype(np.float32); r = np.moveaxis(Rv.read(window=win), 0, -1).astype(np.float32)
    al = r[..., 3:4] / 255; img = (t * (1 - al) + r[..., :3] * al)
    cx, cy = x - x0, y - y0; img[max(cy - 4, 0):cy + 5, max(cx - 4, 0):cx + 5] = (255, 60, 60)
    k = 700 / (2 * hw); 
    from scipy import ndimage as ndi
    img = np.stack([ndi.zoom(img[..., ch], k, order=1) for ch in range(3)], -1)[:490, :700]
    pad = np.zeros((490, 700, 3), np.float32); pad[:img.shape[0], :img.shape[1]] = img; tiles.append(pad)
while len(tiles) % 2: tiles.append(np.zeros((490, 700, 3), np.float32))
sheet = np.concatenate([np.concatenate(tiles[i:i + 2], 1) for i in range(0, len(tiles), 2)], 0)
write_png(os.path.join(WORK, sys.argv[1]), np.clip(sheet, 0, 255).astype(np.uint8))
