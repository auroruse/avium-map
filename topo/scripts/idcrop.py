"""idcrop.py x0 y0 w h scale minarea out.png — overlay crop (3000px coords) with blob outlines and ids"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
F = {"0":"111101101101111","1":"010110010010111","2":"111001111100111","3":"111001111001111","4":"101101111001001",
     "5":"111100111001111","6":"111100111101111","7":"111001010010010","8":"111101111101111","9":"111101111001111"}
def draw(img, x, y, text, k, fg=(255, 255, 255), bg=(0, 0, 0)):
    w = (4 * len(text) - 1) * k; h = 5 * k
    x0 = int(x - w / 2); y0 = int(y - h / 2)
    H, W = img.shape[:2]
    if x0 < 2 or y0 < 2 or x0 + w + 2 > W or y0 + h + 2 > H: return
    img[y0 - 2:y0 + h + 2, x0 - 2:x0 + w + 2] = bg
    for i, ch in enumerate(text):
        for j, b in enumerate(F[ch]):
            if b == "1":
                yy = y0 + (j // 3) * k; xx = x0 + (i * 4 + j % 3) * k
                img[yy:yy + k, xx:xx + k] = fg
x0, y0, w, h, s, mina = map(int, sys.argv[1:7]); out = sys.argv[7]
src = np.load(os.path.join(WORK, "pang3000.npy"))[y0:y0+h, x0:x0+w]
lab = np.load(os.path.join(WORK, sys.argv[8] if len(sys.argv) > 8 else "blob.npy"))[y0:y0+h, x0:x0+w]
img = src.repeat(s, 0).repeat(s, 1).copy(); L = lab.repeat(s, 0).repeat(s, 1)
e = np.zeros(L.shape, bool); e[1:] |= L[1:] != L[:-1]; e[:, 1:] |= L[:, 1:] != L[:, :-1]
img[e] = (255, 0, 255)
from scipy import ndimage as ndi
ids, cnt = np.unique(lab, return_counts=True)
ids = ids[(cnt >= mina) & (ids > 0)]
pad = np.pad(lab, 1)
same = (pad[1:-1, 1:-1] == pad[:-2, 1:-1]) & (pad[1:-1, 1:-1] == pad[2:, 1:-1]) & (pad[1:-1, 1:-1] == pad[1:-1, :-2]) & (pad[1:-1, 1:-1] == pad[1:-1, 2:])
d = ndi.distance_transform_edt(same)
for i, (y, x) in zip(ids, ndi.maximum_position(d, lab, ids)):
    draw(img, (x + .5) * s, (y + .5) * s, str(i), 2)
write_png(out, img)
