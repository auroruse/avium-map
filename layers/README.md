# Layer PNGs

Export these from ibis Paint as separate 6000×6000 PNGs:

| File | ibis Paint Layer | Notes |
|------|-----------------|-------|
| `base.png` | Layer 1 — Land and sea | Fully opaque, no text or markers |
| `borders.png` | Layer 3 — National borders | Transparent background |

Four more are written here by `topo/`, never exported by hand (see `topo/README.md`):

| File | Notes |
|------|-------|
| `rivers.png` | Real rivers carried through the Pangaea overlay, plus Eivorie's from the drawing. Exporting layer 4 over it puts the hand-drawn rivers back |
| `rivers-drawn.PNG` | The hand-drawn rivers as last exported. `topo/` reads Eivorie's rivers and the river cities from it |
| `relief.png`, `contours.png` | 12000×12000, the Political map's shaded ground and the contour lines |
| `terrain.png` | 12000×12000, elevation tints. Not tiled since the Terrain map went; `topo/`'s check sheets are drawn on it |
| `hybrid.png`, `rivers-fine.png` | 12000×12000, the Hybrid map's ground (the terrain over a deep blue sea, no coastline) and its rivers at near their real width |

**Do not export** layers 2 (grid — built into the app), 5 (Pangaea overlay), 6 (city markers), 7 (city names), or 8 (nation names).

After placing the PNGs here, run:

```
npm run tile
```

You can also tile a single layer:

```
npm run tile base
```
