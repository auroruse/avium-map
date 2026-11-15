"""Carry every region's warp exactly through its named cities. No refit: a rigid or affine correction for the
region as a whole, then a local Gaussian correction for what is left at each city."""
import sys, pickle, shutil; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from geo import *
src = os.path.join(WORK, "warps_fit.pkl")              # the fit's own output, kept so this step can be rerun
if not os.path.exists(src) or os.path.getmtime(src) < os.path.getmtime(os.path.join(WORK, "fit_report.json")):
    shutil.copyfile(os.path.join(WORK, "warps.pkl"), src)
region = np.load(os.path.join(WORK, "region.npy")); AREA = np.bincount(region[region > 0]) * 4.0   # px on the 6000 grid
MISPLACED = 120.0     # km: cities this far off together mean the region itself is in the wrong place
warps = pickle.load(open(src, "rb")); lm = np.load(os.path.join(WORK, "landmarks.npy"))
av = os.path.join(WORK, "avium_anchors.npy")            # Avium cities standing on their stat donor (donors.py): many, a little loose
if os.path.exists(av): lm = np.concatenate([lm, np.load(av)])
def resid(W, a):
    E, N = W.plane(a[:, 0], a[:, 1]); TE, TN = aeqd_fwd(a[:, 2], a[:, 3], W.lon0, W.lat0)
    return np.stack([E, N], 1), np.stack([TE, TN], 1)
before = []; after = []; ex_all = []; kinds = {"shift": 0, "similarity": 0, "affine": 0, "local": 0}
for b in np.unique(lm[:, 0]).astype(int):
    if b not in warps: continue
    W = warps[b]; sel = lm[:, 0] == b; a = lm[sel][:, 1:5]; k = len(a); exact = lm[sel][:, 5] > 0
    cur, tgt = resid(W, a); d = np.hypot(*(cur - tgt).T); before += d.tolist()
    if d.max() > 5.0:
        if np.median(d) > MISPLACED:
            # the region as a whole is off: move it
            if k == 1:
                W.post = np.array([[1, 0, tgt[0, 0] - cur[0, 0]], [0, 1, tgt[0, 1] - cur[0, 1]]], float); kinds["shift"] += 1
            else:
                post = fit_similarity(cur[:, 0], cur[:, 1], tgt[:, 0], tgt[:, 1], np.ones(k)); kind = "similarity"
                if k >= 4:
                    A = fit_affine(cur[:, 0], cur[:, 1], tgt[:, 0], tgt[:, 1], np.ones(k)); sv = np.linalg.svd(A[:, :2], compute_uv=False)
                    if np.linalg.det(A[:, :2]) > 0 and sv[1] / sv[0] > 0.5 and 0.6 < np.sqrt(sv[0] * sv[1]) < 1.6: post = A; kind = "affine"
                if kind == "similarity" and not (0.6 < np.hypot(post[0, 0], post[1, 0]) < 1.6):
                    post = np.array([[1, 0, (tgt - cur)[:, 0].mean()], [0, 1, (tgt - cur)[:, 1].mean()]], float); kind = "shift"
                W.post = post; kinds[kind] += 1
            cur, tgt = resid(W, a)
        r = tgt - cur
        if np.hypot(*r.T).max() > 2.0:
            # otherwise the borders stay where the neighbours agreed and only the ground around each city bends:
            # a Gaussian correction centred on the cities, fading before it reaches the edge of the region
            u, v = a[:, 0], -a[:, 1]; size = np.sqrt(AREA[b])
            if k == 1: sg = float(np.clip(0.35 * size, 25, 150)); Phi = np.ones((1, 1))
            else:
                dd = np.hypot(u[:, None] - u[None], v[:, None] - v[None]); np.fill_diagonal(dd, np.inf)
                sg = float(np.clip(3.0 * np.median(dd.min(1)), 60, max(60, min(300, 0.5 * size))))
                Phi = np.exp(-np.where(np.isinf(dd), 0, dd) ** 2 / (2 * sg * sg))
            # a printed city dot is held exactly; an Avium city was placed by hand, so it is followed on average
            wt = np.linalg.solve(Phi + np.diag(np.where(exact, 0.02, 2.5)), r)
            W.rbf = (np.stack([u, v], 1), wt, sg); kinds["local"] += 1
    cur, tgt = resid(W, a); dd_ = np.hypot(*(cur - tgt).T); after += dd_.tolist(); ex_all += exact.tolist()
pickle.dump(warps, open(os.path.join(WORK, "warps.pkl"), "wb"))
b_, a_ = np.array(before), np.array(after)
print("regions corrected:", kinds)
ex = np.array(ex_all)
print("printed city dots, km off: before median %.1f -> after median %.2f, max %.1f" % (np.median(b_[ex]), np.median(a_[ex]), a_[ex].max()))
print("Avium cities on their donor, km off: before median %.0f, p90 %.0f -> after median %.0f, p90 %.0f" % (np.median(b_[~ex]), np.percentile(b_[~ex], 90), np.median(a_[~ex]), np.percentile(a_[~ex], 90)))
print("all anchors, km off before: median %.1f, over 25 km: %d, over 100 km: %d | after: median %.2f, max %.1f, over 5 km: %d" % (np.median(b_), (b_ > 25).sum(), (b_ > 100).sum(), np.median(a_), a_.max(), (a_ > 5).sum()))
