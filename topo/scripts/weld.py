"""Weld neighbouring warps along the borders they share: where two regions name slightly different real places for the
same border pixel, both are bent to meet in the middle, fading out a short way inside each. Needs seams.npy (seams.py)."""
import sys, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
warps = pickle.load(open(os.path.join(WORK, "warps.pkl"), "rb")); S = np.load(os.path.join(WORK, "seams.npy"))
rng = np.random.default_rng(5); SG = 44.0; n = 0
S = S[S[:, 8] < 200]                                  # a bigger gap is a misplaced region, not a seam
def xyz(lo, la):
    lo = np.radians(lo); la = np.radians(la); return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], 1)
m = xyz(S[:, 4], S[:, 5]) + xyz(S[:, 6], S[:, 7]); m /= np.linalg.norm(m, axis=1)[:, None]
mlon = np.degrees(np.arctan2(m[:, 1], m[:, 0])); mlat = np.degrees(np.arcsin(m[:, 2]))
for b, W in warps.items():
    sel = np.nonzero((S[:, 0] == b) | (S[:, 1] == b))[0]
    if len(sel) < 8: continue
    if len(sel) > 350: sel = rng.choice(sel, 350, replace=False)
    x, y = S[sel, 2], S[sel, 3]
    E, N = W.plane(x, y); TE, TN = aeqd_fwd(mlon[sel], mlat[sel], W.lon0, W.lat0)
    r = np.stack([TE - E, TN - N], 1)
    u, v = x, -y
    Phi = np.exp(-((u[:, None] - u[None]) ** 2 + (v[:, None] - v[None]) ** 2) / (2 * SG * SG))
    wt = np.linalg.solve(Phi + 0.6 * np.eye(len(sel)), r)
    W.rbfs = list(getattr(W, "rbfs", [])) + [(np.stack([u, v], 1), wt, SG)]; n += 1
pickle.dump(warps, open(os.path.join(WORK, "warps.pkl"), "wb"))
print("regions welded:", n)
