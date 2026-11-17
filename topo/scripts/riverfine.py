"""The Hybrid map's rivers: the same rivers as layers/rivers.PNG at something near their real width.
The rivers layer draws a river 3 to 5 px wide on the 12000 grid, which is 5 to 9 km of water: right for a map that is
read by its lines, and far too heavy over ground that is meant to look like the ground. Here the widest are about
1.5 px (2.6 km) and a headwater 0.6, in the colour of the Hybrid map's shallow water, so they thin out and fade as the
map is zoomed out, as rivers do from above.
Traced rivers are redrawn along their own lines (work/rivers_final.pkl), each as wide as the rivers layer made it, scaled.
Eivorie's are hand-drawn and have no lines, so theirs is the drawn stroke thinned to its middle.
-> layers/rivers-fine.png (12000px). Run after riverlayer.py and install_rivers.py."""
import sys, pickle, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
t0 = time.time(); M = 12000
SCALE, WMIN, WMAX = 0.33, 0.6, 1.5         # full width here per px of full width on the rivers layer, and its limits (px, 12000 grid)
STEP = 0.25                                # px between the samples a line is laid down in
COLOUR = (40, 88, 124)

big = read_png(os.path.join(WORK, "rivers12000.png"))[..., 3] > 127
R = ndi.distance_transform_edt(big).astype(np.float32)                    # at a river's middle: half its drawn width, near enough
cover = np.zeros(M * M, np.float32)
def lay(x, y, w):
    """Area of line per pixel: each sample puts w * STEP px of water down, shared between the four pixels round it"""
    x = x - 0.5; y = y - 0.5; x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64); fx = x - x0; fy = y - y0
    for dy, dx, k in ((0, 0, (1 - fx) * (1 - fy)), (0, 1, fx * (1 - fy)), (1, 0, (1 - fx) * fy), (1, 1, fx * fy)):
        yy = y0 + dy; xx = x0 + dx; ok = (yy >= 0) & (yy < M) & (xx >= 0) & (xx < M)
        cover[:] += np.bincount(yy[ok] * M + xx[ok], weights=(w * k)[ok], minlength=M * M).astype(np.float32)
X, Y, Wd = [], [], []
for rank, name, xy in pickle.load(open(os.path.join(WORK, "rivers_final.pkl"), "rb")):
    p = np.asarray(xy, np.float64) * 2 + 0.5
    if len(p) < 2: continue
    s = np.r_[0, np.cumsum(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])))]; t = np.arange(0, s[-1], STEP)
    x = np.interp(t, s, p[:, 0]); y = np.interp(t, s, p[:, 1])
    r = R[np.clip(y.astype(int), 0, M - 1), np.clip(x.astype(int), 0, M - 1)]
    r = ndi.maximum_filter1d(r, 9, mode="nearest")                        # a sample a pixel off the middle reads thin
    X.append(x); Y.append(y); Wd.append(np.clip(SCALE * 2 * r, WMIN, WMAX))
x = np.concatenate(X); y = np.concatenate(Y); w = np.concatenate(Wd); del X, Y, Wd
lay(x, y, w * STEP); print("traced rivers: %d samples | %.0f s" % (len(x), time.time() - t0), flush=True)

# Eivorie: the drawn stroke thinned to its middle line (Zhang-Suen), on the drawing's own 6000 grid, so each pixel of
# line is a 2 x 2 block here
def thin(m):
    m = m.copy()
    while True:
        gone = False
        for step in (0, 1):
            P = np.pad(m, 1); n = [P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:], P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]]
            B = sum(v.astype(np.uint8) for v in n); A = sum((~n[i] & n[(i + 1) % 8]).astype(np.uint8) for i in range(8))
            c = (~(n[0] & n[2] & n[4]) & ~(n[2] & n[4] & n[6])) if step == 0 else (~(n[0] & n[2] & n[6]) & ~(n[0] & n[4] & n[6]))
            rm = m & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any(): m &= ~rm; gone = True
        if not gone: return m
eiv = np.load(os.path.join(WORK, "eiv.npy")); D = (read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0) & eiv; del eiv
ys, xs = np.nonzero(D); n = 0
if len(ys):
    r = slice(max(ys.min() - 2, 0), ys.max() + 3); c = slice(max(xs.min() - 2, 0), xs.max() + 3)
    Rd = ndi.distance_transform_edt(D[r, c]); yy, xx = np.nonzero(thin(D[r, c])); n = len(yy)
    w = np.clip(SCALE * 4 * Rd[yy, xx], WMIN, WMAX) / 2                    # 4: half a width on the 6000 grid to a whole one on this
    yy = 2 * (yy + r.start); xx = 2 * (xx + c.start)
    for dy in (0, 1):
        for dx in (0, 1): cover += np.bincount((yy + dy) * M + xx + dx, weights=w, minlength=M * M).astype(np.float32)
print("Eivorie: %d px of middle line | %.0f s" % (n, time.time() - t0), flush=True); del D

alpha = np.clip(ndi.gaussian_filter(cover.reshape(M, M), 0.45), 0, 1); del cover
land = np.load(os.path.join(WORK, "land12k.npy"))
alpha *= np.clip((ndi.gaussian_filter(land.astype(np.float32), 0.8) - 0.35) / 0.3, 0, 1)            # a river stops at the shore
out = np.zeros((M, M, 4), np.uint8); out[..., 0], out[..., 1], out[..., 2] = COLOUR; out[..., 3] = np.round(alpha * 255).astype(np.uint8)
write_png(os.path.join(LAYERS, "rivers-fine.png"), out)
print("wrote layers/rivers-fine.png | %.0f s" % (time.time() - t0))
