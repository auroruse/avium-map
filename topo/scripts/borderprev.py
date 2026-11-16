"""Before and after pictures of the borders against the rivers, drawn as the app draws them with Relief off: flat land and
sea, the nation fills, the rivers over them, city dots.
  borderprev.py AFTER OUTDIR [name:x0,y0,x1,y1 ...]
AFTER is a borders PNG or a label array from riverborders.py; the boxes are in 6000 px coordinates. With no boxes, the ten
places the user sent on 15 Nov 2026 as examples of borders that sat beside their rivers. Left half before, right half after;
the city dots before are read from work/coordinates_before.tsv when it is there."""
import sys, os, csv; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
SITES = {"01_lapsikan": (3705, 820, 4075, 975), "02_camphanh": (4110, 868, 4370, 1062), "03_jinyang": (3295, 722, 3540, 900),
         "04_kurogawa": (2548, 886, 2878, 1014), "05_permskoye": (2280, 884, 2392, 966), "06_wilna": (2980, 2330, 3148, 2438),
         "07_veynach": (3106, 2553, 3210, 2652), "08_caldrin": (1652, 2812, 1798, 3230), "09_sanpablo": (1514, 4233, 1610, 4284),
         "10_canot": (2478, 3822, 2852, 4172)}
before = read_png(os.path.join(WORK, "borders_before_rivers.PNG"))
def load(path):
    if path.endswith(".npy"):
        lab = np.load(path); out = before.copy(); m = lab >= 0
        out[m, 0] = (lab[m] >> 16) & 255; out[m, 1] = (lab[m] >> 8) & 255; out[m, 2] = lab[m] & 255; out[m, 3] = 255; out[lab == -1] = 0
        return out
    return read_png(path)
land = np.load(os.path.join(WORK, "land12k.npy"), mmap_mode="r"); riv = read_png(os.path.join(WORK, "rivers12000.png"))[..., 3]
cities = [(int(float(r["X"])), int(float(r["Y"]))) for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if r["KIND"] == "city" and r["X"]]
def panel(bd, box, k, pts=cities):
    x0, y0, x1, y1 = box; f = np.s_[2 * y0:2 * y1, 2 * x0:2 * x1]
    img = np.where(np.asarray(land[f])[..., None], np.array((180, 179, 191), np.float32), np.array((62, 78, 111), np.float32))
    c = bd[y0:y1, x0:x1].repeat(2, 0).repeat(2, 1).astype(np.float32); a = c[..., 3:] / 255; img = img * (1 - a) + c[..., :3] * a
    a = riv[f].astype(np.float32)[..., None] / 255; img = img * (1 - a) + np.array((56, 72, 104), np.float32) * a
    img = img.astype(np.uint8)
    for x, y in pts:
        if x0 + 2 <= x < x1 - 2 and y0 + 2 <= y < y1 - 2:
            cy, cx = 2 * (y - y0), 2 * (x - x0); yy, xx = np.mgrid[cy - 3:cy + 4, cx - 3:cx + 4]; d = np.hypot(yy - cy, xx - cx)
            img[yy[d <= 3.2], xx[d <= 3.2]] = (20, 20, 24); img[yy[d <= 2.1], xx[d <= 2.1]] = (255, 255, 255)
    return img.repeat(k, 0).repeat(k, 1)
def tsv(path): return [(int(float(r["X"])), int(float(r["Y"]))) for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t") if r["KIND"] == "city" and r["X"]]
old_ = os.path.join(WORK, "coordinates_before.tsv"); cities0 = tsv(old_) if os.path.exists(old_) else cities      # the dots before citybanks.py
def sheet(after, box, path):
    w = box[2] - box[0]; k = 1 if w > 195 else 2 if w > 130 else 3 if w > 97 else 4
    A = panel(before, box, k, cities0); B = panel(after, box, k, cities); gap = np.full((A.shape[0], 8, 3), 255, np.uint8)
    write_png(path, np.concatenate([A, gap, B], 1))
if __name__ == "__main__":
    after = load(sys.argv[1]); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    boxes = {a.split(":")[0]: tuple(int(v) for v in a.split(":")[1].split(",")) for a in sys.argv[3:]} or SITES
    for name, box in boxes.items(): sheet(after, box, os.path.join(out, "borders_%s.png" % name))
    print("wrote", len(boxes), "pictures to", out)
