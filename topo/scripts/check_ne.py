import sys, shapefile
root = sys.argv[1]
for d, f in [("ne_countries", "ne_10m_admin_0_countries"), ("ne_places", "ne_10m_populated_places"),
             ("ne_rivers", "ne_10m_rivers_lake_centerlines"), ("ne_lakes", "ne_10m_lakes")]:
    r = shapefile.Reader(f"{root}/{d}/{f}", encoding="utf-8")
    print(f"{f}: {len(r)} records, type {r.shapeTypeName}, bbox {[round(v, 1) for v in r.bbox]}")
