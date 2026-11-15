"""Rasterise Natural Earth countries (+ big lakes as water) to a 1-arcmin label grid."""
import sys, json; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
import shapefile
from rasterio import features
from rasterio.transform import from_origin
W, H = 21600, 10800
tf = from_origin(-180, 90, 360 / W, 180 / H)
r = shapefile.Reader(os.path.join(DATA, "ne_countries", "ne_10m_admin_0_countries"), encoding="utf-8")
f = [x[0] for x in r.fields[1:]]
ia = f.index("ADM0_A3"); iname = f.index("NAME")
codes = sorted({rec[ia] for rec in r.records()})
idx = {c: i + 1 for i, c in enumerate(codes)}
names = {}
shapes = []
for sr in r.iterShapeRecords():
    c = sr.record[ia]; names[c] = sr.record[iname]
    shapes.append((sr.shape.__geo_interface__, idx[c]))
lab = features.rasterize(shapes, out_shape=(H, W), transform=tf, fill=0, dtype="int16")
rl = shapefile.Reader(os.path.join(DATA, "ne_lakes", "ne_10m_lakes"), encoding="utf-8")
fl = [x[0] for x in rl.fields[1:]]; isr = fl.index("scalerank")
lakes = [(sr.shape.__geo_interface__, 1) for sr in rl.iterShapeRecords() if sr.record[isr] <= 2]
lk = features.rasterize(lakes, out_shape=(H, W), transform=tf, fill=0, dtype="uint8")
print("lakes used:", len(lakes), "lake px:", int(lk.sum()))
lab[lk > 0] = 0
np.save(os.path.join(WORK, "real_lab.npy"), lab)
lat = 90 - (np.arange(H) + 0.5) * 180 / H
cell = (6371.0 ** 2) * np.radians(360 / W) * np.radians(180 / H) * np.cos(np.radians(lat))
area = np.zeros(len(codes) + 1)
for y in range(H):
    area += np.bincount(lab[y], minlength=len(codes) + 1) * cell[y]
json.dump({"codes": codes, "names": names, "area_km2": {c: float(area[idx[c]]) for c in codes}},
          open(os.path.join(WORK, "ne_meta.json"), "w"))
print(len(codes), "countries; RUS", round(area[idx["RUS"]]), "km2; land total", round(area[1:].sum()))
