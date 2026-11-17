"""Where on Earth every Avium pixel's ground comes from, and how the overlay stretches it there.
-> work/place.npz: lat, lon (float32, a 3000x3000 grid: every 4th px of the 12000 one; NaN where the overlay has nothing),
   stretch (the longer over the shorter axis a real km takes up on the map), scale (real km per map px, geometric mean)
The elevation and the imagery are cross-faded where two regions meet; a place cannot be, so each pixel takes the region
that weighs most there. Carried through relax.py's shift and nudge.py's, as they are."""
import sys, pickle, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
from scipy import ndimage as ndi
OUT, K, D, STEP, F = 12000, 4, 6, 16, 4
if __name__ == "__main__":
    t0 = time.time()
    warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb")); own = np.load(os.path.join(WORK, "own.npy")); RX = Relax(WORK)
    n = OUT // F; best = np.zeros((n, n), np.float32); V = np.full((n, n, 3), np.nan, np.float32); objs = ndi.find_objects(own)
    for b, W in warps.items():
        sl = objs[b - 1]
        if sl is None: continue
        r0, r1 = max(sl[0].start - D - 1, 0), min(sl[0].stop + D + 1, 3000); c0, c1 = max(sl[1].start - D - 1, 0), min(sl[1].stop + D + 1, 3000)
        m = own[r0:r1, c0:c1] == b; wt = np.clip(1 - ndi.distance_transform_edt(~m) / D, 0, 1).astype(np.float32)     # own.npy is on the 3000 grid: so is this
        if wt.max() <= 0: continue
        h, w = (r1 - r0) * K, (c1 - c0) * K
        gy = np.arange(0, h + STEP, STEP); gx = np.arange(0, w + STEP, STEP); GX, GY = np.meshgrid(gx, gy)
        x6 = (c0 * K + GX + 0.5) / 2; y6 = (r0 * K + GY + 0.5) / 2
        lon, lat = W(x6, y6); lon, lat = Relax.apply(RX.region(b), lon, lat, x6, y6)
        lo = np.radians(lon); la = np.radians(lat); U = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
        py, px = np.meshgrid((np.arange(r1 - r0) * K + K / 2) / STEP, (np.arange(c1 - c0) * K + K / 2) / STEP, indexing="ij")
        v = np.stack([ndi.map_coordinates(U[k], [py, px], order=1, mode="nearest") for k in range(3)], -1)
        sub = (slice(r0, r1), slice(c0, c1)); take = wt > best[sub]
        V[sub][take] = v[take]; best[sub][take] = wt[take]
    # nudge.py's shift: the ground at a pixel is the ground that stood 2f further back
    Fd = np.load(os.path.join(WORK, "nudge_field.npy")); yy, xx = np.meshgrid(np.arange(n, dtype=np.float32) * F + F / 2, np.arange(n, dtype=np.float32) * F + F / 2, indexing="ij")
    gy = ((yy + 0.5) / 2 - 4) / 8; gx = ((xx + 0.5) / 2 - 4) / 8
    sy = (yy - 2 * ndi.map_coordinates(Fd[..., 1], [gy, gx], order=1, mode="nearest")) / F - 0.5; sx = (xx - 2 * ndi.map_coordinates(Fd[..., 0], [gy, gx], order=1, mode="nearest")) / F - 0.5
    ok = np.isfinite(V[..., 0]); _, (iy, ix) = ndi.distance_transform_edt(~ok, return_indices=True); Vf = V[iy, ix]
    Vn = np.stack([ndi.map_coordinates(Vf[..., k], [sy, sx], order=1, mode="nearest") for k in range(3)], -1)
    okn = ndi.map_coordinates(ok.astype(np.float32), [sy, sx], order=0, mode="nearest") > 0.5
    Vn /= np.maximum(np.linalg.norm(Vn, axis=-1, keepdims=True), 1e-9)
    lat = np.degrees(np.arcsin(np.clip(Vn[..., 2], -1, 1))); lon = np.degrees(np.arctan2(Vn[..., 1], Vn[..., 0]))
    # the stretch: how far apart on Earth neighbours on the map are, along the map's two axes
    R_ = 6371.0; dy = (Vn[2:, 1:-1] - Vn[:-2, 1:-1]) * R_ / (2 * F); dx = (Vn[1:-1, 2:] - Vn[1:-1, :-2]) * R_ / (2 * F)      # km per map px, 3-vectors
    a = (dx * dx).sum(-1); c = (dy * dy).sum(-1); bb = (dx * dy).sum(-1); tr = a + c; det = np.maximum(a * c - bb * bb, 0)
    s1 = np.sqrt(np.maximum(tr / 2 + np.sqrt(np.maximum(tr * tr / 4 - det, 0)), 1e-12)); s2 = np.sqrt(np.maximum(tr / 2 - np.sqrt(np.maximum(tr * tr / 4 - det, 0)), 1e-12))
    stretch = np.ones((n, n), np.float32); scale = np.full((n, n), 1.75, np.float32)
    stretch[1:-1, 1:-1] = np.clip(s1 / s2, 1, 50); scale[1:-1, 1:-1] = np.sqrt(s1 * s2)
    lat[~okn] = np.nan; lon[~okn] = np.nan
    np.savez(os.path.join(WORK, "place.npz"), lat=lat.astype(np.float32), lon=lon.astype(np.float32), stretch=stretch, scale=scale)
    land = np.load(os.path.join(WORK, "land12k.npy"))[F // 2::F, F // 2::F] & okn; s = stretch[land]; k = scale[land]
    print("place: %d s | stretch on land: median %.2f, over 1.5 on %.1f%%, over 2 on %.1f%%, over 3 on %.1f%% | km per px: median %.2f, 5-95%% %.2f-%.2f"
          % (time.time() - t0, np.median(s), 100 * (s > 1.5).mean(), 100 * (s > 2).mean(), 100 * (s > 3).mean(), np.median(k), np.percentile(k, 5), np.percentile(k, 95)))
