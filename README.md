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
| Power / grid access | 40% | 134 UK substations with real NESO TEC Register queue data |
| Permissioning | 30% | Site type + Green/Grey Belt + AI Growth Zone; three buckets (A/B/C) |
| Fibre connectivity | 20% | ITU BBmaps backbone routes (1,187 segments) + PeeringDB carrier-neutral colos |
| Buildability | 10% | Site area + type penalties |

**Composite score 0–100.** Flood Zone 3 is a hard exclusion (site removed from scoring); Zone 1/2 shown as informational tags only.

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

---

## Known issues / backlog

### Power scoring — substations with fabricated headroom (6 of 134)

The following substations still use estimated headroom values. Real DNO data should be sourced to correct scores for the ~6,000 parcels that use these as their best substation.

| Substation | kV | Parcels | Issue | Data source needed |
|---|---|---|---|---|
| **Hunterston** | 400 | 1,544 | SPEN SPD — no import limit found | `gsp-overview` (SPD) on spenergynetworks.opendatasoft.com (requires login) |
| **Tealing** | 275 | 1,230 | SPEN SPD — no matching distribution GSP found | Same as above |
| **Grendon** | 400 | 1,014 | UKPN has entry but `asset_import_limit = N/A` | Check UKPN Open Data portal for Grendon alternate name |
| **Clydes Mill** | 275 | 977 | SPEN SPD — no matching distribution GSP found | Same as Hunterston |
| **Corby** | 400 | 818 | Maps to Grendon (UKPN) which has no limit data | Check UKPN portal for Corby or nearby GSP |
| **Elvanfoot** | 400 | 397 | SPEN SPD — remote windfarm area, no distribution GSP | Same as Hunterston |

**Fix procedure** (once data is obtained):
1. Add entry to `NAME_MAP` in `scripts/process_dno_headroom.py`
2. Or add new loader function (see `load_spen_spd_utilisation()` as template)
3. Re-run: `process_dno_headroom.py` → `enrich_power_scores.py` → `enrich_composite_scores.py`

**SPEN SPD portal** (covers Hunterston, Tealing, Clydes Mill, Elvanfoot): register free at spenergynetworks.opendatasoft.com → dataset `gsp-overview` → filter `licence_area=SPD` → export CSV. Convert to `data/spen_spd_technical_limits.json` matching the `spen_spm_technical_limits.json` schema.

### Power QA findings (March 2026)

- **3,271 parcels >50km from nearest substation** — all are remote islands (Faroe, Shetland, Orkney) or Highlands scored against Dounreay (364km). These score low due to 0.30 distance factor. Consider filtering off-mainland sites from the UI.
- **Substations with zero headroom** (Keadby, Stella West, Norton, Grimsby West, South Humber Bank, Willington) score headroom=0 correctly. Broxbourne/Rye House/Waltham Cross have slightly negative headroom (−0.6 MVA) from UKPN data — treated as zero.
- **Wimbledon**: −70.7 MVA headroom (UKPN overcapacity) — correctly scores headroom=0.
- **Clydes Mill fabrication risk**: 977 parcels use Clydes Mill (fabricated 140 MVA / score 75.5) as best_sub, overriding nearer but constrained Erskine (23 MVA). Will self-correct when Clydes Mill gets real SPEN SPD data.
- **Flood enrichment: complete** — all 63,478 parcels have real EA flood zones (Zone 1: 88.7%, Zone 2: 2.8%, Zone 3: 8.5%).
