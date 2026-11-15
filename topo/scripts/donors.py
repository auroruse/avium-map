"""Avium cities that stand where their stat donor stands on the overlay are anchors: a map pixel with a known real place.
Some donors only lend statistics, so a city counts only if its donor is in the country the overlay shows under it
and near where the current warp already puts that pixel.  -> work/avium_anchors.npy rows: region, x6000, y6000, lon, lat, 0"""
import sys, csv, json, pickle, unicodedata; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
import shapefile
from scipy import ndimage as ndi
_reg = np.load(os.path.join(WORK, "region.npy")); _w = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
_d, (_iy, _ix) = ndi.distance_transform_edt(~np.isin(_reg, list(_w)), return_indices=True)
own = np.where(_d <= 24, _reg[_iy, _ix], 0)          # each pixel's region, reaching a little past the overlay's own coast
reg2u = np.load(os.path.join(WORK, "reg2u.npy")); real = np.load(os.path.join(WORK, "real_unit.npy"), mmap_mode="r")
warps = _w
norm = lambda s: "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if c.isalnum())
r = shapefile.Reader(os.path.join(DATA, "ne_places", "ne_10m_populated_places"), encoding="utf-8")
f = [x[0] for x in r.fields[1:]]; g = {k: f.index(k) for k in ("NAME", "NAMEASCII", "NAMEALT", "LATITUDE", "LONGITUDE")}
gaz = {}
for rec in r.records():
    for nm in [rec[g["NAME"]], rec[g["NAMEASCII"]]] + (rec[g["NAMEALT"]] or "").split("|"):
        if nm and nm.strip(): gaz.setdefault(norm(nm), []).append((rec[g["LONGITUDE"]], rec[g["LATITUDE"]]))
pos = {(c["NAME"], c["NATION"]): (float(c["X"]), float(c["Y"])) for c in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if c["KIND"] == "city" and c["X"]}
def km(lo1, la1, lo2, la2):
    a = np.radians([lo1, la1]); b = np.radians([lo2, la2])
    return 2 * 6371 * np.arcsin(np.sqrt(np.sin((b[1] - a[1]) / 2) ** 2 + np.cos(a[1]) * np.cos(b[1]) * np.sin((b[0] - a[0]) / 2) ** 2))
rows = []; n = nogeo = offmap = wrongc = far = 0; dist = []
for c in csv.DictReader(open(os.path.join(MAP, "src", "data", "cities.tsv"), encoding="utf-8"), delimiter="\t"):
    key = (c["CITY"], c["NATION"]); donor = (c.get("STAT DONOR") or "").strip()
    if key not in pos or not donor or donor == "-": continue
    n += 1; X, Y = pos[key]
    cands = gaz.get(norm(donor)) or gaz.get(norm(donor.split(",")[0]))
    if not cands: nogeo += 1; continue
    b = int(own[int(np.clip(Y / 2, 0, 2999)), int(np.clip(X / 2, 0, 2999))])
    if b <= 0 or b not in warps: offmap += 1; continue
    lo, la = warps[b](np.array([X]), np.array([Y]))
    d = [km(lo[0], la[0], cl, ca) for cl, ca in cands]; k = int(np.argmin(d)); cl, ca = cands[k]
    ru = int(real[int(np.clip((90 - ca) * 60, 0, 10799)), int(np.clip((cl + 180) * 60, 0, 21599))])
    if ru != 0 and ru != int(reg2u[b]): wrongc += 1; continue
    if d[k] > 200: far += 1; continue
    rows.append((b, X, Y, cl, ca, 0)); dist.append(d[k])
np.save(os.path.join(WORK, "avium_anchors.npy"), np.array(rows))
dist = np.array(dist)
print(f"cities with a donor: {n} | donor not in the gazetteer: {nogeo} | off the overlay: {offmap} | donor in another country: {wrongc} | donor over 200 km away: {far}")
print(f"cities standing on their donor: {len(rows)} in {len({r[0] for r in rows})} regions | current offset km: median {np.median(dist):.0f}, p75 {np.percentile(dist, 75):.0f}, p90 {np.percentile(dist, 90):.0f}")
