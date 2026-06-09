# DC Market Comparison — EMEA Market Intelligence

Map-driven tool that compares **48 EMEA countries** across **13 data-centre siting factors** with a user-weighted composite score.

Built as a sister tool to `dc-siting-tool` (the UK parcel-level finder). This one is country-level, EMEA-wide, and answers the question: *which markets should we be active in?*

---

## Factors

| Group | Factor | Coverage |
|---|---|---:|
| Demand        | Total compute demand 2027 (TWh)       | 16 / 48 |
| Demand        | Latency reachability sphere (live)    | n/a (live) |
| Grid          | Connection timeline (years)           | 37 / 48 |
| Grid          | Power production / capita (kWh/yr)    | 48 / 48 |
| Grid          | Forecast grid investment (USD bn)     | 27 / 48 |
| Fibre         | Median bandwidth (Gbps)               | 36 / 48 |
| Fibre         | 2030 broadband forecast (Gbps)        | 10 / 48 |
| Differentiator| DC construction cost (USD/MW)         | 31 / 48 |
| Differentiator| Power cost (USD/kWh)                  | 36 / 48 |
| Differentiator| R&D techs per million                 | 32 / 48 |
| Differentiator| Tertiary graduate %                   | 47 / 48 |
| Differentiator| Grid carbon intensity (gCO₂/kWh)      | 48 / 48 |
| Maturity      | Live DC capacity (MW)                 | 32 / 48 |
| Maturity      | Planned DC capacity (MW)              | 28 / 48 |

Every value carries `{value, year, source, url}` and the source link is clickable from the UI.

## Scoring & weighting

The composite is a **weighted average of 10 directional factors** (the 13 above minus 3 informational/neutral ones). Each factor is min-max normalised to 0-100 within its EMEA range, with direction respected (lower is better for cost/wait/carbon). Drag the sliders in the sidebar weights panel, or hit a preset:

- **Reset** — all weights = 5 (balanced)
- **Power** — heavy on grid headroom, connection wait, electricity cost
- **Cost** — heavy on construction + electricity cost
- **Sustain** — heavy on carbon intensity + per-capita production
- **Latency** — heavy on bandwidth + grid speed
- **Off** — zero out scoring

Missing data → the weight renormalises across the factors a country actually has.

## Build pipeline

```
data/countries.geo.json        ← 48 EMEA countries (capital + DC-metro anchors)
data/raw/curated_overrides.json ← manually curated factor values per ISO-2
data/raw/ember_*.json          ← automated fetch — Ember via OWID
data/raw/worldbank_*.json      ← automated fetch — World Bank Indicators
        |
        v
scripts/build_markets_dataset.py
        |
        v
data/markets.json              ← single merged file the browser loads
```

### Refresh data

```bash
# Fetch from open APIs (Ember + World Bank)
python3 scripts/fetch_ember.py
python3 scripts/fetch_world_bank.py

# Optional: refresh map overlays (PeeringDB IXPs + facilities + OSM HV grid)
python3 scripts/fetch_overlays.py

# Merge raw + curated into the single markets.json the browser reads
python3 scripts/build_markets_dataset.py
```

For factors without a stable open API (DC construction cost, planned capacity, grid investment plans), edit `data/raw/curated_overrides.json` directly. Each entry needs `{value, year, source, url}` at minimum.

## Data sources

| Source | Used for |
|---|---|
| **EdenLab 'Inputs' demand model** | Addressable broadband demand 2030 (informational) |
| **Ember (via Our World in Data)** | Power per capita, grid carbon intensity, grid connection wait |
| **Our World in Data** | R&D technicians per million (2022) |
| **UN data** | STEM graduate share (Engineering/Manufacturing/Construction) |
| **Eurostat NRG_PC_205** | Industrial power tariffs (EU) |
| **National TSO/DSO plans & press releases** | Grid connection wait, annual grid investment (€) |
| **Turner & Townsend Data Centre Construction Cost Index 2025-26** | Construction cost (all-in US$/W) — published per-city, others scaled to benchmark |
| **Cushman & Wakefield Global Data Center Market Comparison 2024** | Live + planned DC capacity (FLAP-D + GCC) |
| **JLL EMEA Data Centres Q4 2024** | Live + planned DC capacity (emerging) |
| **datacentermap.com** | Facility counts for smaller markets |
| **TeleGeography** | Average fibre bandwidth (Gbps) |
| **PeeringDB** | IXP and carrier-neutral facility overlays |
| **OpenStreetMap Overpass** | HV (>=220 kV) transmission line overlay |

## Local development

```bash
cd "DC Market Comparison"
python3 -m http.server 8765
# open http://localhost:8765
```

Set the Mapbox token in `config.js`. The token must include `http://localhost:*` in its allowed URLs.

## Architecture

```
DC Market Comparison/
├── index.html         # App shell: sidebar + map + rankings panel + drawer
├── style.css          # Dark theme, cyan accent, traffic-light red→green ramp
├── markets.js         # All UI + state + scoring (vanilla JS, no framework)
├── config.js          # Mapbox token
├── netlify.toml       # Local stub
├── data/
│   ├── countries.geo.json    # 48 EMEA country definitions
│   ├── markets.json          # Merged factor dataset
│   ├── overlay_*.geojson     # Map overlay layers (IXPs, grid, DC sites)
│   └── raw/                  # Source files for the merge step
└── scripts/
    ├── build_markets_dataset.py
    ├── fetch_ember.py
    ├── fetch_world_bank.py
    └── fetch_overlays.py
```

Stack: vanilla JS + Mapbox GL JS 3.x + static JSON. Hosted via the parent project's Netlify site.
