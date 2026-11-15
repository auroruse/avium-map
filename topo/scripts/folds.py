"""How much of the fitted land does the final warp fold (map backwards) or crush (area under a tenth of normal)?"""
import sys, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
region = np.load(os.path.join(WORK, "region.npy")); objs = ndi.find_objects(np.clip(region, 0, None))
for name in sys.argv[1:]:
    warps = pickle.load(open(os.path.join(WORK, name), "rb")); tot = fold = crush = 0; worst = []
    for b, W in warps.items():
        sl = objs[b - 1]; yy, xx = np.nonzero(region[sl] == b)
        k = np.arange(0, len(yy), 3); x = 2.0 * (xx[k] + sl[1].start) + 1; y = 2.0 * (yy[k] + sl[0].start) + 1; h = 3.0
        E1, N1 = W.plane(x + h, y); E0, N0 = W.plane(x - h, y); E3, N3 = W.plane(x, y + h); E2, N2 = W.plane(x, y - h)
        det = ((E1 - E0) * (N3 - N2) - (E3 - E2) * (N1 - N0)) / (4 * h * h); r = det / (-np.linalg.det(W.A[:, :2]))
        tot += len(r); fold += (r <= 0).sum(); crush += ((r > 0) & (r < 0.1)).sum(); worst.append(((r < 0.1).mean(), b, len(r)))
    worst.sort(reverse=True)
    print(f"{name}: folded {100*fold/tot:.2f}% | crushed {100*crush/tot:.2f}% of land | worst regions:", ", ".join(f"#{b} {100*f:.0f}%" for f, b, n in worst[:6] if f > 0.02))
