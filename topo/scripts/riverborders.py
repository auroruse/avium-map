"""Put the borders that run alongside a river onto the river (user, 15 Nov 2026: "Every border needs to be aesthetically
pleasing in reference to rivers"; reach 15 px, unclaimed land trades too, a city keeps its country and that stretch stays).

layers/borders.PNG is flat fills, one colour per nation, no drawn line: a border is where two colours meet. The layer as the
user drew it is kept in work/borders_before_rivers.PNG and every run starts from that copy.

How: for each pair of neighbours the line between them is redrawn as the cheapest line that separates them (a minimum cut),
where a line may only run in three places:
  under a river        cheap, and cheapest down the middle of the river's drawn width, so the river hides the border;
  on the old border    as drawn, at cost 1 per px (EVCOST where it was drawn on a hand-drawn river the traced one has left);
  on a short link      between the two, through ground that lies between an old border and a river no more than REACH apart
                       (EVREACH for a stretch drawn on a hand-drawn river), dearer the longer it is.
Anywhere else a line cannot run at all, so a border with no river beside it stays exactly as drawn. Ground changes hands only
within REACH px of a river and CAP px of a drawn border. So a border leaves its drawn line only when the river beside it is
long compared with the links it takes to get on and off, and it gets on and off where the two come closest. Pairs are redone
in turn until nothing moves, which lets the point where three countries meet slide onto the river.

Then every patch that went from one holder to another is checked; one that fails is put back as drawn, frozen, and the
borders round it solved again:
  its new border must be mostly river (river >= RIVER_SHARE x link);
  it may not split a country in two;
  it may not move a city to another country, unless the city stands within 3 px of the river and its own bank is within 8 px
  (citybanks.py then moves the dot onto that bank). Round any other city the border is left as drawn for 12 px either way.
A second pass, with no links at all, lets a border already on a river follow it round a bend out to BEND px, and keeps the
bend only if the border runs on under the river past both its ends.

Tried and dropped: one check per connected patch (a strip won fairly carried a corner cut between two countries); smooth noise
on the link cost (links still ruler-straight); a 0.75 threshold for "under the river" (gaps on thin reaches); reach limits
without the river-distance limit (a river crossing a thin strip of a country handed the whole strip over).

Never touched: the sea, the base map's white coastline stroke (the fills stop at it), soft-edged pixels, stray pieces of
SPECK px or less. Writes work/borders_snapped.PNG (layers/borders.PNG with `install`), work/riverborders.png (what moved),
work/riverborders_labels.npy (for citybanks.py) and work/riverborders_report.txt.
Run after riverlayer.py; then citybanks.py write; then node scripts/coords.mjs and npm run tile in the app folder."""
import sys, os, csv, shutil, time; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from scipy import ndimage as ndi, sparse
from scipy.sparse.csgraph import maximum_flow, breadth_first_order

REACH = 15                 # px (6000 grid) between a border and the river it is moved onto, where it gets on and off
CAP = REACH + 5            # once on a river the border follows it round a bend, but nothing further than this changes hands
SPECK = 40                 # px: pieces of the drawing this small (stray pixels, seams between fills) are left alone
# A quarter of all border was drawn on the hand-drawn rivers (layers/rivers-drawn.PNG), which is proof of what it was meant to
# follow. Where the traced river has moved away from such a stretch, the stretch costs EVCOST a px to keep, and may go up to
# EVREACH px to the river.
EVCOST, EVREACH = 3.0, 30
LINK = 2.7                 # cost of a px of link against 1 for a px of old border: never under 1.5, about 1.9 along the line
                           # the cut finds through the uneven ground below, and 2.2x that for a link REACH long. So a border
                           # goes onto a river ~4x as long as the gap when they are close, ~8x at the full reach, and gets
                           # on and off where the two come closest instead of at the end of its reach
RIVER_SHARE = 1.5          # a patch's new border must be this many px of river for each px of link
SCALE, BIG = 1000, 2_000_000
WA, WD = 0.3927, 0.2777    # 8-neighbour weights that make a cut's cost its length (Cauchy-Crofton)
NONE, U = -9, -1           # not ground a border can cross (sea, coastline stroke, soft pixels); land no nation holds
N = 6000
t0 = time.time()
def tick(s): print("[%4d s] %s" % (time.time() - t0, s), flush=True)

P = os.path.join(LAYERS, "borders.PNG"); keep = os.path.join(WORK, "borders_before_rivers.PNG")
if not os.path.exists(keep): shutil.copy(P, keep)
b = read_png(keep).copy(); al = b[..., 3]
land = np.load(os.path.join(WORK, "land12k.npy")).reshape(N, 2, N, 2).mean((1, 3)) >= 0.5
# The fills cover the base map's ground and stop at its white coastline stroke (138 px of 5.9M stray onto it), so ground is
# all a border can cross: the stroke, the sea and the few soft-edged pixels are never touched.
base = read_png(os.path.join(LAYERS, "base.PNG"))[..., :3].astype(np.int16)
node = (np.abs(base - np.array((180, 179, 191), np.int16)).max(-1) < 14) & ~((al > 40) & (al < 200)); white = (base > 230).all(-1); del base
orig = np.where(al >= 200, (b[..., 0].astype(np.int32) << 16) | (b[..., 1].astype(np.int32) << 8) | b[..., 2], U).astype(np.int32)
keyraw = orig.copy(); orig[~node] = NONE

# ---- the rivers as drawn: how deep under the river's line each possible piece of border lies
fine = read_png(os.path.join(WORK, "rivers12000.png"))[..., 3] > 128
D = np.zeros((2 * N, 2 * N), np.float32)
for y0 in range(0, 2 * N, 2000):
    a_, b_ = max(0, y0 - 16), min(2 * N, y0 + 2016)
    D[y0:y0 + 2000] = ndi.distance_transform_edt(fine[a_:b_])[y0 - a_:y0 - a_ + 2000]
r6 = fine.reshape(N, 2, N, 2).any((1, 3)); del fine
depH = np.zeros((N, N), np.float32); depV = np.zeros((N, N), np.float32); depX = np.zeros((N, N), np.float32)
Dr = D[0::2] + D[1::2]; depH[:, :-1] = (Dr[:, 1:-1:2] + Dr[:, 2::2]) / 4; del Dr
Dc = D[:, 0::2] + D[:, 1::2]; depV[:-1] = (Dc[1:-1:2] + Dc[2::2]) / 4; del Dc
depX[:-1, :-1] = (D[1:-1:2, 1:-1:2] + D[1:-1:2, 2::2] + D[2::2, 1:-1:2] + D[2::2, 2::2]) / 4; del D
# Mean depth (12000 px) at which a piece of border counts as under the river: half of it covered. Anything stricter leaves gaps
# along the thin upper reaches (2-3 px wide at 12000), where at one pixel phase in two no piece is more than half covered.
UNDER = 0.45
def rivercost(d): return 0.1 + 0.6 * (1 - np.minimum(d, 2.0) / 2.0) ** 2

# ---- where a line may run, and what it costs
def differs(a, dy, dx, flip=False):
    o = np.zeros((N, N), bool)
    if flip: o[:-1, :-1] = a[:-1, 1:] != a[1:, :-1]
    else: o[:N - dy, :N - dx] = a[:N - dy, :N - dx] != a[dy:, dx:]
    return o
oldH, oldV, oldD1, oldD2 = differs(orig, 0, 1), differs(orig, 1, 0), differs(orig, 1, 1), differs(orig, 0, 0, True)
bpix = np.zeros((N, N), bool)                                    # ground beside a drawn border between two pieces of land
m = oldH & node & np.roll(node, -1, 1); bpix |= m | np.roll(m, 1, 1)
m = oldV & node & np.roll(node, -1, 0); bpix |= m | np.roll(m, 1, 0)
d_b = ndi.distance_transform_edt(~bpix).astype(np.float32); d_r = ndi.distance_transform_edt(~r6).astype(np.float32)
# Ground may change hands only within REACH of a river and CAP of a drawn border. The river limit is what stops a river
# that crosses a thin strip of a country from handing the whole strip over.
free = node & (d_b < CAP) & (d_r <= REACH)
Z = free & (d_b + d_r <= REACH + 1)                              # ground between a border and a river: where a link may run
drawn = read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0
ev = bpix & (ndi.distance_transform_edt(~drawn) <= 2.5) & (d_r > 1.5) & (d_r <= EVREACH); del drawn
d_e = ndi.distance_transform_edt(~ev).astype(np.float32)
fe = node & (d_e < EVREACH) & (d_r <= REACH + 5); free |= fe; Z |= fe & (d_e + d_r <= EVREACH + 1); del fe
# a link's cost is uneven from px to px, so it is drawn with the small steps of a hand-drawn line and not with a ruler
# (px-to-px grain for the small jogs, a broader swell for the drift: smoothed noise alone leaves neighbouring columns alike
# and the cut still picks one and runs straight down it)
rng = np.random.default_rng(7); nz = rng.standard_normal((N, N)).astype(np.float32); sw = ndi.gaussian_filter(rng.standard_normal((N, N)).astype(np.float32), 2.5)
nz = 0.75 * nz + 0.65 * sw / sw.std(); del sw
nz = np.clip(np.exp(0.9 * nz / nz.std()), 0.55, 3.0) * (1 + 1.2 * np.minimum(np.minimum((d_b + d_r) / REACH, (d_e + d_r) / EVREACH), 2) ** 2)
def caps(dep, old, za, zb, na, nb, w, ea=None, eb=None):
    open_ = np.where(za & zb, LINK * (na + nb) / 2, BIG / (SCALE * w))
    mult = np.where(dep >= UNDER, rivercost(dep), np.where(old, 1.0 if ea is None else np.where(ea | eb, EVCOST, 1.0), open_))
    return np.round(SCALE * w * mult).astype(np.int32)
def sh(a, dy, dx): return np.roll(a, (-dy, -dx), (0, 1))
capH = caps(depH, oldH, Z, sh(Z, 0, 1), nz, sh(nz, 0, 1), WA, ev, sh(ev, 0, 1)); capV = caps(depV, oldV, Z, sh(Z, 1, 0), nz, sh(nz, 1, 0), WA, ev, sh(ev, 1, 0))
capD1 = caps(depX, oldD1, Z, sh(Z, 1, 1), nz, sh(nz, 1, 1), WD, ev, sh(ev, 1, 1)); capD2 = caps(depX, oldD2, sh(Z, 0, 1), sh(Z, 1, 0), sh(nz, 0, 1), sh(nz, 1, 0), WD, sh(ev, 0, 1), sh(ev, 1, 0))
tick("fields ready: %d px of land a border can cross, %d within reach of a border, %d where a link may run | border on a hand-drawn river the traced one has left: %d px"
     % (node.sum(), free.sum(), Z.sum(), ev.sum()))

cur = orig.copy(); frozen = np.zeros((N, N), bool)
labels = [int(v) for v in np.unique(orig) if v != NONE]
for L in labels:
    lb_, k_ = ndi.label(orig == L); sz_ = np.bincount(lb_.ravel()); frozen |= (sz_ <= SPECK)[lb_] & (lb_ > 0)
tick("%d px in pieces of %d px or less, left alone" % (frozen.sum(), SPECK)); del lb_
def bbox(mask):
    ys = np.nonzero(mask.any(1))[0]; xs = np.nonzero(mask.any(0))[0]
    return None if not len(ys) else (ys[0], ys[-1] + 1, xs[0], xs[-1] + 1)
box0 = {L: bbox(orig == L) for L in labels}
pairs = set()
for o_, dy, dx in ((oldH, 0, 1), (oldV, 1, 0)):
    ys, xs = np.nonzero(o_ & node & sh(node, dy, dx)); a_ = orig[ys, xs]; c_ = orig[ys + dy, xs + dx]
    pairs |= set(zip(np.minimum(a_, c_).tolist(), np.maximum(a_, c_).tolist()))
pairs = sorted(pairs); tick("%d pairs of neighbours" % len(pairs))
S8 = np.ones((3, 3), bool)

stuck = []
def solve(A, B, sl, var):
    """Redraw the A|B line over the px in `var` (a mask on the window sl). -> px that changed"""
    c = cur[sl]; isA, isB = c == A, c == B; fA, fB = isA & ~var, isB & ~var
    n = int(var.sum()); idx = np.full(c.shape, -1, np.int64); idx[var] = np.arange(n)
    cS = np.zeros(n, np.int64); cT = np.zeros(n, np.int64); ii, jj, cc = [], [], []
    for cp, ps, qs in ((capH[sl][:, :-1], np.s_[:, :-1], np.s_[:, 1:]), (capV[sl][:-1, :], np.s_[:-1, :], np.s_[1:, :]),
                       (capD1[sl][:-1, :-1], np.s_[:-1, :-1], np.s_[1:, 1:]), (capD2[sl][:-1, :-1], np.s_[:-1, 1:], np.s_[1:, :-1])):
        vp, vq, ip, iq = var[ps], var[qs], idx[ps], idx[qs]
        k = vp & vq; ii.append(ip[k]); jj.append(iq[k]); cc.append(cp[k])
        for vv, iv, other in ((vp, ip, qs), (vq, iq, ps)):
            k = vv & fA[other]; np.add.at(cS, iv[k], cp[k])
            k = vv & fB[other]; np.add.at(cT, iv[k], cp[k])
    ii = np.concatenate(ii); jj = np.concatenate(jj); cc = np.concatenate(cc); ar = np.arange(n); z = np.zeros(n, np.int64)
    cS = np.minimum(cS, 2 ** 30); cT = np.minimum(cT, 2 ** 30)
    G = sparse.coo_matrix((np.concatenate([cc, cc, cS, z, cT, z]).astype(np.int32),
                           (np.concatenate([ii, jj, np.full(n, n), ar, ar, np.full(n, n + 1)]), np.concatenate([jj, ii, ar, np.full(n, n), np.full(n, n + 1), ar]))),
                          shape=(n + 2, n + 2)).tocsr()
    mf = maximum_flow(G, n, n + 1)
    if mf.flow_value >= BIG // 2: stuck.append((A, B, sl)); return 0          # no line the rules allow: leave it as it is
    fl = mf.flow
    res = (G - fl).tocsr(); res.data[res.data < 0] = 0; res.eliminate_zeros()
    side = np.zeros(n + 2, bool); side[breadth_first_order(res, n, directed=True, return_predecessors=False)] = True
    new = np.where(side[:n], A, B).astype(np.int32); was = c[var]; c[var] = new
    return int((new != was).sum())

def sweep(dirty):
    """One pass over every pair, wherever `dirty` says something nearby moved. -> (px changed, the next dirty)"""
    nxt = np.zeros((N, N), bool); tot = 0
    for A, B in pairs:
        ba, bb = box0[A], box0[B]; pad = 3 * REACH + 6
        y0, y1 = max(ba[0], bb[0]) - pad, min(ba[1], bb[1]) + pad; x0, x1 = max(ba[2], bb[2]) - pad, min(ba[3], bb[3]) + pad
        if y0 >= y1 or x0 >= x1: continue
        sl = np.s_[max(0, y0):min(N, y1), max(0, x0):min(N, x1)]
        if not dirty[sl].any(): continue
        c = cur[sl]; isA, isB = c == A, c == B
        I = (isA & ndi.binary_dilation(isB, S8)) | (isB & ndi.binary_dilation(isA, S8))
        if not I.any(): continue
        near = ndi.distance_transform_edt(~I) <= 2 * REACH + 2
        lab, k = ndi.label(near, S8)
        for i, o in enumerate(ndi.find_objects(lab)):
            oy = slice(max(0, o[0].start - 1), o[0].stop + 1); ox = slice(max(0, o[1].start - 1), o[1].stop + 1)
            sub = np.s_[sl[0].start + oy.start:sl[0].start + min(oy.stop, c.shape[0]), sl[1].start + ox.start:sl[1].start + min(ox.stop, c.shape[1])]
            if not dirty[sub].any(): continue
            cs = cur[sub]; var = (lab[oy, ox] == i + 1) & ((cs == A) | (cs == B)) & free[sub] & ~frozen[sub]
            if not var.any(): continue
            t1 = time.time(); ch = solve(A, B, sub, var)
            if time.time() - t1 > 3: tick("    slow: pair %s|%s, %d px, %.0f s, window %s" % (A, B, int(var.sum()), time.time() - t1, sub))
            if ch:
                tot += ch; p2 = 2 * REACH + 6
                nxt[max(0, sub[0].start - p2):sub[0].stop + p2, max(0, sub[1].start - p2):sub[1].stop + p2] = True
    return tot, nxt

def settle(dirty, what):
    for s in range(8):
        ch, dirty = sweep(dirty); tick("  %s, pass %d: %d px changed sides" % (what, s + 1, ch))
        if not ch: break

# ---- cities
rows = [r for r in csv.DictReader(open(os.path.join(MAP, "src", "data", "coordinates.tsv"), encoding="utf-8"), delimiter="\t") if r["KIND"] == "city" and r["X"]]
cities = [(r["NAME"], int(float(r["Y"])), int(float(r["X"]))) for r in rows]; cities = [c for c in cities if 0 <= c[1] < N and 0 <= c[2] < N]
disc = lambda r: np.hypot(*np.mgrid[-r:r + 1, -r:r + 1]) <= r

def under_river(lb):
    """px on either side of a piece of border that lies under a river's line"""
    ur = np.zeros((N, N), bool)
    for dep, dy, dx in ((depH, 0, 1), (depV, 1, 0)):
        q = sh(lb, dy, dx); e = (lb != q) & (lb != NONE) & (q != NONE) & (dep >= UNDER); ur |= e | np.roll(e, (dy, dx), (0, 1))
    return ur

def check(base, bends=False):
    """The patches that changed hands since `base`. -> list of (mask slice, mask, reason) for those to put back, and their number"""
    # a patch is ground that went from one holder to one other: where two countries both gain along a river, each gain is
    # judged on its own, or a strip won fairly carries a corner cut between the two that no river asked for
    changed = cur != base; ys, xs = np.nonzero(changed); code = (base[ys, xs].astype(np.int64) << 32) | (cur[ys, xs].astype(np.int64) & 0xffffffff)
    lab = np.zeros((N, N), np.int32); k = 0
    for pr in np.unique(code):
        m = code == pr; y_, x_ = ys[m], xs[m]; y0, x0 = y_.min(), x_.min(); sub = np.zeros((y_.max() - y0 + 1, x_.max() - x0 + 1), bool); sub[y_ - y0, x_ - x0] = True
        lb, kk = ndi.label(sub, S8); lab[y_, x_] = lb[y_ - y0, x_ - x0] + k; k += kk
    bad = {}; objs = ndi.find_objects(lab); ur = under_river(cur) if bends else None
    for i, o in enumerate(objs):
        sl = np.s_[max(0, o[0].start - 1):o[0].stop + 1, max(0, o[1].start - 1):o[1].stop + 1]
        m = lab[sl] == i + 1; c = cur[sl]; nr = nb = no = 0
        for dep, old, ps, qs in ((depH[sl], oldH[sl], np.s_[:, :-1], np.s_[:, 1:]), (depV[sl], oldV[sl], np.s_[:-1, :], np.s_[1:, :])):
            e = (c[ps] != c[qs]) & (m[ps] | m[qs]) & (c[ps] != NONE) & (c[qs] != NONE); dp = dep[ps]; ol = old[ps]
            r_ = e & (dp >= UNDER); nr += int(r_.sum()); nb += int((e & ~r_ & ol).sum()); no += int((e & ~r_ & ~ol).sum())
        if nr < RIVER_SHARE * no or nr == 0: bad[i + 1] = "new border only %d px river against %d px link" % (nr, no)
        elif bends:
            # a bend counts only where the border runs on under the river past both its ends: then it is the river the
            # border follows wandering off and coming back, and not two rivers that happen to close off a corner
            w = np.s_[max(0, o[0].start - 14):o[0].stop + 14, max(0, o[1].start - 14):o[1].stop + 14]; mw = lab[w] == i + 1
            lu, _ = ndi.label(ur[w], S8); ids = np.unique(lu[ur[w] & ndi.binary_dilation(mw, S8)]); dp_ = ndi.distance_transform_edt(~mw)
            ring, kr = ndi.label(np.isin(lu, ids[ids > 0]) & (dp_ > 3) & (dp_ <= 12), S8)
            if (np.bincount(ring.ravel())[1:] >= 5).sum() < 2: bad[i + 1] = "a river bend the border does not follow on both sides"
    # a country may not be split
    for L in labels:
        if L == U: continue
        bx = box0[L]; sl = np.s_[max(0, bx[0] - REACH - 2):bx[1] + REACH + 2, max(0, bx[2] - REACH - 2):bx[3] + REACH + 2]
        if not changed[sl].any(): continue
        la, ka = ndi.label(cur[sl] == L); lo, ko = ndi.label(orig[sl] == L)
        if ka <= ko: continue
        core = (cur[sl] == L) & (orig[sl] == L)
        seen = {}
        for a_ in range(1, ka + 1):
            mm = la == a_; os_ = np.unique(lo[mm & core]); os_ = os_[os_ > 0]
            key = int(os_[0]) if len(os_) else -a_; seen.setdefault(key, []).append((int(mm.sum()), a_))
        for key, parts in seen.items():
            if len(parts) < 2: continue
            for size, a_ in sorted(parts)[:-1]:
                near = ndi.binary_dilation(la == a_, S8, iterations=3)
                for v in np.unique(lab[sl][near]):
                    if v: bad.setdefault(int(v), "would cut a piece of a country off")
    out = [(objs[v - 1], lab[objs[v - 1]] == v, why) for v, why in bad.items()]
    # A city keeps its country. One standing at the river (within 3 px) is moved onto its own bank by citybanks.py, if that
    # bank is within 8 px; round any other the border is left as drawn, for 12 px either way.
    for name, y, x in cities:
        v = lab[y, x]
        if not v or v in bad: continue
        if d_r[y, x] <= 3 and y >= 8 and x >= 8:
            w = np.s_[y - 8:y + 9, x - 8:x + 9]
            if cur[w].shape == (17, 17) and ((cur[w] == orig[y, x]) & (d_r[w] >= 1.5) & disc(8)).any(): continue
        if bends: out.append((objs[v - 1], lab[objs[v - 1]] == v, "would move %s to another country" % name)); bad[int(v)] = 1; continue
        w = np.s_[max(0, y - 12):y + 13, max(0, x - 12):x + 13]; dd = disc(12)[12 - (y - w[0].start):, 12 - (x - w[1].start):][:cur[w].shape[0], :cur[w].shape[1]]
        out.append((w, (lab[w] == v) & dd, "would move %s to another country" % name))
    return out, k

def putback(base, what, bends=False):
    for rnd in range(40):
        bad, k = check(base, bends); tick("%s, check %d: %d patches changed hands, %d fail" % (what, rnd + 1, k, len(bad)))
        if not bad: break
        dirty = np.zeros((N, N), bool)
        for o, m, why in bad:
            g = np.s_[max(0, o[0].start - 2):o[0].stop + 2, max(0, o[1].start - 2):o[1].stop + 2]
            mm = np.zeros(cur[g].shape, bool); mm[o[0].start - g[0].start:o[0].stop - g[0].start, o[1].start - g[1].start:o[1].stop - g[1].start] = m
            # frozen with a rim, so the next line does not hug it; the rim only over ground that has not moved, or it would
            # clip the patch next door and leave a border no rule allows
            mm |= ndi.binary_dilation(mm, S8, iterations=1 if "only 0 px river" in why or bends else 2) & (cur[g] == base[g]) & (cur[g] != NONE)
            cur[g][mm] = base[g][mm]; frozen[g] |= mm
            p2 = 2 * REACH + 6; dirty[max(0, g[0].start - p2):g[0].stop + p2, max(0, g[1].start - p2):g[1].stop + p2] = True
            rejected.append(((o[1].start + o[1].stop) // 2, (o[0].start + o[0].stop) // 2, int(m.sum()), why))
        settle(dirty, "  borders round the patches put back")

settle(np.ones((N, N), bool), "borders onto rivers")
rejected = []
putback(orig, "borders onto rivers")

# ---- river bends. A border now on a river follows it round a bend that takes it further than CAP from the drawn line, out to
# BEND px: no links here, only ground the river itself closes off against the border as it now stands.
BEND = 2 * REACH
stage = cur.copy(); nA = len(rejected)
oldH, oldV, oldD1, oldD2 = differs(stage, 0, 1), differs(stage, 1, 0), differs(stage, 1, 1), differs(stage, 0, 0, True)
free = node & (d_b < BEND) & (d_r <= REACH + 5); no_ = np.zeros((N, N), bool)      # the middle of a wide bend is further from the river
capH = caps(depH, oldH, no_, no_, nz, nz, WA); capV = caps(depV, oldV, no_, no_, nz, nz, WA)
capD1 = caps(depX, oldD1, no_, no_, nz, nz, WD); capD2 = caps(depX, oldD2, no_, no_, nz, nz, WD)
settle(np.ones((N, N), bool), "river bends")
putback(stage, "river bends", True)
bendpx = int((cur != stage).sum())

# ---- seams. The drawing has stray unfilled px along some borders (a 1 px gap between two fills). Where the border has moved
# away and such a gap is left inside one country's ground, it is filled; a gap still on a border is left as drawn.
lu, ku = ndi.label(orig == U); szu = np.bincount(lu.ravel()); seams = 0
for i, o in enumerate(ndi.find_objects(lu)):
    if szu[i + 1] > SPECK: continue
    w = np.s_[max(0, o[0].start - 1):o[0].stop + 1, max(0, o[1].start - 1):o[1].stop + 1]; m = lu[w] == i + 1
    ring = ndi.binary_dilation(m, S8) & ~m & (cur[w] != NONE); v = np.unique(cur[w][ring])
    if len(v) == 1 and v[0] >= 0 and (cur[w][ring] != orig[w][ring]).any(): cur[w][m] = v[0]; seams += int(m.sum())
del lu
np.save(os.path.join(WORK, "riverborders_labels.npy"), cur)

# ---- write
ch = cur != orig; assert not (ch & ~node).any()
# The fills have a soft edge, 1 px of the colour at half strength, and a few hundred filled px are not ground. Neither is
# ground a border can cross, so left alone they stay behind as a ghost of the old edge in ground that changed hands. Each one
# beside moved ground takes the holder of the ground all round it: solid if a country, cleared if nobody.
soft = (al > 40) & (al < 200); fin = cur.copy(); cand = ~node & ((keyraw != U) | soft) & ~white; strays = 0     # never the white coastline stroke
for _ in range(3):
    for y, x in zip(*np.nonzero(cand & ndi.binary_dilation(fin != orig, S8) & (fin == NONE))):
        nb = fin[max(0, y - 1):y + 2, max(0, x - 1):x + 2]; v = nb[nb != NONE]
        if len(v) and (v == v[0]).all() and (soft[y, x] or v[0] != keyraw[y, x]): fin[y, x] = v[0]; strays += 1
rgb = (b[..., 0].astype(np.int32) << 16) | (b[..., 1].astype(np.int32) << 8) | b[..., 2]              # and a soft px left with none of its own colour beside it goes
for y, x in zip(*np.nonzero(soft & ~white & ndi.binary_dilation(fin != orig, S8) & (fin == NONE))):
    if not (fin[max(0, y - 1):y + 2, max(0, x - 1):x + 2] == rgb[y, x]).any(): fin[y, x] = U; strays += 1
ch = fin != orig; out = b.copy(); mv = ch & (fin >= 0)
out[mv, 0] = (fin[mv] >> 16) & 255; out[mv, 1] = (fin[mv] >> 8) & 255; out[mv, 2] = fin[mv] & 255; out[mv, 3] = 255
out[ch & (fin == U)] = 0; ch = cur != orig
cand = os.path.join(WORK, "borders_snapped.PNG"); write_png(cand, out)
if "install" in sys.argv[1:]: shutil.copyfile(cand, P); print("installed as layers/borders.PNG")
else: print("wrote work/borders_snapped.PNG; run with `install` to put it in layers/")
vis = np.where(land[..., None], 90, 30).astype(np.uint8).repeat(3, -1); vis[r6] = (70, 120, 220); vis[bpix] = (230, 60, 60); vis[ch] = (240, 200, 40)
write_png(os.path.join(WORK, "riverborders.png"), vis)

def hidden(lb):
    """(border px within REACH of a river, of them under the river's line)"""
    tot = und = 0
    for dep, dy, dx in ((depH, 0, 1), (depV, 1, 0)):
        q = sh(lb, dy, dx); e = (lb != q) & (lb != NONE) & (q != NONE) & (d_r <= REACH); tot += int(e.sum()); und += int((e & (dep >= UNDER)).sum())
    return tot, und
t_, u_ = hidden(orig); t2, u2 = hidden(cur); lab, k = ndi.label(ch, S8)
rep = ["Borders onto rivers, reach %d px. Started from work/borders_before_rivers.PNG." % REACH,
       "Ground that changed hands: %d px (6000 grid) in %d patches; unclaimed land painted: %d px, nation ground cleared: %d px."
       % (int(ch.sum()), k, int((ch & (orig == U)).sum()), int((ch & (cur == U)).sum())),
       "Border within %d px of a river: %d px, under the river's line before: %d (%.0f%%), now: %d of %d (%.0f%%)."
       % (REACH, t_, u_, 100 * u_ / t_, u2, t2, 100 * u2 / t2),
       "Stray unfilled px left inside a country by a moved border, filled: %d; soft-edge and off-ground px that followed the ground round them: %d." % (seams, strays),
       "Of that, %d px is the inside of river bends the border follows round, up to %d px from the drawn line." % (bendpx, BEND),
       "Patches put back as drawn: %d (%d of them river bends)%s" % (len(rejected), len(rejected) - nA, " | solves with no allowed line (left as they were): %d" % len(stuck) if stuck else "")] + ["  at (%d, %d), %d px: %s" % r for r in sorted(rejected, key=lambda r: -r[2])]
nb_ = np.zeros((N, N), bool)
for dy, dx in ((0, 1), (1, 0)):
    q = sh(cur, dy, dx); e = (cur != q) & (cur != NONE) & (q != NONE); nb_ |= e | np.roll(e, (dy, dx), (0, 1))
left = bpix & (d_e == 0) & nb_; ll, kl = ndi.label(ndi.binary_dilation(left, S8), S8); szl = np.bincount(ll[left], minlength=kl + 1)[1:]; ol = ndi.find_objects(ll)
rep += ["Border drawn on a hand-drawn river that the traced river has left: %d px of ground beside it; still where it was: %d px, in %d stretches of 15 px or more:"
        % (int(ev.sum()), int(left.sum()), int((szl >= 15).sum()))]
rep += ["  %d px at (%d, %d), traced river %.0f px away" % (szl[i], (ol[i][1].start + ol[i][1].stop) // 2, (ol[i][0].start + ol[i][0].stop) // 2, float(np.median(d_r[ol[i]][left[ol[i]] & (ll[ol[i]] == i + 1)])))
        for i in np.argsort(-szl) if szl[i] >= 15]
open(os.path.join(WORK, "riverborders_report.txt"), "w").write("\n".join(rep) + "\n"); print("\n".join(rep[:6])); tick("done")
