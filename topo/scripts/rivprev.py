"""rivprev.py x0 y0 w h out [step] — terrain preview (12000 grid) + new rivers (cyan) + old drawn rivers (red)"""
import sys, pickle, subprocess; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
x0, y0, w, h = map(int, sys.argv[1:5]); out = sys.argv[5]; step = int(sys.argv[6]) if len(sys.argv) > 6 else 2
subprocess.run([sys.executable, "-I", os.path.join(TOPO, "scripts", "preview.py"), str(x0), str(y0), str(w), str(h), "_tmp.png", str(step)], check=True, capture_output=True)
img = read_png(os.path.join(WORK, "_tmp.png")).copy()
old = read_png(os.path.join(LAYERS, "rivers-drawn.PNG" if os.path.exists(os.path.join(LAYERS, "rivers-drawn.PNG")) else "rivers.PNG"))[..., 3] > 0
yy, xx = np.nonzero(old[y0 // 2:(y0 + h) // 2, x0 // 2:(x0 + w) // 2])
X = (xx * 2) // step; Y = (yy * 2) // step; m = (X < img.shape[1]) & (Y < img.shape[0]); img[Y[m], X[m]] = (230, 40, 40)
if "--old-only" not in sys.argv:
    for rank, name, xy in pickle.load(open(os.path.join(WORK, "rivers_final.pkl"), "rb")):
        p = xy * 2
        d = np.maximum(np.abs(np.diff(p[:, 0])), np.abs(np.diff(p[:, 1]))).max() if len(p) > 1 else 0
        k = max(int(np.ceil(d / step * 2)), 1)
        t = np.linspace(0, len(p) - 1, (len(p) - 1) * k + 1)
        px = np.interp(t, np.arange(len(p)), p[:, 0]); py = np.interp(t, np.arange(len(p)), p[:, 1])
        X = ((px - x0) / step).astype(int); Y = ((py - y0) / step).astype(int)
        m = (X >= 0) & (Y >= 0) & (X < img.shape[1]) & (Y < img.shape[0]); img[Y[m], X[m]] = (0, 235, 255) if rank <= 6 else (120, 225, 255)
write_png(os.path.join(WORK, out), img)
