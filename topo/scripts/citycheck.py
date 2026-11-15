import sys, pickle, csv; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
old = read_png(os.path.join(LAYERS, "rivers.PNG"))[..., 3] > 0
do = ndi.distance_transform_edt(~old)
rows = [r for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if r["KIND"] == "city" and r["X"]]
xy = np.array([[float(r["X"]), float(r["Y"])] for r in rows])
d = do[np.clip(xy[:, 1].round().astype(int), 0, 5999), np.clip(xy[:, 0].round().astype(int), 0, 5999)]
print("cities", len(rows), "| px to nearest hand-drawn river: <=2:", int((d <= 2).sum()), "<=4:", int((d <= 4).sum()), "<=6:", int((d <= 6).sum()), "<=10:", int((d <= 10).sum()))
print("Eivorie cities on a river (<=4):", sum(1 for r, dd in zip(rows, d) if r["NATION"] == "Eivorie" and dd <= 4))
lines = pickle.load(open(os.path.join(WORK, "river_lines.pkl"), "rb"))
newm = np.ones((6000, 6000), bool)
for rank, name, p in lines:
    k = int(max(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])).sum() * 2, 2)); t = np.linspace(0, len(p) - 1, k)
    newm[np.clip(np.round(np.interp(t, np.arange(len(p)), p[:, 1])).astype(int), 0, 5999), np.clip(np.round(np.interp(t, np.arange(len(p)), p[:, 0])).astype(int), 0, 5999)] = False
dn = ndi.distance_transform_edt(newm)
on = d <= 4
dd = dn[np.clip(xy[on, 1].round().astype(int), 0, 5999), np.clip(xy[on, 0].round().astype(int), 0, 5999)]
print("river cities -> nearest NEW river px: median %.1f | <=3: %d | <=8: %d | <=15: %d | <=25: %d | >25: %d" % (np.median(dd), (dd <= 3).sum(), (dd <= 8).sum(), (dd <= 15).sum(), (dd <= 25).sum(), (dd > 25).sum()))
