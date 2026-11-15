"""Which way each hand-drawn river runs, and how far the ground under it runs uphill.
Rivers and the lakes they touch form one network; each network drains to the sea where it touches it, else to its lowest point.
Run it to audit a height file:  riverflow.py [height.npy [waterlevel.npy [x y]]]"""
import sys, time, heapq; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
N = 6000

def network(H12, lev12, riv=None):
    """-> dict: y, x (6000 grid), h (ground, or lake level), pred (downstream node, -1 at a mouth or in a lake), dist, riv, lake id (0 = not a lake)"""
    if riv is None: riv = read_png(os.path.join(LAYERS, "rivers-drawn.PNG"))[..., 3] > 0
    land = read_png(os.path.join(LAYERS, "mono.png"))[:, :, 0] > 0
    wl, nw = ndi.label(~land); ocean = wl == (np.bincount(wl.ravel())[1:].argmax() + 1); lake = (~land) & ~ocean
    H = np.maximum(np.asarray(H12).reshape(N, 2, N, 2).astype(np.float32), 0.5).mean((1, 3))
    lev = np.asarray(lev12[1::2, 1::2], np.float32)
    near = ndi.binary_dilation(riv, iterations=3)
    ll, nl = ndi.label(lake); touched = np.unique(ll[near & lake]); touched = touched[touched > 0]
    lk = np.isin(ll, touched)
    net = ((riv & land) | lk | (ndi.binary_dilation(lk, iterations=3) & near & land)) & ~ocean      # rivers, their lakes, and the few px between
    lmax = np.r_[0.0, ndi.maximum(lev, ll, np.arange(1, nl + 1))].astype(np.float32) if nl else np.zeros(1, np.float32)
    h = np.where(lk, lmax[ll], H)                                # one level per lake: its edge px can read 0 on the finer grid
    ys, xs = np.nonzero(net); n = len(ys); idx = -np.ones((N, N), np.int64); idx[ys, xs] = np.arange(n)
    hv = h[ys, xs]; I, J = [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        y2, x2 = ys + dy, xs + dx; ok = (y2 < N) & (x2 >= 0) & (x2 < N); j = np.where(ok, idx[np.clip(y2, 0, N - 1), np.clip(x2, 0, N - 1)], -1); ok &= j >= 0
        i = np.arange(n)[ok]; j = j[ok]; I += [i, j]; J += [j, i]
    G = coo_matrix((np.ones(sum(len(i) for i in I), np.int8), (np.concatenate(I), np.concatenate(J))), shape=(n, n)).tocsr()
    nc, comp = connected_components(G, directed=False)
    atsea = ndi.distance_transform_edt(~ocean)[ys, xs] <= 3.0
    islake = lk[ys, xs]
    src = atsea | islake; hassea = np.zeros(nc, bool); hassea[comp[atsea]] = True    # a lake takes whatever runs down to it; nothing is forced out of it
    order = np.lexsort((hv, comp)); first = np.r_[True, comp[order][1:] != comp[order][:-1]]; low = order[first]
    src[low[~hassea[comp[low]]]] = True                                    # a network with no mouth drains to its lowest point
    # priority flood from the mouths: each node drains to the mouth or lake it can reach over the lowest ground
    ip, ix = G.indptr, G.indices; hl = hv.tolist(); pred = np.full(n, -1, np.int64); dist = np.zeros(n); seen = np.zeros(n, bool)
    heap = [(hl[i], 0, int(i)) for i in np.nonzero(src)[0]]; heapq.heapify(heap); seen[src] = True; c = 0
    while heap:
        lv, _, i = heapq.heappop(heap); dist[i] = c; c += 1
        for j in ix[ip[i]:ip[i + 1]]:
            if not seen[j]: seen[j] = True; pred[j] = i; heapq.heappush(heap, (max(lv, hl[j]), c, int(j)))
    return dict(y=ys, x=xs, h=hv, pred=pred, dist=dist, riv=riv[ys, xs], lake=np.where(lk, ll, 0)[ys, xs], comp=comp, nc=nc, nsea=int(hassea.sum()), root=src)

def climb(net, h=None):
    """Metres each node sits below the highest ground between it and its mouth."""
    h = net["h"] if h is None else h; bar = h.copy(); pred = net["pred"]
    for i in np.argsort(net["dist"]):
        if pred[i] >= 0: bar[i] = max(h[i], bar[pred[i]])
    return bar - h

if __name__ == "__main__":
    a = sys.argv[1:]; t0 = time.time()
    net = network(np.load(os.path.join(WORK, a[0] if a else "height_raw.npy"), mmap_mode="r"), np.load(os.path.join(WORK, a[1] if len(a) > 1 else "waterlevel.npy"), mmap_mode="r"))
    c = climb(net); r = net["riv"]
    print("networks:", net["nc"], "| reach the sea or a lake:", net["nsea"], "| river px:", int(r.sum()))
    for m in (5, 20, 50, 100, 200, 500, 1000): print("  river px that must climb more than %4d m to get out: %5.1f%%" % (m, 100 * (c[r] > m).mean()))
    if len(a) > 3:
        ys, xs, pred = net["y"], net["x"], net["pred"]; k = int(np.argmin((xs - int(a[2])) ** 2 + (ys - int(a[3])) ** 2)); out = []
        while k >= 0 and len(out) < 6000: out.append(k); k = pred[k]
        out = np.array(out); st = max(len(out) // 40, 1)
        print("from (%d, %d) downstream, %d px to the mouth at (%d, %d):" % (xs[out[0]], ys[out[0]], len(out), xs[out[-1]], ys[out[-1]]))
        print(" ".join("%d" % v for v in net["h"][out][::st]))
    print("done %.0f s" % (time.time() - t0))
