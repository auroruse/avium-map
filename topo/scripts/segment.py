import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
from scipy.cluster.vq import kmeans2
s = np.load(os.path.join(WORK, "pang3000.npy")).astype(np.float32)
med = np.stack([ndi.median_filter(s[..., i], size=7) for i in range(3)], -1)
r, g, b = med[..., 0], med[..., 1], med[..., 2]
sea = (b > r + 55) & (g > r + 45) & (r < 110)
print("sea frac", sea.mean())
land = ~sea
px = med[land]
rng = np.random.default_rng(1)
sub = px[rng.choice(len(px), 200000, replace=False)]
K = 26
cent, _ = kmeans2(sub, K, minit="++", seed=3, iter=40)
d = ((px[:, None, :] - cent[None]) ** 2).sum(-1)
cls = np.zeros(sea.shape, np.int16)
cls[land] = d.argmin(1) + 1
# mode filter 5x5 via per-class box counts
best = np.zeros(cls.shape, np.float32); out = np.zeros_like(cls)
for k in range(0, K + 1):
    cnt = ndi.uniform_filter((cls == k).astype(np.float32), 5)
    m = cnt > best; best[m] = cnt[m]; out[m] = k
cls = out
for k in range(K):
    print(k + 1, cent[k].round().astype(int), int((cls == k + 1).sum()))
# connected components per class
lab = np.zeros(cls.shape, np.int32); n = 0
for k in range(1, K + 1):
    l, m = ndi.label(cls == k)
    l[l > 0] += n; lab += l; n += m
areas = np.bincount(lab.ravel())
print("blobs", n, "| >=200px:", int((areas[1:] >= 200).sum()), "| >=30px:", int((areas[1:] >= 30).sum()))
np.save(os.path.join(WORK, "cls.npy"), cls); np.save(os.path.join(WORK, "lab.npy"), lab)
np.save(os.path.join(WORK, "cent.npy"), cent)
# preview: class centroid colours + black blob edges
img = np.zeros(cls.shape + (3,), np.uint8); img[:] = (40, 60, 90)
img[cls > 0] = cent[cls[cls > 0] - 1].clip(0, 255).astype(np.uint8)
e = (lab != np.roll(lab, 1, 0)) | (lab != np.roll(lab, 1, 1))
img[e] = 0
write_png(os.path.join(WORK, "seg.png"), img)
write_png(os.path.join(WORK, "seg_small.png"), img[::2, ::2])
