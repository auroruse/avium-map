"""Projection + warp model shared by the fit and everything downstream."""
import numpy as np
from scipy.interpolate import RBFInterpolator
R = 6371.0
D2R = np.pi / 180

def aeqd_fwd(lon, lat, lon0, lat0):
    lam = (np.asarray(lon, float) - lon0) * D2R; phi = np.asarray(lat, float) * D2R; p0 = lat0 * D2R
    cc = np.clip(np.sin(p0) * np.sin(phi) + np.cos(p0) * np.cos(phi) * np.cos(lam), -1, 1)
    c = np.arccos(cc); k = np.where(c < 1e-9, 1.0, c / np.maximum(np.sin(c), 1e-12))
    return R * k * np.cos(phi) * np.sin(lam), R * k * (np.cos(p0) * np.sin(phi) - np.sin(p0) * np.cos(phi) * np.cos(lam))

def aeqd_inv(x, y, lon0, lat0):
    x = np.asarray(x, float); y = np.asarray(y, float); p0 = lat0 * D2R
    rho = np.hypot(x, y); c = rho / R; rs = np.maximum(rho, 1e-9)
    phi = np.arcsin(np.clip(np.cos(c) * np.sin(p0) + y * np.sin(c) * np.cos(p0) / rs, -1, 1))
    lam = np.arctan2(x * np.sin(c), rs * np.cos(p0) * np.cos(c) - y * np.sin(p0) * np.sin(c))
    lon = lon0 + lam / D2R
    return (lon + 180) % 360 - 180, phi / D2R

def centroid(lon, lat):
    lam = np.asarray(lon) * D2R; phi = np.asarray(lat) * D2R
    v = np.array([np.mean(np.cos(phi) * np.cos(lam)), np.mean(np.cos(phi) * np.sin(lam)), np.mean(np.sin(phi))])
    v /= np.linalg.norm(v)
    return float(np.arctan2(v[1], v[0]) / D2R), float(np.arcsin(v[2]) / D2R)

class Warp:
    """overlay px (6000 grid) -> lon/lat.  plane = A.[u,v,1] (+ TPS residual), u = x, v = -y."""
    def __init__(self, lon0, lat0, A):
        self.lon0, self.lat0, self.A = lon0, lat0, np.asarray(A, float)
        self.tps = None; self.c = np.zeros(2); self.s = 1.0
    def plane(self, x, y):
        u = np.asarray(x, float); v = -np.asarray(y, float)
        E = self.A[0, 0] * u + self.A[0, 1] * v + self.A[0, 2]
        N = self.A[1, 0] * u + self.A[1, 1] * v + self.A[1, 2]
        if self.tps is not None:
            q = np.stack([(u.ravel() - self.c[0]) / self.s, (v.ravel() - self.c[1]) / self.s], 1)
            out = np.empty((len(q), 2))
            for i in range(0, len(q), 200000):
                out[i:i + 200000] = self.tps(q[i:i + 200000])
            E = E + out[:, 0].reshape(E.shape); N = N + out[:, 1].reshape(N.shape)
        post = getattr(self, "post", None)          # set by postfit.py: carries the warp exactly through its cities
        if post is not None:
            E, N = post[0, 0] * E + post[0, 1] * N + post[0, 2], post[1, 0] * E + post[1, 1] * N + post[1, 2]
        layers = ([self.rbf] if getattr(self, "rbf", None) is not None else []) + list(getattr(self, "rbfs", []))
        for rbf in layers:                          # local Gaussian corrections: cities first, then the weld along shared borders
            c, wt, sg = rbf; sh = E.shape; uu = u.ravel(); vv = v.ravel(); add = np.zeros((len(uu), 2))
            for i in range(0, len(uu), 200000):
                k = np.exp(-((uu[i:i + 200000, None] - c[None, :, 0]) ** 2 + (vv[i:i + 200000, None] - c[None, :, 1]) ** 2) / (2 * sg * sg))
                add[i:i + 200000] = k @ wt
            E = E + add[:, 0].reshape(sh); N = N + add[:, 1].reshape(sh)
        return E, N
    def __call__(self, x, y):
        E, N = self.plane(x, y)
        return aeqd_inv(E, N, self.lon0, self.lat0)
    def scale(self):
        return float(np.sqrt(abs(np.linalg.det(self.A[:, :2]))))   # km per px

def fit_similarity(u, v, E, N, w):
    p = u + 1j * v; q = E + 1j * N; w = w / w.sum()
    pm = (w * p).sum(); qm = (w * q).sum()
    a = (w * (q - qm) * np.conj(p - pm)).sum() / max((w * np.abs(p - pm) ** 2).sum(), 1e-12)
    b = qm - a * pm
    return np.array([[a.real, -a.imag, b.real], [a.imag, a.real, b.imag]])

def fit_affine(u, v, E, N, w):
    M = np.stack([u, v, np.ones_like(u)], 1) * np.sqrt(w)[:, None]
    A0 = np.linalg.lstsq(M, E * np.sqrt(w), rcond=None)[0]; A1 = np.linalg.lstsq(M, N * np.sqrt(w), rcond=None)[0]
    return np.stack([A0, A1])


class Relax:
    """work/relax_d.npy: a shift (km, 3-D) of every map position's real place, on a grid of nodes 8 px apart (6000 grid)."""
    def __init__(self, work):
        import os
        f = os.path.join(work, "relax_d.npy")
        self.ok = os.path.exists(f)
        if self.ok: self.D = np.load(f); self.R = np.load(os.path.join(work, "relax_r.npy"))
    def region(self, b, pad=6):
        """the shift field of one region, carried a little past its edge so its cross-fade zone moves with it"""
        if not self.ok: return None
        from scipy import ndimage as ndi
        ii, jj = np.nonzero(self.R == b)
        if not len(ii): return None
        r0, r1, c0, c1 = max(ii.min() - pad, 0), ii.max() + pad + 1, max(jj.min() - pad, 0), jj.max() + pad + 1
        m = self.R[r0:r1, c0:c1] == b
        _, (iy, ix) = ndi.distance_transform_edt(~m, return_indices=True)
        return self.D[r0:r1, c0:c1][iy, ix], r0, c0
    @staticmethod
    def apply(field, lon, lat, x6, y6):
        if field is None: return lon, lat
        from scipy import ndimage as ndi
        Db, r0, c0 = field; sh = np.shape(lon)
        gy = (np.asarray(y6, float).ravel() - 5) / 8 - r0; gx = (np.asarray(x6, float).ravel() - 5) / 8 - c0
        lo = np.radians(np.asarray(lon, float).ravel()); la = np.radians(np.asarray(lat, float).ravel())
        v = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], 1) * R
        for k in range(3): v[:, k] += ndi.map_coordinates(Db[..., k], [gy, gx], order=1, mode="nearest")
        v /= np.linalg.norm(v, axis=1)[:, None]
        return np.degrees(np.arctan2(v[:, 1], v[:, 0])).reshape(sh), np.degrees(np.arcsin(np.clip(v[:, 2], -1, 1))).reshape(sh)
