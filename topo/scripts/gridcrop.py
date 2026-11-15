"""gridcrop.py x0 y0 w h scale out.png [step] — overlay crop (3000px coords) with a labelled coordinate grid and region outlines"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
F = {"0":"111101101101111","1":"010110010010111","2":"111001111100111","3":"111001111001111","4":"101101111001001",
     "5":"111100111001111","6":"111100111101111","7":"111001010010010","8":"111101111101111","9":"111101111001111"}
def draw(img, x0, y0, text, k=2, fg=(255, 255, 0), bg=(0, 0, 0)):
    w = (4 * len(text) - 1) * k; h = 5 * k
    H, W = img.shape[:2]
    if x0 < 0 or y0 < 0 or x0 + w + 2 > W or y0 + h + 2 > H: return
    img[y0:y0 + h + 2, x0:x0 + w + 2] = bg
    for i, ch in enumerate(text):
        for j, b in enumerate(F[ch]):
            if b == "1":
                yy = y0 + 1 + (j // 3) * k; xx = x0 + 1 + (i * 4 + j % 3) * k
                img[yy:yy + k, xx:xx + k] = fg
x0, y0, w, h, s = map(int, sys.argv[1:6]); out = sys.argv[6]; step = int(sys.argv[7]) if len(sys.argv) > 7 else 50
src = np.load(os.path.join(WORK, "pang3000.npy"))[y0:y0+h, x0:x0+w]
img = src.repeat(s, 0).repeat(s, 1).copy()
if os.path.exists(os.path.join(WORK, "region.npy")):
    L = np.load(os.path.join(WORK, "region.npy"))[y0:y0+h, x0:x0+w].repeat(s, 0).repeat(s, 1)
    e = np.zeros(L.shape, bool); e[1:] |= L[1:] != L[:-1]; e[:, 1:] |= L[:, 1:] != L[:, :-1]
    img[e] = (255, 0, 255)
for gx in range((x0 // step + 1) * step, x0 + w, step):
    c = (gx - x0) * s; img[:, c] = (img[:, c] * 0.5 + 60).astype(np.uint8); draw(img, c + 2, 2, str(gx))
for gy in range((y0 // step + 1) * step, y0 + h, step):
    r = (gy - y0) * s; img[r, :] = (img[r, :] * 0.5 + 60).astype(np.uint8); draw(img, 2, r + 2, str(gy))
write_png(out, img)
