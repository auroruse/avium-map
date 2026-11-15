"""Mode-tile thumbnails for the two ground maps, cut from the finished drawings around Shinkeisei."""
import sys, csv; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
rows = [r for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if r["NAME"] == "Shinkeisei"]
cx, cy = float(rows[0]["X"]) * 2, float(rows[0]["Y"]) * 2
W, H, K = 264, 165, 6
x0 = int(cx - W * K / 2); y0 = int(cy - H * K / 2)
for name in ("relief", "terrain"):
    a = read_png(os.path.join(LAYERS, name + ".png"))[y0:y0 + H * K, x0:x0 + W * K, :3].astype(np.float32)
    t = a.reshape(H, K, W, K, 3).mean(axis=(1, 3))
    write_png(os.path.join(MAP, "src", "assets", "map-modes", name + ".png"), t.astype(np.uint8))
    print("thumb", name, t.shape)
