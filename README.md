# DC Site Finder — UK Data Centre Land Intelligence

A map-driven siting tool for identifying and scoring the highest-potential land parcels for new data centre development across the UK.

**Live:** [dcsitingtool.netlify.app](https://dcsitingtool.netlify.app)

---

## What it does

DC developers and real estate buyers typically spend weeks manually screening land parcels across 10+ fragmented data sources — NESO TEC Register, local planning portals, EA flood maps, fibre databases, OS data. This tool replaces that process with a scored, filterable map interface.

**40,000+ raw land parcels** (industrial, brownfield, power, transport and other DC-relevant site types) are scored across six dimensions and surfaced in a single interface.

---

## Scoring model

| Dimension | Weight | Data source |
|-----------|--------|-------------|
| Power / grid access | 35% | 134 UK substations with real NESO TEC Register queue data |
| Fibre connectivity | 20% | ITU BBmaps backbone routes (1,187 segments) + PeeringDB carrier-neutral colos |
| Flood risk | 15% | EA Flood Map for Planning (Zone 1/2/3) |
| Planning / land use | 15% | OSM landuse classification |
| Buildability | 10% | Site area + type penalties |
| Market proximity | 5% | Distance to Tier 1 demand centres |

**Composite score 0–100.** Hard exclusion for Flood Zone 3 (toggleable).

---

## Features

- **Map** — Mapbox GL JS dark basemap with parcel polygons, substation overlay (colour-coded by TEC queue pressure), animated powerline layer, ITU backbone fibre routes
- **Colour modes** — colour parcels by site type, power score, or composite score
- **DC size selector** — 20 / 50 / 100 MW; scores interpolate between anchors
- **Filters** — region, minimum site size, minimum composite score, flood zone exclusion, site type toggles
- **Site detail panel** — full score breakdown by dimension, power sub-scores, connection timeline estimate based on TEC queue pressure
- **Parcel list** — top 100 matching parcels sorted by composite score, synced to map selection
- **Area search** — restrict list to current map viewport

---

## Data sources

| File | Source | Notes |
|------|--------|-------|
| `uk_industrial_parcels.geojson` | OpenStreetMap (Overpass API) | 40k+ parcels, >2 acres, pre-enriched with all scores |
| `uk_substations.json` | NESO TEC Register | 134 substations with real queue data as of early 2025 |
| `uk_powerlines.geojson` | OpenStreetMap | 132kV+ transmission lines |
| `uk_fibre_routes.geojson` | ITU BBmaps WFS | 1,187 operational UK backbone fibre route segments |
| `uk_peeringdb.json` | PeeringDB API | UK internet exchanges and carrier-neutral facilities |

---

## Enrichment pipeline

Data enrichment runs offline and outputs the scored GeoJSON. Scripts run in order:

```bash
python3 scripts/fetch_osm_parcels.py        # fetch raw land parcels from Overpass
python3 scripts/fetch_powerlines.py         # fetch 132kV+ lines from OSM
python3 scripts/fetch_peeringdb.py          # fetch UK IXPs and carrier colos
python3 scripts/fetch_itu_fibre.py          # fetch ITU backbone fibre routes
python3 scripts/enrich_power_scores.py      # add power scores (substation proximity + TEC queue)
python3 scripts/enrich_flood_zones.py       # add EA flood zone classification (resumable, ~3hr)
python3 scripts/enrich_fibre_routes.py      # add distance to nearest backbone fibre route
python3 scripts/enrich_composite_scores.py  # compute final composite scores across all dimensions
```

---

## Local development

```bash
python3 -m http.server 8080
# open http://localhost:8080
```

Requires a [Mapbox](https://mapbox.com) public token in `config.js`.

---

## Deployment

Hosted on Netlify, auto-deploys on push to `main`. The `netlify.toml` sets long-cache headers on `/data/*` files to avoid re-downloading the 65MB parcels file on every visit.

---

## Key technical decisions

- **Static GeoJSON** — all enrichment runs offline; the map loads a single pre-scored file rather than making live API calls. Avoids rate limits and latency.
- **Three MW anchors** — power and composite scores are pre-computed at 20/50/100 MW and linearly interpolated at runtime, avoiding per-parcel recalculation in the browser.
- **ITU BBmaps for fibre** — the only freely available source of UK backbone fibre route geometry. All routes are 2-vertex segments, enabling fast point-to-segment distance computation (~30s for 40k parcels).
- **EA flood zones** — the EA OGC API rate-limits aggressively. The enrichment script uses a 5s request delay, geographic filtering to skip non-England cells, and a resumable checkpoint file.
