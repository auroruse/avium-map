"""Shared helpers for the topography build. Run with the venv python, -I."""
import os, numpy as np
os.environ.setdefault("GDAL_PAM_ENABLED", "NO")
import rasterio
import warnings
warnings.filterwarnings("ignore", category=rasterio.errors.NotGeoreferencedWarning)

TOPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.dirname(TOPO)
LAYERS = os.path.join(MAP, "layers")
DATA = os.path.join(TOPO, "data")
WORK = os.path.join(TOPO, "work")

def read_png(path):
    """-> uint8 array (H, W, C)"""
    with rasterio.open(path) as ds:
        return np.moveaxis(ds.read(), 0, -1)

def write_png(path, arr):
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    h, w, c = arr.shape
    with rasterio.open(path, "w", driver="PNG", width=w, height=h, count=c, dtype=arr.dtype) as ds:
        ds.write(np.moveaxis(arr, -1, 0))
