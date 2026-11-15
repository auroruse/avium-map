import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
import shapefile, collections
a = read_png(os.path.join(LAYERS, "rivers.PNG"))
al = a[..., 3]; m = al > 0
print("rivers.PNG", a.shape, "opaque px", int((al == 255).sum()), "semi", int(((al > 0) & (al < 255)).sum()))
c = a[al > 200][:, :3]; u, n = np.unique(c // 8 * 8, axis=0, return_counts=True); o = np.argsort(-n)[:5]
print("colours:", [(tuple(int(v) for v in u[i]), int(n[i])) for i in o])
from scipy import ndimage as ndi
d = ndi.distance_transform_edt(m); print("line half-width px: median of ridge", float(np.median(d[d >= 1])), "max", float(d.max()))
write_png(os.path.join(WORK, "riv_old.png"), a[3300:3900, 2000:2600, :3] * (a[3300:3900, 2000:2600, 3:] > 0) + (255 - 255 * (a[3300:3900, 2000:2600, 3:] > 0)).astype(np.uint8))
r = shapefile.Reader(os.path.join(DATA, "ne_rivers", "ne_10m_rivers_lake_centerlines"), encoding="utf-8")
f = [x[0] for x in r.fields[1:]]; print(f)
recs = r.records()
print(collections.Counter(x[f.index("featurecla")] for x in recs))
print("scalerank", sorted(collections.Counter(x[f.index("scalerank")] for x in recs).items()))
print("strokeweig", sorted(collections.Counter(round(x[f.index("strokeweig")], 2) for x in recs).items())[:12])
print([x[f.index("name")] for x in recs if x[f.index("scalerank")] <= 2][:40])
