"""crop.py <layer file> x0 y0 w h scale out.png  — view a piece of a layer"""
import sys, numpy as np
sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
f, x0, y0, w, h, s, out = sys.argv[1], *map(int, sys.argv[2:7]), sys.argv[7]
a = read_png(os.path.join(LAYERS, f))[y0:y0+h, x0:x0+w, :3]
if s > 1: a = a.repeat(s, 0).repeat(s, 1)
write_png(out, a)
