import sys, json, pickle, copy; sys.path.insert(0, __import__("os").path.dirname(__file__))
import numpy as np
import fit as F
from scipy import ndimage as ndi
warps = pickle.load(open(F.os.path.join(F.WORK, "warps.pkl"), "rb"))
objs = ndi.find_objects(np.clip(F.blob, 0, None))
for b in map(int, sys.argv[1:]):
    B = F.Blob(b); W = copy.copy(warps[b]); W.tps = None
    sl = objs[b - 1]; r0, c0 = max(sl[0].start - 12, 0), max(sl[1].start - 12, 0)
    m = ndi.binary_dilation(F.blob[r0:sl[0].stop + 12, c0:sl[1].stop + 12] == b, iterations=4)
    yy, xx = np.nonzero(m); k = np.random.default_rng(1).choice(len(yy), min(len(yy), 6000), replace=False)
    gx = 2.0 * (xx[k] + c0) + 1; gy = 2.0 * (yy[k] + r0) + 1
    ext = W.scale() * 2 * np.sqrt(F.AREA[b]); cap = max(35.0, 0.3 * ext)
    B.match_junctions(W, 500)
    print("region", b, "ext km", round(ext), "cap", round(cap), "landmarks", len(B.L))
    for lam, d in F.SCHED:
        B.icp(W, "tps", 3, min(d, cap), min(d, cap), lam=lam)
        h = 3.0
        E1, N1 = W.plane(gx + h, gy); E0, N0 = W.plane(gx - h, gy); E3, N3 = W.plane(gx, gy + h); E2, N2 = W.plane(gx, gy - h)
        a = (E1 - E0) / (2 * h); c = (N1 - N0) / (2 * h); bb = (E3 - E2) / (2 * h); dd = (N3 - N2) / (2 * h)
        det = a * dd - bb * c; rr = det / (-np.linalg.det(W.A[:, :2]))
        fro = a * a + bb * bb + c * c + dd * dd
        s2 = np.sqrt(np.maximum((fro - np.sqrt(np.maximum(fro * fro - 4 * det * det, 0))) / 2, 0)); s1 = np.sqrt((fro + np.sqrt(np.maximum(fro * fro - 4 * det * det, 0))) / 2)
        sv = np.linalg.svd(W.A[:, :2], compute_uv=False); an = (s2 / np.maximum(s1, 1e-9)) / (sv[1] / sv[0])
        w = np.argmin(rr)
        print(f"  lam {lam:5} | area ratio min {rr.min():.2f} p2 {np.percentile(rr,2):.2f} p98 {np.percentile(rr,98):.2f} | aniso p2 {np.percentile(an,2):.2f} | worst at 3000px ({gx[w]/2:.0f},{gy[w]/2:.0f}) | ok {F.jac_ok(W, gx, gy)}")
