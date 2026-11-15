"""seaprev.py out.png [x0,y0,x1,y1 on the 6000 grid]  -- quick look at the heights: sea floor tinted and shaded, land grey"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
H = np.load(os.path.join(WORK, sys.argv[3] if len(sys.argv) > 3 else "height_raw.npy"), mmap_mode="r")
if len(sys.argv) > 2 and sys.argv[2] != "-": x0, y0, x1, y1 = [int(v) * 2 for v in sys.argv[2].split(",")]; Z = np.asarray(H[y0:y1, x0:x1], np.float32); cell = 1750.0
else: Z = np.asarray(H[::8, ::8], np.float32); cell = 1750.0 * 8
gy, gx = np.gradient(Z, cell); zf = 14.0 if cell > 2000 else 5.0; gx *= zf; gy *= zf; nz = 1 / np.sqrt(gx * gx + gy * gy + 1)
sh = np.clip((gx * 0.5 + gy * 0.5 + 0.67) * nz, 0, 1) / 0.67
stops = [(-9000, (20, 24, 60)), (-6000, (30, 44, 96)), (-4500, (46, 74, 130)), (-3000, (74, 116, 168)), (-1500, (120, 164, 200)), (-200, (176, 208, 226)), (0, (205, 228, 238))]
xs = [s[0] for s in stops]; rgb = np.stack([np.interp(Z, xs, [s[1][c] for s in stops]) for c in range(3)], -1) * np.clip(sh, 0.55, 1.35)[..., None]
rgb[Z > 0] = (np.array((150, 148, 140)) * np.clip(sh[Z > 0], 0.6, 1.3)[:, None])
write_png(os.path.join(WORK, sys.argv[1]), np.clip(rgb, 0, 255).astype(np.uint8))
print("depth percentiles (sea):", np.percentile(Z[Z < 0], [1, 10, 50, 90, 99]).astype(int))
