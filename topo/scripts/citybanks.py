"""Move the city dots that stand in a river onto its bank (user, 16 Nov 2026: "Cities in rivers"; "Move the dot").

riverlayer.py runs a traced river through every city that stood on a drawn one, so about two hundred dots sit on the river's
line. Each is moved to the nearest px that is clear of the river by a px, on the base map's ground, in the country it was in
before riverborders.py moved any border, and not on top of another city. A city that riverborders.py left on the far bank of
a border river (it only does that to a city within 3 px of the river) is brought back to its own bank the same way.
Nothing moves further than MAXMOVE px; what cannot be placed is listed and left.

The source of truth is src/data/cities.json (x, y in 6000 px); coordinates.tsv is regenerated from it by scripts/coords.mjs.
  citybanks.py          what would move
  citybanks.py write    move it, then run `node scripts/coords.mjs` from the app folder
Run after riverborders.py."""
import sys, os, json; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from scipy import ndimage as ndi
MAXMOVE, CLEAR, APART, N = 8, 2.0, 2.0, 6000        # px; clear of the river's drawn line in 12000 px; px between two cities
NONE, U = -9, -1
path = os.path.join(MAP, "src", "data", "cities.json"); raw = open(path, encoding="utf-8").read(); cities = json.loads(raw)
assert json.dumps(cities, indent=2, ensure_ascii=False) + "\n" == raw, "cities.json is not in the form this script writes back"
b = read_png(os.path.join(WORK, "borders_before_rivers.PNG")); al = b[..., 3]
orig = np.where(al >= 200, (b[..., 0].astype(np.int32) << 16) | (b[..., 1].astype(np.int32) << 8) | b[..., 2], U).astype(np.int32)
now = np.load(os.path.join(WORK, "riverborders_labels.npy"))
base = read_png(os.path.join(LAYERS, "base.PNG"))[..., :3].astype(np.int16); ground = np.abs(base - np.array((180, 179, 191), np.int16)).max(-1) < 14; del base
fine = read_png(os.path.join(WORK, "rivers12000.png"))[..., 3] > 128
# distance from each dot position (a px corner: the app draws the marker at x, y) to the river's line, in 12000 px
dist = np.zeros((2 * N, 2 * N), np.float32)
for y0 in range(0, 2 * N, 2000):
    a_, b_ = max(0, y0 - 64), min(2 * N, y0 + 2064); dist[y0:y0 + 2000] = np.minimum(ndi.distance_transform_edt(~fine[a_:b_]), 60)[y0 - a_:y0 - a_ + 2000]
def clear(y, x):                                       # of the four 12000 px cells round the corner
    return float(dist[max(0, 2 * y - 1):2 * y + 1, max(0, 2 * x - 1):2 * x + 1].min())
placed = [c for c in cities if c.get("x") is not None and c.get("y") is not None]
pos = np.array([(c["y"], c["x"]) for c in placed]); taken = {(int(y), int(x)) for y, x in pos}
offs = sorted(((dy, dx) for dy in range(-MAXMOVE, MAXMOVE + 1) for dx in range(-MAXMOVE, MAXMOVE + 1) if 0 < dy * dy + dx * dx <= MAXMOVE * MAXMOVE), key=lambda o: (o[0] ** 2 + o[1] ** 2, o))
moves, stuck = [], []
for i, c in enumerate(placed):
    y, x = int(c["y"]), int(c["x"])
    if not (0 <= y < N and 0 <= x < N): continue
    home = int(orig[y, x]); wet = clear(y, x) < 1.0; away = home != int(now[y, x]) and now[y, x] != NONE and ground[y, x]
    if not (wet or away): continue
    for dy, dx in offs:
        yy, xx = y + dy, x + dx
        if not (0 <= yy < N and 0 <= xx < N) or not ground[yy, xx] or clear(yy, xx) < CLEAR: continue
        if ground[y, x] and int(now[yy, xx]) != home: continue
        d = np.hypot(pos[:, 0] - yy, pos[:, 1] - xx); d[i] = 9e9
        if d.min() < APART: continue
        moves.append((c, x, y, xx, yy, float(np.hypot(dy, dx)), "in the river" if wet else "left on the far bank by a border that moved onto the river", away or int(now[y, x]) != int(now[yy, xx])))
        pos[i] = (yy, xx); break
    else: stuck.append((c["name"], c["nation"], x, y, "in the river" if wet else "on the far bank"))
far = [m for m in moves if m[5] > 4]; crossed = [m for m in moves if "far bank" in m[6]]
lines = ["City dots moved off rivers: %d of %d placed cities, %.1f px on average, %.1f at most." % (len(moves), len(placed), np.mean([m[5] for m in moves]) if moves else 0, max([m[5] for m in moves]) if moves else 0),
         "Brought back across a river that became their country's border: %d" % len(crossed)] + ["  %s (%s): (%d, %d) -> (%d, %d), %.1f px" % (m[0]["name"], m[0]["nation"], m[1], m[2], m[3], m[4], m[5]) for m in crossed]
lines += ["Moved more than 4 px: %d" % len(far)] + ["  %s (%s): (%d, %d) -> (%d, %d), %.1f px, %s" % (m[0]["name"], m[0]["nation"], m[1], m[2], m[3], m[4], m[5], m[6]) for m in far]
lines += ["Could not be placed within %d px and left where they were: %d" % (MAXMOVE, len(stuck))] + ["  %s (%s) at (%d, %d), %s" % s for s in stuck]
print("\n".join(lines))
if "write" in sys.argv[1:]:
    for c, x, y, xx, yy, *_ in moves: c["x"], c["y"] = int(xx), int(yy)
    open(path + ".tmp", "w", encoding="utf-8").write(json.dumps(cities, indent=2, ensure_ascii=False) + "\n"); os.replace(path + ".tmp", path)
    open(os.path.join(WORK, "citybanks_report.txt"), "w").write("\n".join(lines + ["All moves:"] + ["  %s (%s): (%d, %d) -> (%d, %d)" % (m[0]["name"], m[0]["nation"], m[1], m[2], m[3], m[4]) for m in moves]) + "\n")
    print("cities.json written; now run `node scripts/coords.mjs` in the app folder")
