"""preview.py [x0 y0 w h] [out] [scale] — hillshaded, tinted look at height.npy (coords on the 12000 grid)"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
H = np.load(os.path.join(WORK, "height.npy"), mmap_mode="r")
a = sys.argv[1:]
if len(a) >= 4:
    x0, y0, w, h = map(int, a[:4]); out = a[4] if len(a) > 4 else "prev.png"; step = int(a[5]) if len(a) > 5 else 1
else:
    x0, y0, w, h = 0, 0, 12000, 12000; out = a[0] if a else "prev.png"; step = 8
z = np.asarray(H[y0:y0 + h, x0:x0 + w]).astype(np.float32)
if step > 1: z = z.reshape(h // step, step, w // step, step).mean(axis=(1, 3))
cell = 1750.0 * step
gy, gx = np.gradient(z * 5.0, cell)
az, alt = np.radians(315), np.radians(45)
slope = np.arctan(np.hypot(gx, gy)); aspect = np.arctan2(-gx, gy)
shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
shade = np.clip(shade, 0, 1)
stops_l = [(0, (112, 153, 110)), (200, (150, 180, 122)), (500, (205, 205, 140)), (1000, (214, 180, 120)), (2000, (176, 132, 96)), (3500, (150, 120, 110)), (5000, (235, 235, 235)), (9000, (255, 255, 255))]
stops_s = [(-11000, (10, 20, 60)), (-5000, (18, 38, 92)), (-3000, (30, 62, 122)), (-1000, (58, 102, 160)), (-200, (104, 150, 196)), (0, (150, 190, 220))]
def ramp(v, stops):
    xs = [s[0] for s in stops]
    return np.stack([np.interp(v, xs, [s[1][k] for s in stops]) for k in range(3)], -1)
col = np.where((z > 0)[..., None], ramp(z, stops_l), ramp(z, stops_s))
img = np.clip(col * (0.45 + 0.75 * shade[..., None]), 0, 255).astype(np.uint8)
write_png(os.path.join(WORK, out), img)
print(out, img.shape)
