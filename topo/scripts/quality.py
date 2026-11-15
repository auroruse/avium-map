"""Map-wide defect audit: stretch, repaired ground, lake shores, river breaks. By Avium nation where it helps."""
import sys, csv, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
flon = np.load(os.path.join(WORK, "fwd_lon.npy")); flat = np.load(os.path.join(WORK, "fwd_lat.npy")); own = np.load(os.path.join(WORK, "own.npy"))
lo = np.radians(flon); la = np.radians(flat)
V = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1) * 6371.0
Jx = (V[:, 2:] - V[:, :-2])[1:-1] / 2; Jy = (V[2:] - V[:-2])[:, 1:-1] / 2
ok = (own[1:-1, 2:] == own[1:-1, :-2]) & (own[2:, 1:-1] == own[:-2, 1:-1]) & (own[1:-1, 1:-1] > 0)
a = (Jx * Jx).sum(-1); b = (Jx * Jy).sum(-1); c = (Jy * Jy).sum(-1)
tr = a + c; dt = np.maximum(a * c - b * b, 0); disc = np.sqrt(np.maximum(tr * tr / 4 - dt, 0))
s1 = np.sqrt(tr / 2 + disc); s2 = np.sqrt(np.maximum(tr / 2 - disc, 1e-9))
an = np.full(own.shape, np.nan, np.float32); an[1:-1, 1:-1] = np.where(ok, s1 / s2, np.nan)
sc = np.full(own.shape, np.nan, np.float32); sc[1:-1, 1:-1] = np.where(ok, np.sqrt(s1 * s2) / 2, np.nan)      # km per px on the 6000 grid
mono = read_png(os.path.join(LAYERS, "mono.png"))[:, :, 0] > 0
land3 = mono.reshape(3000, 2, 3000, 2).mean(axis=(1, 3)) > 0.5
E = np.load(os.path.join(WORK, "ereal.npy"), mmap_mode="r"); has = np.load(os.path.join(WORK, "ehas.npy"), mmap_mode="r")
land12 = np.load(os.path.join(WORK, "land12k.npy"))
rep3 = np.zeros((3000, 3000), np.float32); none3 = np.zeros((3000, 3000), np.float32)
for r0 in range(0, 12000, 2000):
    e = np.asarray(E[r0:r0 + 2000]); h = np.asarray(has[r0:r0 + 2000]); l = land12[r0:r0 + 2000]
    rep3[r0 // 4:r0 // 4 + 500] = (l & h & (e < 2)).reshape(500, 4, 3000, 4).mean(axis=(1, 3))
    none3[r0 // 4:r0 // 4 + 500] = (l & ~h).reshape(500, 4, 3000, 4).mean(axis=(1, 3))
m = land3 & np.isfinite(an)
print("STRETCH (how much the sampled terrain is pulled longer one way than the other; 1.0 = none)")
print("  Avium land with real elevation: ratio over 1.5: %.0f%% | over 2: %.0f%% | over 3: %.0f%% | over 5: %.1f%%" % tuple(100 * (an[m] > t).mean() for t in (1.5, 2, 3, 5)))
print("  scale, real km per map px (6000 grid): p5 %.1f | median %.1f | p95 %.1f  (the map's own scale is 2.36)" % tuple(np.percentile(sc[m], [5, 50, 95])))
print("REPAIRED GROUND: land that sampled real sea and was filled by mirroring: %.1f%% of Avium land | land with no Earth counterpart at all: %.1f%%" % (100 * rep3[land3].mean(), 100 * none3[land3].mean()))
# per nation, at the cities
rows = [c for c in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if c["KIND"] == "city" and c["X"]]
rep_near = ndi.maximum_filter(rep3, 5); nat = {}
for c in rows:
    x, y = int(float(c["X"]) / 2), int(float(c["Y"]) / 2)
    if not (0 <= x < 3000 and 0 <= y < 3000): continue
    d = nat.setdefault(c["NATION"], [[], 0, 0, 0]); d[3] += 1
    if np.isfinite(an[y, x]): d[0].append(an[y, x])
    if rep_near[y, x] > 0.3: d[1] += 1
    if none3[y, x] > 0.5 or not np.isfinite(an[y, x]): d[2] += 1
tab = []
for n, (A, rp, nn, tot) in nat.items():
    if tot < 8: continue
    A = np.array(A) if A else np.array([np.nan])
    tab.append(((np.nanmean(A > 2) if len(A) else 0) + rp / tot, n, tot, float(np.nanmedian(A)), 100 * float(np.nanmean(A > 2)), 100 * rp / tot, 100 * nn / tot))
tab.sort(reverse=True)
print("BY NATION (cities | median stretch | cities stretched over 2x | cities on repaired ground | cities with no real elevation)")
for _, n, tot, med, bad, rp, nn in tab[:22]: print(f"  {n:22s} {tot:4d} | {med:4.1f} | {bad:3.0f}% | {rp:3.0f}% | {nn:3.0f}%")
good = [t for t in tab if t[4] < 10 and t[5] < 10 and t[6] < 10]
print(f"  nations with under 10% of cities affected on every count: {len(good)} of {len(tab)}")
# lakes
water6 = ~read_png(os.path.join(LAYERS, "mono.png"))[:, :, 0].astype(bool)
lab, k = ndi.label(water6); sizes = np.bincount(lab.ravel()); ocean = sizes[1:].argmax() + 1
inland = (lab > 0) & (lab != ocean); nl = int((sizes[1:] >= 12).sum()) - 1
ring = ndi.binary_dilation(inland, iterations=3) & ~water6
Hr = np.load(os.path.join(WORK, "height_raw.npy"), mmap_mode="r")
yy, xx = np.nonzero(ring); e_ring = np.asarray(E[np.clip(2 * yy, 0, 11999), np.clip(2 * xx, 0, 11999)])
print("LAKES: %d inland water bodies; all are treated as sea, so their shores are pulled to sea level. Shore ground that is really above 100 m: %.0f%% of lake shore (median real height there %.0f m)" % (nl, 100 * (e_ring > 100).mean(), np.median(e_ring[e_ring > 100]) if (e_ring > 100).any() else 0))
fin = pickle.load(open(os.path.join(WORK, "rivers_final.pkl"), "rb"))
L = np.array([np.hypot(np.diff(p[2][:, 0]), np.diff(p[2][:, 1])).sum() for p in fin])
print("RIVERS: %d separate pieces from 1,471 real rivers | pieces shorter than 40 px: %d | median piece %.0f px" % (len(fin), (L < 40).sum(), np.median(L)))

# zigzag: a river line that doubles back on itself at consecutive vertices is hopping between two placements
zz = tot = 0; worst = []
for rank, name, p in fin:
    d = np.diff(p, axis=0); l = np.hypot(d[:, 0], d[:, 1]); ok_ = (l[:-1] > 1.5) & (l[1:] > 1.5)
    cs = (d[:-1] * d[1:]).sum(1) / np.maximum(l[:-1] * l[1:], 1e-9); k = int((ok_ & (cs < -0.5)).sum()); zz += k; tot += len(cs)
    if k >= 4: worst.append((k, name or "?", int(p[:, 0].mean()), int(p[:, 1].mean())))
worst.sort(reverse=True)
print("RIVER HOPS: segments longer than 8 px in the finished rivers: %d" % sum(int((np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])) > 8).sum()) for _, _, p in fin))
print("RIVER ZIGZAG: %d sharp reversals in %d vertices; pieces with 4 or more: %d %s" % (zz, tot, len(worst), worst[:8]))
