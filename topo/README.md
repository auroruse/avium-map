# topo — the ground under Avium

Builds the ground layers (shaded relief for the Political map, shaded and unshaded elevation tints for the
Terrain map, the Satellite map's ground), the contour lines and the rivers layers from real elevation and, for
the Satellite map, real imagery. The Satellite map was called Hybrid until 17 Nov 2026 and still is in the code,
the file names and most of what follows.

`layers/pangaea.PNG` is a present-day political map bent into Pangaea, and Avium's coast was traced
over it. So every pixel of Avium land is a piece of the real Earth that has been moved. This folder
works out which piece, samples real elevation there, and conditions the result to Avium's own land
and sea.

Nothing here is needed to run the map. The tiles it produces are committed like the others.

## Running it

```
python3 -m venv topo/.venv && topo/.venv/bin/pip install numpy scipy rasterio pyshp
```

Source data goes in `topo/data/` (gitignored), each set in its own folder:

| Folder | File | From |
|---|---|---|
| `etopo/` | `ETOPO_2022_v1_30s_N90W180_bed.tif` (1.6 GB) | NOAA NCEI, ETOPO 2022, 30 arc-second bedrock |
| `ne_countries/` | `ne_10m_admin_0_countries` | Natural Earth 1:10m |
| `ne_places/` | `ne_10m_populated_places` | Natural Earth 1:10m |
| `ne_rivers/` | `ne_10m_rivers_lake_centerlines` | Natural Earth 1:10m |
| `ne_lakes/` | `ne_10m_lakes` | Natural Earth 1:10m |
| `bluemarble/` | `world.2004MM.3x21600x10800.jpg`, twelve months (271 MB); and at 500 m, `world.200407.3x21600x21600.<A-D>1.jpg` and `world.200401.3x21600x21600.<A-D>2.jpg` (354 MB): July for the northern tiles, January for the southern | NASA Blue Marble Next Generation, base: `assets.science.nasa.gov/content/dam/science/esd/eo/images/bmng/bmng-base/<month>/` |

Then, in order. Each step reads the last one's output from `topo/work/` (gitignored).

| Step | Script | What it does |
|---|---|---|
| 1 | `palette.py`, `segment.py`, `blobs.py`, `merge.py`, `merge2.py 18` | Cuts the overlay into colour blobs, one per country more or less |
| 2 | `ne_raster.py`, `dem60.py` | Real countries as a grid; elevation at 60 arc-seconds with lakes levelled |
| 3 | `units.py`, `junctions.py`, `dots.py --detect` | Regions, their border samples, the points where three countries meet, the overlay's city dots |
| 4 | `run_fit.sh` | The georeference: one warp per region (`fit.py`), then carried through the cities (`donors.py`, `postfit.py`) and welded along shared borders (`seams.py`, `weld.py`) |
| 5 | `build.sh` | Elevation through the warps, rivers calibrated on their cities, Avium terrain and sea floor, rivers traced in the valleys, their beds settled, the land's colour from space (`place.py`, `colour.py`), and the drawings in `layers/` |
| 6 | `install_rivers.py`, `thumbs.py`, then `npm run tile` | The rivers layer goes in place; the map tiles what changed |

`labels.txt` says which country each overlay blob is. It was read by eye and belongs to one
segmentation: rerun step 1 with different settings and the blob numbers move.

## How the georeference works

Each region's warp is fitted so that its borders land on the real borders of the same country:
a border with France only matches France's border, a coast only matches a coast that faces the same
way. The warp starts rigid and is allowed to bend in stages; a stage that would fold the map is refused.

Then three corrections, none of them a fit:

- **Printed cities.** The overlay prints about three hundred real cities. `cities.txt` names each dot
  from its label, and every warp is carried exactly through its own.
- **Avium cities.** Most Avium cities stand where their stat donor stands on the overlay. `donors.py`
  keeps the ones whose donor is in the country the overlay shows under them and near where the warp
  already puts them (some donors only lend statistics), and the warps follow those on average,
  since they were placed by hand.
- **Shared borders.** Where two neighbours name slightly different real places for the same border
  pixel, both are bent to meet in the middle.

`qa.py`, `seams.py`, `where.py` and `folds.py` are the checks. `work/agree.png` shows every overlay
land pixel pushed through its warp, green where it lands in its own country.

`labels.txt` and `cities.txt` were read by eye. To correct a region, add or fix a line in
`cities.txt` (or a cape in `landmarks.txt`) and rerun from step 4.

## Keeping the terrain's shape

The overlay was fitted to a square and squeezes parts of the world two- and threefold. Followed exactly, real
ridges come out as streaks. `relax.py` (run by `build.sh`) solves for one smooth shift of every pixel's real
position that caps the local stretch at 1.5, gives crushed ground a footprint back, and moves ground that
landed on real sea toward the nearest real shore, while the printed cities hold and real neighbours stay
joined. Ground between cities can end up 50 to 150 km from where the overlay strictly puts it in the squeezed
areas; that was chosen over streaks.

`quality.py` is the audit to run after any change: stretch, invented ground, lakes and river breaks, by nation.
`look.py` and `overview.py` render check sheets.

## What Avium changes

- **Coast.** Land is wherever `layers/mono.png` says. Ground meets the sea at sea level. Ground that still lands just off a real coast samples the real terrain mirrored across that coast.
- **Lakes.** Every inland water body is a lake at the height of its own shore, with a bowl as deep as its width allows.
- **Every body of water** (`seafloor.py`).
  - *Open ocean.* Generated; nothing is carried over from Earth's oceans, because a real floor brings real islands
    with it and Avium already has those as land. Nothing is constructed from distances between points or from
    cells either: a ridge at a set distance from the coast came out as a ring, and plates as cells came out as a
    honeycomb. The ridge is where a broad field of noise changes sign, so it wanders across the ocean as a few
    long lines; only in a narrow ocean between two great land masses does it run down the middle. The crust sinks
    as it ages away from the crest. Fracture zones are noise smeared along the spreading direction: each streak
    sets the crest off sideways and carries the step in age down its whole length. Abyssal hills are fine noise
    smeared the other way, the floor is rough everywhere and roughest at the crest, and sediment buries all of it
    near the continents. On top: plateaus, scattered seamounts, and chains of volcanoes. Every group of small Avium
    islands out in the ocean is the young end of a chain that runs on from its smaller islands.
  - *Enclosed and marginal seas.* How deep a sea can be follows from how wide it is at that place, so a strait is a
    sill, a gulf is shallower than the sea it opens on, and a wide sea has deep basins parted by rises.
  - *Drowned land.* Greenland, the central Sahara and the western Amazon are land on the overlay and sea in Avium.
    They keep their real relief, sunk: highlands are rises on the basin floor, ridges and valleys its grain.
  - *Margins.* Shelf width has Earth's own spread, measured off the real elevation (half of all coast has under
    15 km of shelf, a tenth over 125 km): most coast drops straight off and a few stretches carry a broad platform.
    Low coasts and bays lean wide, mountain coasts narrow. `SHELF_MED` and `SHELF_SPREAD` set it; a shelf of much
    the same width on every coast is a halo. The margin is one surface from the shore to the deep floor: shelf and
    fall meet at the same depth and slope, the break is rounded, and where the shelf ends is ragged at every scale.
    A step or a knee along a clean curve reads as a ruled line. A high coast on open ocean gets a trench. Nothing is
    cut off a river mouth: a trench across the shelf is as dark as a river and reads as one drawn out to sea.
  - *How deep a sea is.* One rule for all water: the wider it is, the nearer its floor comes to an ocean's. Whether
    straits or a broad mouth join a sea to the ocean changes nothing. Mountains round a narrow sea deepen it.
  - *Islands.* A small island is a volcano: almost no shelf, a flank straight down to the deep floor, and a shared
    ridge under a chain or cluster. Only a large island carries a shelf, in proportion to its size.
- **The Hybrid map's ground** (`place.py`, `colour.py`, then `hybrid.py` with `satgrade.py` and `seacolour.py`).
  The terrain map in the colours the ground has from space: the satellite layer under the relief map's hillshade.
  - *The satellite layer* (`colour.py` -> `work/colour.npy`). NASA Blue Marble carried through the same warps, relaxation
    and river calibration as the elevation, so every pixel of land has the colour of the real place its ground came from,
    each in its own midsummer month, and forest stands on the same ranges the relief shows.
  - *Climate.* The imagery brings Earth's with it: the Canadian Arctic's ice caps stand at 21-24 N on Avium. Snow and ice
    that last the real summer stay only above Avium's permanent snow line (`permanent()`); below it a pixel shows the
    month near midsummer in which the country round it lies barest, and ice that is never bare is painted over with
    pieces of real bare ground copied from beside it. Avium's rules choose which real pixel shows, never what one looks like.
  - *Stretch.* The overlay stretches ground up to threefold (Guandong, parts of Nichirin). `place.py` works out where
    each pixel's ground is on Earth and how stretched; where that passes 1.7 the fine detail is taken from the imagery
    unstretched, in ragged cells about 110 km across each laid true to scale, over the broad colour the warp gives.
    Below that the colour follows the warp exactly, because the relief does and the two have to agree.
  - *Ground Avium made.* Ocean islands take the imagery of the real island laid on them. Coasts brought down to an
    Avium-made sea (`flank.py`: Tibet and the Tarim on the Himalayan Sea) take the colour land round them has at their new
    height and green toward the sea. Tartarus takes Antarctica's imagery through the fit its ice surface was laid by, with
    the Rift's warm ground bare. Hyperborea is its ice sheet inside the Northern Wall and black basalt and tundra
    outside it.
  - *On the map* (`hybrid.py`). The layer goes down unsmoothed, lifted a little (`satgrade.grade`), under the
    hillshade. Lakes the imagery has and Avium does not are painted out first (`satgrade.stray_water`).
  - *At 24000 px* (`hybrid.py` -> `layers/hybrid.png`). The map opens two levels past the 12000 px drawings, and on a
    screen of double density a map pixel was three and four screen pixels across under sharp names and lines (the
    user: "Apple Maps overlaid on a PS2 game"). Everything the 12000 build is made of stops near 1.8 km. So this
    drawing is twice the grid, and what is finer than the 12000 build is real: Blue Marble at 500 m and ETOPO at 30
    arc-seconds, each read at the real place every point's ground comes from (the same warps, relaxation, cross-fade
    and river calibration; stretched ground from the same true-to-scale cells). Nothing is decided twice: the
    satellite layer and `height.npy` stand for everything broader than a pixel and a half of theirs, so the month a
    place shows, the ice Avium does not keep, the made ground and the grade are as they were. Where the layer shows
    the midsummer photograph as it is, the fine band is the photograph's; where the layer was made, only the
    photograph's texture goes on it, as light and dark. Fine relief stays off shores, off ground Avium moved, and
    off ground whose real place lies below sea level (the Jordan rift, the Mesopotamian marshes): that ground is laid
    from across the nearest real shore, its place jumps, and fine relief across a jump is a ruled crease. The land's
    edge is `land12k`'s smoothed and drawn at this size (the mask is 6000 px doubled and steps in twos), with 2 px
    islets and lakes kept. The ocean islands read the real island laid on them; the polar continents have nothing
    finer behind them and are the 12000 build enlarged. The sea is asked of `seacolour.py` at this size.
    `work/fine/` holds its caches (some 20 GB, mostly the eight mosaics as plain arrays); `hybrid.py --window r0 r1 c0
    c1 out.png` draws one window for a look. 48000 px was sampled too and is sharper again; it was passed over for the
    weight of its tiles (some 300 MB against 100).
  - *The sea* (`seacolour.py`). The old shaded sea, as varied as the land. Depth sets the tone, off a smoothed depth (the
    sea floor has a flat shelf a few metres deep along every shore, which coloured as it stands is a pale band round every
    coast) and under a softer light than the land's (lit as sharply, a trench wall is a ruled edge). Temperature sets
    the hue: slate in the Hyperborean Ocean and under the katabatic corridor, bluer with teal shoals round the
    meteorological equator, cold again off Tartarus. Faint plankton in the open Hyperborean water; ice adrift off both
    polar coasts, drawn out like smoke in the eddies and gone a few hundred km out (none in the Rift's warm water);
    reefs and banks where warm water is shallow, in stretches (the east of the Sahara Sea above all). The red water of
    the Tartarean Rift, with its plume north, is laid over it (`work/sea_tint.npy`, `tartarus.md`). `seacolour.aux()`
    caches the map-wide distances these need in `work/sea_*.npy`; delete them after the coast changes. Silt plumes off
    the big rivers' mouths were built and taken out again at the user's word.
  - *Kemet's "Nile"* (`colour.py`, `kemet_shore()`). The real Nile cannot exist here: Aswan, Khartoum and Lake Victoria
    lie under Avium's sea, and only Cairo to Luxor is land, a strip on the Sea of Kemet's east shore. The user's call:
    the lower valley's green lines up with that shore, and the delta is its own branch. The imagery's ribbon ran some
    17 km inland with a river's bends; it is taken off and its own colours laid as a band along the water. The delta
    keeps its green and its two branches on the rivers layer, which are a river of their own.
  - *Hyperborea's ice* (`colour.py`, `hyperborea()`), read off the ground's shape: blue in its hollows, a few melt
    ponds and a faint stain of algae in a belt behind the Wall, rock through the ice where it is steep, outlet glaciers
    down the valley floors to the fjords.
  - *Taken back, each on the user's word after seeing it.* Snow drawn from noise; a northern winter (right where the
    real place has a snowy month, wrong over northern Nichirin, where it has none); the imagery with no hillshade (a
    photograph with a photograph's faults and no terrain: "This was a bad idea"); and climate ramps blended from the
    imagery over 30-200 km (pastel blobs that ignored the mountains: "blended quite terribly"). Set anything made beside
    the real thing at the same scale before showing it.
  - `colour.py` keeps its slow halves in `work/` (`bm_MM.npy`, `warp_MM.npy`, `colour_real_MM.npy`, about 19 GB); delete
    them to start again. `--prep` stops after the months. Tartarus and its water are drawn from a generator state that is
    replayed so they stay as the user passed them: do not reorder those draws.
- **Ocean islands** (`islands.py`). Most of Avium's ocean islands sit on open sea on the overlay and sampled nothing, so
  they stood flat at the placeholder height. Each takes a real island's ground: an island with a city takes the island
  its city's stat donor stands on (Ranpua is Hilo, so Hawaii); one without a city near an island with one takes the best
  match by outline among that donor's archipelago (real islands within 1,200 km), each real island used once where the
  group allows; one further out takes the best match among the real islands round the place the overlay puts the
  nearest Avium land. Each is laid on its outline by the turn, mirror, scale and shift that make the outlines agree best
  (ETOPO 2022 60s surface, so Svalbard's ice caps are their surface). A real island shrunk onto a smaller Avium one is
  smoothed so its grain does not alias, and keeps its summits at a little less height. The donors' positions are the
  `DONORS` table; a new island city needs its donor added there. Polar ground is left to `polar.py`.
- **Coasts Earth does not have** (`flank.py`). Where Avium's shore cuts through ground that is high on Earth (the
  Himalayan Sea against Tibet and the Tarim basin) the real relief would stand as a wall at the water. Such a shore
  is known by what lies off it: the real elevation carries on under the sea as high ground. Behind it the land is
  scaled down under an envelope that rises inland like a coastal range (lowland, foothills, range front, full
  height about 300 km in) and is cut by the valleys of a drainage flooded in from the sea. Real coasts, however
  mountainous, have real sea off them and are left alone. Lakes take their level after this step.
- **Polar continents** (`polar.py`). Hyperborea and Tartarus have nothing under them on the overlay, so their
  ground is made from their Talopedia articles, in map space at the pipeline's 1.75 km per px (ground made true
  to the sphere would show stretched toward the corners). Hyperborea: coastal lowland with lava shields, lava
  lobes, cinder cones, raised beaches and thermokarst; the Northern Wall, a volcanic ring about 160 km inland
  (the article says 100; the user moved it), peaks 2,000-4,000 m and 4,187 m at the top, cut by six glacier
  gaps at the heads of the deepest fjords, with end moraines at their mouths; behind it a high ice plateau
  (the article says 200-800 m; the user asked for a plateau): Greenland's ice surface from the same ETOPO grid,
  fitted over the interior (`work/hyperborea_fit.npy`) and brought to 1,350-2,450 m, with buried ranges as
  belts of swell and rows of nunataks, buried basins, bare rock in the lows, ice cauldrons and volcanoes
  through the ice along its edge, and dune ridges across the southeast katabatic wind; deep
  fjords behind sills, glacial troughs across the shelf, and a trench offshore as a smooth arc. Tartarus:
  Antarctica's real ice surface from the ETOPO 2022 60s surface grid (`data/etopo/..._surface.tif`),
  reprojected to true km and laid over Tartarus by the rotation, mirror, scale and shift that best match the
  two outlines (cached in `work/tartarus_fit.npy`; delete it to search again), thin over the Tartarean Rift;
  the Rift is the multi-ring basin in
  the drawing (rocky central massif, deep moat, three ring crests as island arcs joined by submarine ridges over
  troughs, two more rings on land, all inward-facing scarps that show through the ice), hydrothermal vent cones
  on its floor and broad fractures running out from it. Ranges are cut by a drainage flooded in from the sea, as
  in `flank.py`. Ice surfaces carry streams that branch back from where the ice leaves, flow lines along them,
  dune grain across the slope and flat patches over subglacial lakes. No white and no ice tint (tried and removed at the user's word). The two continents get a palette of their own on the Terrain map instead (`render.py`, `POLAR`): at every height the main ramp's CIELAB lightness less 10, in slate, blue-grey and violet-grey, so they do not read as farmland and steppe. Neither
  continent's drawing gives the Tartarean gateways a water passage, and Tartarus's coast does not meet itself
  across the 180th meridian (62.7°S on the right edge, 83.5°S on the bottom one).
- **Eivorie** (`eivorie.py`). Its own ground, made from the Eivorian map (`data/eivorie/eivorie_map.png`, laid on the
  grid by `affine_coast.npy`: fitted to the city dots, then to the coast, which agree to about 6 px). The map's
  shading cannot be lifted off it (its translucent names would come back as ridges), so it only says where the
  uplands and plains are, read from its lit slopes alone. The ground is built as running water would leave it: every cell
  drains to Eivorie's drawn rivers or the sea, and stands above the cell it drains to by the slope a stream of its size
  holds, steep where the map is rugged, so a river's head is on high ground and its valley grows downstream. Heights are
  an assumption (the map gives none), set to sit with the neighbours: 98% under 900 m, summits about 1,500 m. Its relief
  was matched to the neighbours' scale by scale (3-30 km bands within a few metres of theirs). Eased into the neighbours'
  ground over about 50 km.
- **Borders onto rivers** (`riverborders.py`, by hand after `riverlayer.py`; writes `work/borders_snapped.PNG`, and
  `layers/borders.PNG` with `install`). Each pair of neighbours' border is redrawn as the cheapest line that separates
  them, where a line may only run under a river (cheapest down the middle of its drawn width, so the river hides it), on
  the border as drawn, or on a short link between the two through ground that lies between a border and a river no more
  than 15 px apart. Nowhere else, so a border with no river beside it stays exactly as drawn. A quarter of all border was
  drawn on the hand-drawn rivers (`layers/rivers-drawn.PNG`); such a stretch may go 30 px to the traced river. Every patch
  that changes hands is then checked (mostly river on its new edge, no country split, no city moved to another country
  unless it stands at the river) and put back as drawn if it fails. Never touched: the sea, the base map's white
  coastline stroke, stray pieces of 40 px or less. `borderprev.py` draws before/after pictures; the report is
  `work/riverborders_report.txt`; the layer as drawn is kept in `work/borders_before_rivers.PNG`. Earlier tries that
  failed: a zone round borders on drawn rivers (caught 35 patches), any border near any river, a watershed, boxes.
- **Cities out of rivers** (`citybanks.py`, after `riverborders.py`; `write` to apply, then `node scripts/coords.mjs`).
  `riverlayer.py` runs a traced river through every city that stood on a drawn one, so the dot sat on the river's line.
  Each such dot goes to the nearest px clear of the river, on ground, in the country it was in, at most 8 px away; a city
  left on the far bank of a river that became its country's border is brought back to its own bank.
- **Rivers** (`riverlayer.py`). A channel that runs beside a bigger river for most of its way (the Ob's Small Ob, a split
  Chao Phraya) is dropped and its tributaries carried on to the main river: at map scale it reads as one river drawn twice. Real rivers, laid in the valleys of the Avium terrain. Each Natural Earth river
  arrives through the warps a few km off its valley, so it is re-traced on the terrain from its upper end down,
  inside a corridor round the warped line, along the route that climbs least and keeps to the valley floor.
  A trace ends the moment it comes within reach of the sea, a lake or a river already traced, so rivers join and
  never cross, loop or run double. Then: consecutive pieces of one river are stitched; ends left in mid-air run
  downhill to water if that takes no climb; a river whose sea Pangaea closed is led on over the lowest ground
  to the nearest sea, lake or river; stubs are dropped; one flood over the whole network decides which way
  everything runs. Drawn rivers with no real river beside them are traced the same way with the drawn line as
  the guide, so the cities on them keep a river. Eivorie's rivers are fictional: the hand-drawn ones are kept
  there as drawn. `nudge.py` first shifts rivers and elevation together so each river passes the cities that
  stood on it. `GENERATED = False` in `riverlayer.py` puts the hand-drawn layer back everywhere.
- **River beds** (`carve.py`). What the tracing cannot remove is the grain of the elevation data. For each
  network the bed that differs least from the ground and never rises downstream is solved, and the ground
  beside it eased by the same amount; a lake's level moves to fit the rivers running into it.
- **Checks.** `rivqa.py` counts each kind of river defect (cities off their river, doubled lines, specks,
  ruler-straight runs, cusps, networks that end inland); `netprof.py` lists the rivers that sit worst on the
  ground; `spotlook.py out.png x,y[,half] ...` and `seaprev.py` draw check sheets.
