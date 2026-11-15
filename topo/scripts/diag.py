"""diag.py blob [blob...] -> work/diag_<blob>.png : real unit boundary (grey/blue) + mapped overlay samples (red coast, green typed)"""
import sys, json, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
b2u = np.load(os.path.join(WORK, "reg2u.npy"))
ov = np.load(os.path.join(WORK, "ov_samples.npy")); rs = np.load(os.path.join(WORK, "real_samples.npy"))
warps = pickle.load(open(os.path.join(WORK, sys.argv[1]), "rb"))
S = 900
for b in map(int, sys.argv[2:]):
    W = warps[b]; u = int(b2u[b])
    r = rs[rs[:, 0] == u]; s = ov[ov[:, 0] == b]
    RE, RN = aeqd_fwd(r[:, 2], r[:, 3], W.lon0, W.lat0)
    E, N = W.plane(s[:, 1], s[:, 2])
    lo = np.percentile(np.concatenate([E, RE]), [1, 99]); la = np.percentile(np.concatenate([N, RN]), [1, 99])
    c = np.array([lo.mean(), la.mean()]); h = max(np.ptp(lo), np.ptp(la)) * 0.6
    img = np.full((S, S, 3), 255, np.uint8)
    def put(e, n, col, k=0):
        x = ((e - c[0]) / h * 0.5 + 0.5) * S; y = (0.5 - (n - c[1]) / h * 0.5) * S
        m = (x >= 1) & (x < S - 2) & (y >= 1) & (y < S - 2); x = x[m].astype(int); y = y[m].astype(int)
        for dx in range(-k, k + 1):
            for dy in range(-k, k + 1): img[y + dy, x + dx] = col
    put(RE[r[:, 1] == 0], RN[r[:, 1] == 0], (170, 190, 230)); put(RE[r[:, 1] != 0], RN[r[:, 1] != 0], (120, 120, 120))
    put(E[s[:, 3].astype(int) == 0], N[s[:, 3].astype(int) == 0], (230, 40, 40), 1); put(E[s[:, 3].astype(int) != 0], N[s[:, 3].astype(int) != 0], (0, 150, 0), 1)
    write_png(os.path.join(WORK, f"diag_{b}.png"), img)
    print(b, "scale", round(W.scale(), 2), "half-width km", round(h))
