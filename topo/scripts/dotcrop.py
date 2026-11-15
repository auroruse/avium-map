"""dotcrop.py x0 y0 w h scale out.png — overlay crop (3000 grid) with every detected city dot ringed and numbered"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
F = {"0":"111101101101111","1":"010110010010111","2":"111001111100111","3":"111001111001111","4":"101101111001001",
     "5":"111100111001111","6":"111100111101111","7":"111001010010010","8":"111101111101111","9":"111101111001111"}
x0, y0, w, h, s = map(int, sys.argv[1:6]); out = sys.argv[6]
src = np.load(os.path.join(WORK, "pang3000.npy"))[y0:y0+h, x0:x0+w]
img = src.repeat(s, 0).repeat(s, 1).copy(); H, W = img.shape[:2]
dots = np.load(os.path.join(WORK, "dots.npy")); used = np.zeros((H, W), bool); k = 2
for i, (x, y, a) in enumerate(dots):
    if not (x0 + 1 <= x < x0 + w - 1 and y0 + 1 <= y < y0 + h - 1): continue
    cx, cy = int((x - x0 + .5) * s), int((y - y0 + .5) * s); r = int(max(np.sqrt(a) * s * 0.75, 5))
    for t in np.linspace(0, 2 * np.pi, 80):
        px, py = int(cx + r * np.cos(t)), int(cy + r * np.sin(t))
        if 0 <= px < W and 0 <= py < H: img[py, px] = (255, 0, 0)
    text = str(i); tw = (4 * len(text) - 1) * k + 4; th = 5 * k + 4
    for ox, oy in ((r + 3, -th // 2), (-r - 3 - tw, -th // 2), (-tw // 2, -r - 3 - th), (-tw // 2, r + 3), (r + 3, -r - th), (r + 3, r), (-r - 3 - tw, -r - th), (-r - 3 - tw, r)):
        bx, by = cx + ox, cy + oy
        if bx < 0 or by < 0 or bx + tw > W or by + th > H or used[by:by + th, bx:bx + tw].any(): continue
        img[by:by + th, bx:bx + tw] = (0, 0, 0); used[by:by + th, bx:bx + tw] = True
        for n, ch in enumerate(text):
            for j, bit in enumerate(F[ch]):
                if bit == "1":
                    yy = by + 2 + (j // 3) * k; xx = bx + 2 + (n * 4 + j % 3) * k
                    img[yy:yy + k, xx:xx + k] = (255, 255, 0)
        break
write_png(out, img)
