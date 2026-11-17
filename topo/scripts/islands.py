"""Islands with no Earth under them on the overlay get the ground of a real island.

Most of Avium's ocean islands sit on open sea on the overlay, so they sampled nothing and stood at terrain.py's flat
placeholder (or at whatever the repair could mirror in from the nearest coast, which is near sea level). Each one is
given a real island's ground instead (user, 16 Nov 2026: "match islands to irl ones based on the ones that have
cities on them"):

- an island with a city takes the island its city's stat donor stands on (Ranpua is Hilo, so it is Hawaii);
- an island without one, within NEAR px of an island that has, takes whichever island of that donor's archipelago
  (real islands within REACH km of the donor) best matches its outline, preferring one not used yet in the group;
- one further out takes the best match among the real islands round the place the overlay puts the nearest Avium
  land (the Shantar Islands for the islands off Rudania's Okhotsk coast).

Each real island is laid on its Avium outline by the turn, mirror, scale and shift that make the two outlines agree
best, at real heights. Avium land the real island does not cover takes the nearest real ground, falling away.
ETOPO 2022 60s surface, so ice caps (Svalbard) are their surface. Polar ground is polar.py's and is left alone.

An island the overlay does put on Earth, but on Earth's open sea, is the same case and was missed: it counted as
having ground under it, stood dead flat at sea level and took the colour of "water painted over from the nearest
land", which off Vietnam is one hazy pixel of Phu Quy spread over a hundred km (the Gonenite Islands' grey ones; user,
17 Nov 2026: "Possible texture glitches?"). With `real` given (where the ground under the overlay is real land), an
island less than half on real land is treated like the others. They are placed after the rest, so no island that had
a real island before is given a different one.
"""
import os, sys, csv
import numpy as np
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, MAP, WORK

SURFACE = os.path.join(DATA, "etopo", "ETOPO_2022_v1_60s_N90W180_surface.tif")
NEAR = 450          # px (12000 grid) from an island with a city, within which an island counts as its archipelago
REACH = 1200.0      # km from the donor that the archipelago's real islands may lie
FAR_REACH = 900.0   # km round the overlay's real place for islands with no city near
MAX_REAL = 120000.0 # km2: anything bigger is a continent

# Each stat donor's real position (lat, lon), for the donors of cities on islands with nothing under them
DONORS = {
    "Barentsburg": (78.064, 14.233), "Longyearbyen": (78.223, 15.647),
    "Sri Vijaya Puram": (11.623, 92.726), "Hilo": (19.705, -155.086), "Kimbe": (-5.551, 150.138),
    "Noumea": (-22.276, 166.458), "Yuzhno-Kurilsk": (44.031, 145.861), "Campbell Bay": (7.010, 93.940),
    "Naha-Okinawa City": (26.212, 127.679), "Port Stanley": (-51.693, -57.857), "Victoria, SC": (-4.620, 55.452),
    "Suva": (-18.141, 178.442), "Kahului": (20.889, -156.474), "Honiara": (-9.433, 159.950),
    "Honolulu": (21.307, -157.858), "Saint-Denis, RE": (-20.882, 55.450), "Port Louis, MU": (-20.161, 57.501),
    "Port Vila": (-17.734, 168.322), "Hagåtña": (13.476, 144.749), "Nuku'alofa": (-21.139, -175.204),
    "Ishigaki": (24.340, 124.156), "Male": (4.175, 73.509), "Miyakojima": (24.805, 125.281),
}

KM_LAT = 110.57

def _gc(a, b):
    """great-circle km between (lat, lon) pairs"""
    la1, lo1, la2, lo2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2))

def _window(lat, lon, rkm):
    """Real surface round (lat, lon), rkm each way, on the 60s grid; columns wrap at the date line.
    -> heights, row of lat 0 offset, col offset (unwrapped), so row = (90 - lat) * 60 - r0, col = (lon + 180) * 60 - c0"""
    import rasterio
    dlat = rkm / KM_LAT; dlon = rkm / (111.32 * max(np.cos(np.radians(min(abs(lat) + dlat, 89.0))), 0.05))
    r0 = int(max((90 - lat - dlat) * 60, 0)); r1 = int(min((90 - lat + dlat) * 60, 10800))
    c0 = int(np.floor((lon - dlon + 180) * 60)); c1 = int(np.ceil((lon + dlon + 180) * 60))
    if c1 - c0 >= 21600: c0, c1 = 0, 21600
    cols = np.arange(c0, c1) % 21600
    with rasterio.open(SURFACE) as ds:
        lo, hi = cols.min(), cols.max()
        if np.all(np.diff(cols) == 1): a = ds.read(1, window=((r0, r1), (lo, hi + 1)))
        else:
            full = ds.read(1, window=((r0, r1), (0, 21600))); a = full[:, cols]
    a = np.where(a < -20000, -4000, a).astype(np.float32)
    return a, r0, c0

def _real_islands(a, r0, c0, lat0):
    """Land components in the window that do not touch its edge, with their area in km2"""
    lab, n = ndi.label(a > 0.0)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    rows = np.arange(a.shape[0]) + r0; cell = (KM_LAT / 60) * (111.32 / 60) * np.cos(np.radians(90 - (rows + 0.5) / 60))
    area = ndi.sum(np.broadcast_to(cell[:, None], a.shape), lab, np.arange(1, n + 1))
    return lab, [(i, float(area[i - 1])) for i in range(1, n + 1) if i not in edge and 1.0 <= area[i - 1] <= MAX_REAL]

class Real:
    """One real island on a local km frame: q = (east km, south km) from its centroid"""
    def __init__(self, a, lab, sl, i, r0, c0):
        # its own patch of the window, with room round it for the fit to slide
        p = 8; sl = (slice(max(sl[0].start - p, 0), sl[0].stop + p), slice(max(sl[1].start - p, 0), sl[1].stop + p))
        m = lab[sl] == i; ys, xs = np.nonzero(m)
        self.lat0 = 90 - (ys.mean() + sl[0].start + r0 + 0.5) / 60; self.cos = np.cos(np.radians(self.lat0))
        self.cy, self.cx = ys.mean(), xs.mean()
        self.mask = m
        # only this island's ground: other land in the patch is sea to it, so a neighbour cannot be sampled into it
        self.h = np.where(m, a[sl], np.minimum(a[sl], -50.0)); self.area = None
        self.lat_lon = (self.lat0, (xs.mean() + sl[1].start + c0 + 0.5) / 60 - 180)
        self.win = (sl[0].start + r0, sl[1].start + c0)                           # the patch's row, col on the 60s grid
        self.ident = (round(self.lat_lon[0], 2), round((self.lat_lon[1] + 180) % 360 - 180, 2))   # the same island from any window
    def idx(self, qx, qy):
        return self.cy + qy / (KM_LAT / 60), self.cx + qx / (111.32 * self.cos / 60)

def _coords(P, s, th, mir, d):
    """Avium km offsets P (2, n: east, south) -> real km under scale s, turn th, mirror, shift d"""
    x, y = P
    if mir: x = -x
    c, si = np.cos(th), np.sin(th)
    return s * (c * x - si * y) + d[0], s * (si * x + c * y) + d[1]

def _iou(R, P, t, s, th, mir, d):
    qx, qy = _coords(P, s, th, mir, d); iy, ix = R.idx(qx, qy)
    r = ndi.map_coordinates(R.mask.astype(np.float32), [iy, ix], order=1, cval=0.0) > 0.5
    return (r & t).sum() / max((r | t).sum(), 1)

def _fit(R, P, t, area_t):
    s0 = np.sqrt(R.area / area_t); best = (-1, None)
    for mir in (False, True):
        for s in s0 * np.array([0.85, 1.0, 1.18]):
            for th in np.radians(np.arange(0, 360, 10)):
                v = _iou(R, P, t, s, th, mir, (0.0, 0.0))
                if v > best[0]: best = (v, (s, th, mir, (0.0, 0.0)))
    v, fit = best
    for step in (1.0, 0.5):                                                       # then turn, scale and shift finer
        s, th, mir, d = fit
        for ds in (0.94, 0.97, 1.0, 1.03, 1.06):
            for dth in np.radians(np.arange(-5, 5.1, 2.5) * step):
                for dx in np.array([-1, 0, 1]) * 4.0 * step * s:
                    for dy in np.array([-1, 0, 1]) * 4.0 * step * s:
                        cand = (s * ds, th + dth, mir, (d[0] + dx, d[1] + dy))
                        w = _iou(R, P, t, *cand)
                        if w > v: v, fit = w, cand
    return v, fit

def _place(R, P, fit, KM):
    s, th, mir, d = fit
    qx, qy = _coords(P, s, th, mir, d); iy, ix = R.idx(qx, qy)
    step = s * KM / (KM_LAT / 60)                                                  # real cells per Avium px
    # magnified, the 60s cells would show as facets; shrunk, the real grain would alias into noise
    sig = 0.5 * step if step > 1 else max(0.45 / s - 0.3, 0.0)
    hs = ndi.gaussian_filter(R.h, sig) if sig > 0 else R.h
    z = ndi.map_coordinates(hs, [iy, ix], order=3, cval=-1000.0)
    # a real island shrunk onto a smaller Avium one keeps its summits but not all of their height, or every slope
    # would be as many times steeper as the island is smaller
    if s > 1: z = np.where(z > 0, z * s ** -0.4, z)
    return z, ndi.map_coordinates(R.mask.astype(np.float32), [iy, ix], order=1, cval=0.0)

def _cities(lab, targets):
    donor = {r["CITY"]: r["STAT DONOR"] for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "cities.tsv")), delimiter="\t")}
    out = {}
    for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv")), delimiter="\t"):
        if r["KIND"] != "city": continue
        x, y = int(float(r["X"])) * 2, int(float(r["Y"])) * 2
        win = lab[max(y - 6, 0):y + 7, max(x - 6, 0):x + 7]; v = win[win > 0]
        l = lab[y, x] or (int(np.bincount(v).argmax()) if v.size else 0)
        if l in targets and donor.get(r["NAME"]) in DONORS: out.setdefault(int(l), []).append(donor[r["NAME"]])
    return out

def build(h, land, has0, polar, KM, log=print, places=None, real=None):
    """h: land heights (12000 grid) to overwrite on the islands; has0: real elevation under the overlay, before any
    repair; polar: polar.py's ground. -> h, the mask of what was changed, and a report line per island.
    places: a list to receive (slice, mask, row, col) per island: where on the real 60s grid each of its px lies, so
    colour.py can take the same island's imagery"""
    lab, n = ndi.label(land); sz = np.bincount(lab.ravel())
    hs = np.bincount(lab.ravel(), weights=has0.ravel(), minlength=n + 1); ps = np.bincount(lab.ravel(), weights=polar.ravel(), minlength=n + 1)
    targets = [l for l in range(1, n + 1) if sz[l] < 2_000_000 and hs[l] / sz[l] < 0.5 and ps[l] / sz[l] < 0.2]
    extra = []
    if real is not None:
        rl_ = np.bincount(lab.ravel(), weights=real.ravel(), minlength=n + 1)
        extra = [l for l in range(1, n + 1) if sz[l] < 2_000_000 and hs[l] / sz[l] >= 0.5 and rl_[l] / sz[l] < 0.5 and ps[l] / sz[l] < 0.2]
    objs = ndi.find_objects(lab); cit = _cities(lab, set(targets)); cit_all = {**cit, **_cities(lab, set(extra))} if extra else cit
    cm = dict(zip(targets + extra, ndi.center_of_mass(land, lab, targets + extra)))
    flat = np.load(os.path.join(WORK, "fwd_lat.npy")); flon = np.load(os.path.join(WORK, "fwd_lon.npy"))
    ok = np.isfinite(flat); _, (fy, fx) = ndi.distance_transform_edt(~ok, return_indices=True); f = flat.shape[0] / land.shape[0]
    # which real place each island looks to: its city's donor, its archipelago's donor, or the overlay's nearest land
    plan = {}
    for l in targets + extra:
        cit = cit if l in targets else cit_all                  # the islands there were before look only to each other
        if l in cit: plan[l] = ("city", cit[l][0], DONORS[cit[l][0]]); continue
        d, k = min((float(np.hypot(*np.subtract(cm[l], cm[c]))), c) for c in cit) if cit else (1e9, None)
        if d <= NEAR: plan[l] = ("group", cit[k][0], DONORS[cit[k][0]])
        else:
            y, x = int(cm[l][0] * f), int(cm[l][1] * f); y, x = fy[y, x], fx[y, x]
            plan[l] = ("far", "overlay", (float(flat[y, x]), float(flon[y, x])))
    del fy, fx
    changed = np.zeros(land.shape, bool); used = {}; cache = {}; report = []
    def realset(key, centre, rkm):
        if key not in cache:
            a, r0, c0 = _window(centre[0], centre[1], rkm); rl, isl = _real_islands(a, r0, c0, centre[0])
            Rs = []; objs = ndi.find_objects(rl)
            for i, ar in isl:
                R = Real(a, rl, objs[i - 1], i, r0, c0); R.area = ar; R.key = (key, i); Rs.append(R)
            del a, rl
            cache[key] = Rs
        return cache[key]
    # cities first, so each archipelago knows which of its islands are taken
    order = lambda ls: sorted(ls, key=lambda l: (plan[l][0] != "city", -sz[l]))
    for l in order(targets) + order(extra):
        kind, who, centre = plan[l]; sl = objs[l - 1]
        pad = int(0.3 * max(sl[0].stop - sl[0].start, sl[1].stop - sl[1].start)) + 4
        sl = (slice(max(sl[0].start - pad, 0), min(sl[0].stop + pad, land.shape[0])), slice(max(sl[1].start - pad, 0), min(sl[1].stop + pad, land.shape[1])))
        t = lab[sl] == l; yy, xx = np.mgrid[sl]; c = cm[l]
        P = np.stack([(xx - c[1]).ravel() * KM, (yy - c[0]).ravel() * KM]); tt = t.ravel(); area_t = t.sum() * KM * KM
        Rs = realset(who if kind != "far" else "far%d" % l, centre, REACH if kind != "far" else FAR_REACH)
        if kind == "city":
            # the island the donor stands on, or the nearest one to it within 15 cells (about 25 km)
            ry, rx = (90 - centre[0]) * 60, (centre[1] + 180) * 60
            def gap(R):
                ys, xs = np.nonzero(R.mask); dx = (xs + R.win[1] - rx + 10800) % 21600 - 10800
                return float(np.min(np.hypot(ys + R.win[0] - ry, dx)))
            g = sorted((gap(R), j) for j, R in enumerate(Rs))
            cands = [Rs[g[0][1]]] if g and g[0][0] <= 15 else []
        else:
            # the archipelago's islands near enough in size, nearest the donor first among equals; each real island
            # is used once where the group allows, so one group is not the same island again and again
            reach = REACH if kind != "far" else FAR_REACH
            cands = [R for R in Rs if 0.2 <= R.area / area_t <= 6.0 and _gc(centre, R.lat_lon) <= reach]
            cands = sorted(cands, key=lambda R: abs(np.log(R.area / area_t)))[:10]
        best = None
        for R in cands:
            v, fit = _fit(R, P, tt, area_t)
            score = v if kind == "city" else v - 0.25 * used.get(R.ident, 0) - 0.1 * _gc(centre, R.lat_lon) / reach
            if best is None or score > best[0]: best = (score, v, R, fit)
        if best is None:
            report.append((l, int(sz[l]), kind, who, "no real island found: left as it was")); continue
        _, v, R, fit = best; used[R.ident] = used.get(R.ident, 0) + 1
        z, m = _place(R, P, fit, KM); z = z.reshape(t.shape); m = m.reshape(t.shape)
        g = (m > 0.5) & (z > 1.0)
        if not g.any(): g = t & False
        d, (iy, ix) = ndi.distance_transform_edt(~g, return_indices=True)
        z = np.where(g, z, np.maximum(z[iy, ix], 0) * np.exp(-d * KM / 12.0))
        z = np.maximum(z, 2.0)
        hc = h[sl]; hc[t] = z[t]; changed[sl] |= t
        if places is not None:
            iy, ix = R.idx(*_coords(P, *fit)); places.append((sl, t, (iy + R.win[0]).reshape(t.shape)[t], (ix + R.win[1]).reshape(t.shape)[t]))
        s, th, mir, _ = fit
        report.append((l, int(sz[l]), kind, who, "%.0f km2 real island at %.2f, %.2f; agreement %.2f, scale %.2f, turned %.0f%s, top %.0f m"
                       % (R.area, R.lat_lon[0], R.lat_lon[1], v, 1 / s, np.degrees(th) % 360, ", mirrored" if mir else "", float(z[t].max()))))
    log("  islands with nothing under them given real ground: %d of %d (%d px)" % (sum(1 for r in report if "real island" in r[4]), len(targets) + len(extra), int(changed.sum())))
    return h, changed, report
