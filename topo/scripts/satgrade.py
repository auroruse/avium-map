"""Between the satellite layer (colour.py) and the Hybrid map's land: stray water painted out, and the grade."""
import numpy as np
from scipy import ndimage as ndi
GAMMA, GAIN, SAT = 0.80, 1.04, 1.08      # the imagery is dark for ground that has to carry a hillshade and names: lifted, a little richer

def grade(c):
    """c: float array (..., 3) 0-255 -> the same, graded"""
    v = np.clip(c / 255.0, 0, 1) ** GAMMA * GAIN; l = (v @ np.array([0.30, 0.59, 0.11], np.float32))[..., None]
    return np.clip(l + (v - l) * SAT, 0, 1) * 255.0

def stray_water(col, land, leave):
    """Lakes and ponds the imagery has and Avium does not show as smudges of teal on the ground. Bluer than red and not bright (how
    much bluer it has to be falls as it gets darker), or darker than any forest with no red in it at all: nothing
    that grows or lies bare is that colour. They take the ground nearest them.
    -> how many px"""
    c = col.astype(np.int16); lum = (c[..., 0] * 30 + c[..., 1] * 59 + c[..., 2] * 11) // 100
    br = c[..., 2] - c[..., 0]
    wet = (((br > 6) & (c[..., 2] > c[..., 1] - 12) | (br > 12)) & (lum < 110) | (br >= 3) & (lum < 60) | (c[..., 0] < 16) & (lum < 30)) & land; del c, lum, br
    wet = ndi.binary_dilation(wet & ~leave, iterations=3) & land & ~leave        # and the dark rim round each; `leave` (the polar continents) is not looked at
    _, (iy, ix) = ndi.distance_transform_edt(wet | ~land, return_indices=True); ys, xs = np.nonzero(wet)
    col[ys, xs] = col[iy[ys, xs], ix[ys, xs]]; del iy, ix
    r0, r1, q0, q1 = max(ys.min() - 4, 0), ys.max() + 5, max(xs.min() - 4, 0), xs.max() + 5; m = wet[r0:r1, q0:q1]; w = land[r0:r1, q0:q1].astype(np.float32)
    for k in range(3):                                           # the fill, softened where it was laid
        cc = col[r0:r1, q0:q1, k]; sm = ndi.gaussian_filter(cc * w, 1.5) / np.maximum(ndi.gaussian_filter(w, 1.5), 1e-3); cc[m] = np.round(sm[m])
    return len(ys)
