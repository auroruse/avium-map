"""spotlook.py out.png x,y[,half] ...  -- contact sheet (3 across) of the finished terrain + rivers round points on the 6000 grid"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
T = rasterio.open(os.path.join(LAYERS, "terrain.png")); Rv = rasterio.open(os.path.join(LAYERS, "rivers.PNG")); S = 440; tiles = []
for a in sys.argv[2:]:
    v = [int(t) for t in a.split(",")]; hw = (v[2] if len(v) > 2 else 60) * 2; x0 = int(np.clip(v[0] * 2 - hw, 0, 12000 - 2 * hw)); y0 = int(np.clip(v[1] * 2 - hw, 0, 12000 - 2 * hw))
    win = rasterio.windows.Window(x0, y0, 2 * hw, 2 * hw); t = np.moveaxis(T.read(window=win), 0, -1)[..., :3].astype(np.float32); r = np.moveaxis(Rv.read(window=win), 0, -1).astype(np.float32)
    al = r[..., 3:4] / 255; img = t * (1 - al) + np.array((25, 35, 120), np.float32) * al; i = np.clip(((np.arange(S) + 0.5) * 2 * hw / S).astype(int), 0, 2 * hw - 1); img = img[i][:, i]
    img[0] = img[-1] = 255; img[:, 0] = img[:, -1] = 255; tiles.append(img)
while len(tiles) % 3: tiles.append(np.zeros((S, S, 3), np.float32))
write_png(os.path.join(WORK, sys.argv[1]), np.clip(np.concatenate([np.concatenate(tiles[i:i + 3], 1) for i in range(0, len(tiles), 3)], 0), 0, 255).astype(np.uint8))
