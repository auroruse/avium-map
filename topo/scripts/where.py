"""Where is the overlay land that does not land in its own real country? By kind, by depth from the region edge, by region."""
import sys, json, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
region = np.load(os.path.join(WORK, "region.npy")); reg2u = np.load(os.path.join(WORK, "reg2u.npy"))
real = np.load(os.path.join(WORK, "real_unit.npy")); warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
codes = json.load(open(os.path.join(WORK, "ne_meta.json")))["codes"]
objs = ndi.find_objects(np.clip(region, 0, None))
tot = 0; rows = []; depth_bins = np.zeros((2, 4)); 
for b, W in warps.items():
    sl = objs[b - 1]; pad = (slice(max(sl[0].start - 1, 0), sl[0].stop + 1), slice(max(sl[1].start - 1, 0), sl[1].stop + 1))
    m = region[pad] == b
    d = ndi.distance_transform_edt(m)
    yy, xx = np.nonzero(m); lon, lat = W(2 * (xx + pad[1].start) + 1.0, 2 * (yy + pad[0].start) + 1.0)
    ru = real[np.clip(((90 - lat) * 60).astype(int), 0, 10799), np.clip(((lon + 180) * 60).astype(int), 0, 21599)]
    wat = ru == 0; oth = (ru != reg2u[b]) & ~wat; dd = d[yy, xx]
    for k, mm in enumerate((wat, oth)):
        depth_bins[k] += [(mm & (dd <= 2)).sum(), (mm & (dd > 2) & (dd <= 5)).sum(), (mm & (dd > 5) & (dd <= 12)).sum(), (mm & (dd > 12)).sum()]
    tot += len(ru); rows.append((int(wat.sum() + oth.sum()), b, len(ru), int(wat.sum()), int(oth.sum()), int(((wat | oth) & (dd > 5)).sum())))
bad = depth_bins.sum()
print(f"fitted overlay land: {tot} px; not in own country: {100*bad/tot:.2f}% (real water {100*depth_bins[0].sum()/tot:.2f}%, another country {100*depth_bins[1].sum()/tot:.2f}%)")
print("by depth from the region's own edge (overlay px at 3000; 1 px is about 7 km):")
for name, k in (("<=2 px", 0), ("3-5 px", 1), ("6-12 px", 2), (">12 px", 3)):
    print(f"  {name:8s} {100*depth_bins[:, k].sum()/tot:5.2f}% of land  (water {100*depth_bins[0, k]/tot:.2f}, other country {100*depth_bins[1, k]/tot:.2f})")
rows.sort(reverse=True)
print("regions holding the most of it (share of all missed px; of which deeper than 5 px; share of that region missed):")
for n, b, sz, w, o, deep in rows[:22]:
    print(f"  {codes[reg2u[b]-1]} #{b}: {100*n/bad:4.1f}% of the miss | deep {100*deep/bad:4.1f}% | {100*n/sz:3.0f}% of the region (water {w}, other {o})")
print("top 22 regions hold %.0f%% of the miss; regions with <10%% of themselves missed hold %.0f%%" % (100 * sum(r[0] for r in rows[:22]) / bad, 100 * sum(r[0] for r in rows if r[0] < 0.1 * r[2]) / bad))
