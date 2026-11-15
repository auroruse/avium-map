"""ETOPO 2022 30s bedrock -> 60s grid (block mean), real lakes filled to their shore level. work/dem60.npy (int16, 10800x21600)"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
import shapefile
from rasterio import features
from rasterio.transform import from_origin
from scipy import ndimage as ndi
H, W = 10800, 21600
out = np.zeros((H, W), np.float32)
with rasterio.open(os.path.join(DATA, "etopo", "ETOPO_2022_v1_30s_N90W180_bed.tif")) as ds:
    for r0 in range(0, 21600, 2160):
        a = ds.read(1, window=((r0, r0 + 2160), (0, 43200))).astype(np.float32)
        a[a < -20000] = 0
        out[r0 // 2:r0 // 2 + 1080] = a.reshape(1080, 2, W, 2).mean(axis=(1, 3))
print("dem60 min/max", out.min(), out.max())
tf = from_origin(-180, 90, 360 / W, 180 / H)
rl = shapefile.Reader(os.path.join(DATA, "ne_lakes", "ne_10m_lakes"), encoding="utf-8")
shapes = [(sr.shape.__geo_interface__, i + 1) for i, sr in enumerate(rl.iterShapeRecords())]
lk = features.rasterize(shapes, out_shape=(H, W), transform=tf, fill=0, dtype="int32")
objs = ndi.find_objects(lk); n = 0
for i, sl in enumerate(objs, 1):
    if sl is None: continue
    sl = (slice(max(sl[0].start - 2, 0), min(sl[0].stop + 2, H)), slice(max(sl[1].start - 2, 0), min(sl[1].stop + 2, W)))
    m = lk[sl] == i
    ring = ndi.binary_dilation(m, iterations=1) & (lk[sl] == 0)
    if ring.sum() < 3: continue
    level = float(np.median(out[sl][ring]))
    sub = out[sl]; sub[m] = level; n += 1
print("lakes levelled", n)
np.save(os.path.join(WORK, "dem60.npy"), np.round(out).astype(np.int16))
