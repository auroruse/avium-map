"""Put the rivers layer in place as layers/rivers.PNG. The hand-drawn export is kept beside it as rivers-drawn.PNG.
With no real rivers traced (riverlayer.py GENERATED = False) the hand-drawn file goes back untouched."""
import sys, shutil, pickle; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
cur = os.path.join(LAYERS, "rivers.PNG"); keep = os.path.join(LAYERS, "rivers-drawn.PNG")
if not os.path.exists(keep): shutil.copy2(cur, keep); print("kept the hand-drawn layer as", os.path.basename(keep))
added = len(pickle.load(open(os.path.join(WORK, "rivers_final.pkl"), "rb")))
shutil.copyfile(os.path.join(WORK, "rivers12000.png") if added else keep, cur)
print("wrote layers/rivers.PNG:", "%d traced rivers, plus the drawn ones in Eivorie" % added if added else "the hand-drawn rivers, untouched")
