"""Where every map pixel is in the real world before relaxation: own.npy (its region) and fwd_*_raw.npy (3000 grid)."""
import sys, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
region = np.load(os.path.join(WORK, "region.npy")); warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb"))
dist, (iy, ix) = ndi.distance_transform_edt(~np.isin(region, list(warps)), return_indices=True)
own = np.where(dist <= 24, region[iy, ix], 0).astype(np.int32); np.save(os.path.join(WORK, "own.npy"), own)
flon = np.full(own.shape, np.nan, np.float32); flat = np.full(own.shape, np.nan, np.float32); objs = ndi.find_objects(own)
for b, W in warps.items():
    sl = objs[b - 1]
    if sl is None: continue
    yy, xx = np.nonzero(own[sl] == b); yy += sl[0].start; xx += sl[1].start
    lo, la = W(2 * xx + 1.0, 2 * yy + 1.0); flon[yy, xx] = lo; flat[yy, xx] = la
np.save(os.path.join(WORK, "fwd_lon_raw.npy"), flon); np.save(os.path.join(WORK, "fwd_lat_raw.npy"), flat)
print("forward grid:", int((own > 0).sum()), "px")
