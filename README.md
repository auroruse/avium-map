# Avium Map

Interactive world map built for [Avium](https://www.nationstates.net/page=dispatch/id=1815726). Leaflet.js with tiled layers, zero backend.

**[Live App](https://auroruse.github.io/avium-map/)** | **[Discord](https://discord.gg/zVhxZXFea4)**

## Features

### Map
- 6000x6000px base map served as 256px tiles for fast loading at any zoom
- National borders and rivers as toggleable overlay layers
- Apple Maps-style frosted glass UI controls
- Smooth half-step zoom (0.5 increments) with hierarchical city rendering

### Cities
- 1700+ cities with population-tiered markers and labels
- Collision-aware label placement with spatial indexing
- Cities appear progressively as you zoom in (5M+ first, then 1M+, then all)
- Click any city for an info panel showing population, GDP PPP, per capita, rankings, and IRL parallel
- Accent-insensitive search

### Developer Mode
- Append `?dev` to the URL to enter placement mode
- Search and click-to-place cities on the map
- Unassigned cities panel sorted by priority
- TSV paste import with flexible column mapping
- JSON export/import for cities and labels
- Pangaea reference overlay toggle
- Coordinate display on mouse move
