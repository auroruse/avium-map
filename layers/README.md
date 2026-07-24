# Layer PNGs

Export these from ibis Paint as separate 6000×6000 PNGs:

| File | ibis Paint Layer | Notes |
|------|-----------------|-------|
| `base.png` | Layer 1 — Land and sea | Fully opaque, no text or markers |
| `borders.png` | Layer 3 — National borders | Transparent background |
| `rivers.png` | Layer 4 — Rivers | Transparent background |

**Do not export** layers 2 (grid — built into the app), 5 (Pangaea overlay), 6 (city markers), 7 (city names), or 8 (nation names).

After placing the PNGs here, run:

```
npm run tile
```

You can also tile a single layer:

```
npm run tile base
```
