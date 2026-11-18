"""Built-up ground on the real Earth, on the imagery's 60s grid -> work/urban_real.npy (bool, 10800 x 21600).

The photographs show the real Earth's cities: pale grey-tan patches where Tokyo, Osaka and every town of the North China
Plain stand, and Avium's cities stand elsewhere (user, 18 Nov 2026: "There are urban blotches everywhere that we
shouldn't have", and of the patch beside Lake Baishin, a real city's, "looks duplicated"). colour.py paints real
countryside over them.

- Cities and towns: Natural Earth's urban areas (data/ne_urban, from 2002-03 MODIS, the imagery's own years).
- Villages too small for that map: bright dots a few px across, paler and less green than the green country they stand
  in, on flat ground within 45 km of a mapped town, so that nothing is taken from country where nobody lives, nor the
  pale fields of country that is pale all over.
- Water painted from them: the imagery's water is painted over from the nearest land (colour.month_bm), so a lake with a
  built-up shore is a patch of that shore's colour in the lake's shape.
- The real Earth's lakes (data/ne_lakes), for the same reason as its cities: they lie where Avium has none. Most are
  dark and already painted over as water; a silty one is not, and Lake Khanka lay pale beside Lake Baishin like a second
  lake (user: "Lake Baishin looks duplicated"). Where Avium has a lake of its own there, that is water and stays so."""
import sys, time; sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *
from scipy import ndimage as ndi
import shapefile
from rasterio import features
from rasterio.transform import from_origin
t0 = time.time()
def tick(s): print("  [%3.0f s] %s" % (time.time() - t0, s), flush=True)
HAT, NEAR = 9.0, 24          # levels a dot stands above the ground round it; px (60s) from a mapped town

def build():
    sf = shapefile.Reader(os.path.join(DATA, "ne_urban", "ne_10m_urban_areas.shp"))
    ne = features.rasterize([(s.__geo_interface__, 1) for s in sf.iterShapes()], out_shape=(10800, 21600), transform=from_origin(-180, 90, 1 / 60, 1 / 60), all_touched=True, dtype="uint8").astype(bool)
    land = np.load(os.path.join(WORK, "real_lab.npy")) != 0; ne &= land; tick("mapped towns: %.2f%% of land" % (100.0 * ne.sum() / land.sum()))
    dem = np.load(os.path.join(WORK, "dem60.npy")).astype(np.float32); relief = ndi.maximum_filter(dem, 5) - ndi.minimum_filter(dem, 5); del dem
    # each hemisphere in its summer, as colour.py shows it
    lum = np.zeros(land.shape, np.float32); grn = np.zeros(land.shape, np.float32)
    for mm, rows in (("07", slice(0, 5400)), ("01", slice(5400, 10800))):
        a = np.load(os.path.join(WORK, "bm_%s.npy" % mm), mmap_mode="r")[rows].astype(np.float32)
        lum[rows] = a @ np.array([0.30, 0.59, 0.11], np.float32); grn[rows] = a[..., 1] - a[..., 0]; del a
    hat = lum - ndi.grey_opening(lum, footprint=np.hypot(*np.mgrid[-3:4, -3:4]) <= 3.2); tick("dots")
    near = ndi.distance_transform_edt(~ne) <= NEAR
    gm = ndi.uniform_filter(grn, 15)
    dot = (hat > HAT) & land & near & ~ne & (relief < 250) & (gm > 3) & (grn < gm - 4) & (lum < 150)
    lab, n = ndi.label(dot, structure=np.ones((3, 3))); size = ndi.sum(dot, lab, np.arange(1, n + 1))
    dot = np.concatenate([[False], (size <= 16)])[lab]; del lab
    tick("villages: %.2f%% of land" % (100.0 * dot.sum() / land.sum()))
    urban = ne | dot; del lum, grn, hat, near, gm, relief
    import colour as C, rasterio
    for mm, rows in (("07", slice(0, 5400)), ("01", slice(5400, 10800))):       # small lakes are water by their colour alone
        with rasterio.open(os.path.join(DATA, "bluemarble", "world.2004%s.3x21600x10800.jpg" % mm)) as ds: land[rows] &= ~C.water_of(np.moveaxis(ds.read(), 0, -1))[rows]
    urban &= land
    d, (iy, ix) = ndi.distance_transform_edt(~land, return_indices=True); wet = ~land & (d <= 30) & urban[iy, ix]; del d, iy, ix
    wet = ndi.binary_dilation(wet, iterations=4) & ~land; tick("water painted from them: %.2f%% of land's area" % (100.0 * wet.sum() / land.sum()))
    urban |= wet; del wet
    sf = shapefile.Reader(os.path.join(DATA, "ne_lakes", "ne_10m_lakes.shp"), encoding="utf-8", encodingErrors="replace")
    lakes = features.rasterize([(s.__geo_interface__, 1) for s in sf.iterShapes()], out_shape=(10800, 21600), transform=from_origin(-180, 90, 1 / 60, 1 / 60), all_touched=True, dtype="uint8").astype(bool)
    urban |= ndi.binary_dilation(lakes, iterations=1); tick("real lakes: %.2f%% of land's area" % (100.0 * lakes.sum() / land.sum())); del lakes
    np.save(os.path.join(WORK, "urban_real.npy"), urban); tick("built-up ground and lakes: %.2f%% of land" % (100.0 * urban.sum() / land.sum()))
    return urban

if __name__ == "__main__": build()
