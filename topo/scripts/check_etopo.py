import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
with rasterio.open(sys.argv[1]) as ds:
    print(ds.width, ds.height, ds.count, ds.dtypes, ds.crs, ds.bounds, "nodata", ds.nodata, ds.compression)
    for name, lon, lat in (("Everest", 86.925, 27.988), ("Dead Sea", 35.5, 31.5), ("Mariana", 142.2, 11.35), ("Denver", -104.99, 39.74)):
        r, c = ds.index(lon, lat)
        print(name, float(ds.read(1, window=((r, r + 1), (c, c + 1)))[0, 0]))
