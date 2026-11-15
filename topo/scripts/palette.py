import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
a = read_png(os.path.join(LAYERS, "pangaea.PNG"))[:, :, :3]
# 2x block mean -> 3000
s = a.reshape(3000, 2, 3000, 2, 3).mean(axis=(1, 3))
np.save(os.path.join(WORK, "pang3000.npy"), s.astype(np.uint8))
q = (s // 8).astype(np.int32)
key = q[..., 0] * 1024 + q[..., 1] * 32 + q[..., 2]
u, c = np.unique(key, return_counts=True)
o = np.argsort(-c)
tot = key.size
print("distinct 5-bit colours:", len(u))
cum = 0
for i in o[:60]:
    k = u[i]; r, g, b = k // 1024 * 8 + 4, (k // 32) % 32 * 8 + 4, k % 32 * 8 + 4
    cum += c[i]
    print(f"{r:3d},{g:3d},{b:3d}  {c[i]:8d}  {100*c[i]/tot:5.2f}%  cum {100*cum/tot:5.1f}%")
